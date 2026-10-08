from __future__ import annotations

import hmac
import json
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.dependencies import _token_from_request, get_refresh_token
from ..common.exceptions import UnauthorizedError
from ..common.rate_limit import limiter
from ..config import settings
from ..database import get_db
from ..schemas.auth import (
    LoginRequest,
    RefreshResponse,
    TempTokenResponse,
    TokenResponse,
)
from ..services.auth_service import (
    authenticate_local,
    create_access_token,
    create_refresh_token,
    create_temp_token,
    decode_token,
    get_or_create_user_by_netid,
    get_user_by_id,
)

router = APIRouter(prefix="/auth", tags=["auth"])
logger = structlog.get_logger()

_REFRESH_COOKIE = "refresh_token"
_COOKIE_MAX_AGE = 7 * 24 * 3600  # 7 days in seconds


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=token,
        httponly=True,
        secure=not settings.is_development,
        samesite="lax",
        max_age=_COOKIE_MAX_AGE,
        path="/api/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=_REFRESH_COOKIE, path="/api/auth")


# ---------------------------------------------------------------------------
# POST /api/auth/login
# ---------------------------------------------------------------------------


@router.post("/login")
@limiter.limit("5/15minutes")
async def login(
    request: Request,
    body: LoginRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse | TempTokenResponse:
    # --- Dev fallback: accept {netid} directly ---
    if body.netid:
        if not settings.is_development:
            raise UnauthorizedError("netid login only available in development mode")
        user = await get_or_create_user_by_netid(db, body.netid, None)
        await db.commit()
        return TempTokenResponse(temp_token=create_temp_token(user.id))

    # --- Normal username/password login ---
    user = await authenticate_local(db, body.username, body.password)  # type: ignore[arg-type]
    if not user:
        raise UnauthorizedError("Invalid credentials")
    await db.commit()

    access_token = create_access_token(user.id, user.role)
    refresh_token = create_refresh_token(user.id)
    _set_refresh_cookie(response, refresh_token)

    logger.info("login_success", user_id=user.id, role=user.role)
    return TokenResponse(access_token=access_token)


# ---------------------------------------------------------------------------
# GET /api/auth/oauth2-callback  (protected by an OAuth2/SSO proxy middleware
# sitting in front of this service — see README for the campus SSO setup)
# ---------------------------------------------------------------------------

_ALLOWED_REDIRECT_PATHS = {"/student/login", "/staff/login", "/admin/login"}
_PROXY_SECRET_HEADER = "X-Proxy-Shared-Secret"


@router.get("/oauth2-callback", response_class=HTMLResponse)
async def oauth2_callback(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    redirect_to: str = "/student/login",
) -> HTMLResponse:
    if redirect_to not in _ALLOWED_REDIRECT_PATHS:
        redirect_to = "/student/login"

    dest_url = f"{settings.FRONTEND_URL}{redirect_to}"

    # X-Auth-Request-* are otherwise trivial to spoof by anyone with network
    # access to this service — refuse to trust them at all unless the
    # request also carries the secret only the configured OAuth2 proxy
    # knows. Fails closed: an unconfigured secret means this endpoint never
    # succeeds, rather than silently trusting unauthenticated headers.
    # constant-time comparison; same generic error in every failure case so
    # a caller can't distinguish "not configured" from "wrong secret".
    provided_secret = request.headers.get(_PROXY_SECRET_HEADER, "")
    if not settings.OAUTH2_PROXY_SHARED_SECRET or not hmac.compare_digest(
        provided_secret, settings.OAUTH2_PROXY_SHARED_SECRET
    ):
        logger.error(
            "oauth2_callback_untrusted_request",
            configured=bool(settings.OAUTH2_PROXY_SHARED_SECRET),
            secret_present=bool(provided_secret),
        )
        return HTMLResponse(
            _redirect_html(
                dest_url, error="No user information received from OAuth2 provider"
            )
        )

    netid = request.headers.get("X-Auth-Request-User")
    email = request.headers.get("X-Auth-Request-Email")

    if not netid:
        logger.error("oauth2_callback_no_netid", headers=dict(request.headers))
        return HTMLResponse(
            _redirect_html(
                dest_url, error="No user information received from OAuth2 provider"
            )
        )

    user = await get_or_create_user_by_netid(db, netid, email)
    await db.commit()

    temp_token = create_temp_token(user.id)
    auth_data = json.dumps({"temp_token": temp_token})

    logger.info("oauth2_login_success", netid=netid, user_id=user.id)
    return HTMLResponse(_redirect_html(dest_url, auth_data=auth_data))


def _redirect_html(
    dest_url: str, auth_data: str | None = None, error: str | None = None
) -> str:
    if error:
        escaped = error.replace("'", "\\'")
        return f"""<!DOCTYPE html><html><head><script>
window.location.href = '{dest_url}?from=oauth2&error=' + encodeURIComponent('{escaped}');
</script></head><body>Redirecting...</body></html>"""

    return f"""<!DOCTYPE html><html><head><script>
const data = {auth_data};
window.location.href = '{dest_url}?from=oauth2#oauth2_data=' + encodeURIComponent(JSON.stringify(data));
</script></head><body>Authenticating...</body></html>"""


# ---------------------------------------------------------------------------
# POST /api/auth/exchange-temp
# ---------------------------------------------------------------------------


@router.post("/exchange-temp")
@limiter.limit("10/minute")
async def exchange_temp(
    request: Request,
    token: Annotated[str | None, Depends(_token_from_request)],
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Exchange a temp token (from OAuth2 callback) for a full access + refresh token pair."""
    if not token:
        raise UnauthorizedError("Authentication required")
    try:
        payload = decode_token(token)
    except JWTError:
        raise UnauthorizedError("Invalid or expired token")
    if payload.get("token_type") != "temp":
        raise UnauthorizedError("Temp token required")

    user = await get_user_by_id(db, payload["sub"])
    if not user:
        raise UnauthorizedError("User not found")

    access_token = create_access_token(user.id, user.role)
    refresh_token = create_refresh_token(user.id)
    _set_refresh_cookie(response, refresh_token)
    logger.info("temp_token_exchanged", user_id=user.id, role=user.role)
    return TokenResponse(access_token=access_token)


# ---------------------------------------------------------------------------
# POST /api/auth/refresh
# ---------------------------------------------------------------------------


@router.post("/refresh")
async def refresh_token(
    response: Response,
    token: Annotated[str, Depends(get_refresh_token)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RefreshResponse:
    try:
        payload = decode_token(token)
    except JWTError:
        raise UnauthorizedError("Invalid or expired refresh token")

    if payload.get("token_type") != "refresh":
        raise UnauthorizedError("Not a refresh token")

    user = await get_user_by_id(db, payload["sub"])
    if not user:
        raise UnauthorizedError("User not found")

    new_access = create_access_token(user.id, user.role)
    new_refresh = create_refresh_token(user.id)
    _set_refresh_cookie(response, new_refresh)

    return RefreshResponse(access_token=new_access)


# ---------------------------------------------------------------------------
# POST /api/auth/logout
# ---------------------------------------------------------------------------


@router.post("/logout", status_code=204)
async def logout(response: Response) -> None:
    _clear_refresh_cookie(response)

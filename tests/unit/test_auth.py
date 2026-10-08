"""
Unit tests for auth endpoints.

Runs against the FastAPI app directly via httpx.AsyncClient with a mocked
database dependency — no Docker stack required.

Run with:
    cd tests/unit && pytest test_auth.py -v
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def mock_user() -> MagicMock:
    u = MagicMock()
    u.id = "test-user-id-123"
    u.role = "USER"
    u.netid = "jsmith"
    return u


@pytest_asyncio.fixture
async def client(mock_user):
    """
    AsyncClient backed by the FastAPI app, with the DB dependency replaced
    by a mock so no running services are required.
    """
    from app.database import get_db
    from app.main import app

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=mock_user)

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac, mock_user

    app.dependency_overrides.clear()


@pytest.fixture
def proxy_secret(monkeypatch) -> str:
    """Configure OAUTH2_PROXY_SHARED_SECRET for tests that exercise the
    successful oauth2-callback path (it refuses everything without this)."""
    from app.config import settings

    secret = "test-proxy-secret"
    monkeypatch.setattr(settings, "OAUTH2_PROXY_SHARED_SECRET", secret)
    return secret


# ---------------------------------------------------------------------------
# POST /api/auth/exchange-temp
# ---------------------------------------------------------------------------


class TestExchangeTemp:
    async def test_valid_temp_token_returns_access_token(self, client):
        ac, user = client
        from app.services.auth_service import create_temp_token

        temp = create_temp_token(user.id)

        r = await ac.post("/api/auth/exchange-temp", headers={"Authorization": f"Bearer {temp}"})
        assert r.status_code == 200
        body = r.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    async def test_access_token_rejected(self, client):
        ac, user = client
        from app.services.auth_service import create_access_token

        token = create_access_token(user.id, user.role)

        r = await ac.post("/api/auth/exchange-temp", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401

    async def test_refresh_token_rejected(self, client):
        ac, user = client
        from app.services.auth_service import create_refresh_token

        token = create_refresh_token(user.id)

        r = await ac.post("/api/auth/exchange-temp", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401

    async def test_missing_token_returns_401(self, client):
        ac, _ = client
        r = await ac.post("/api/auth/exchange-temp")
        assert r.status_code == 401

    async def test_garbage_token_returns_401(self, client):
        ac, _ = client
        r = await ac.post(
            "/api/auth/exchange-temp", headers={"Authorization": "Bearer not.a.real.jwt"}
        )
        assert r.status_code == 401

    async def test_unknown_user_returns_401(self, client):
        """If the user_id in the temp token no longer exists, reject."""
        ac, _ = client
        from app.database import get_db
        from app.main import app
        from app.services.auth_service import create_temp_token

        mock_db_empty = AsyncMock()
        mock_db_empty.get = AsyncMock(return_value=None)  # user not found

        async def no_user_db():
            yield mock_db_empty

        app.dependency_overrides[get_db] = no_user_db

        temp = create_temp_token("nonexistent-user-id")
        r = await ac.post("/api/auth/exchange-temp", headers={"Authorization": f"Bearer {temp}"})

        app.dependency_overrides.pop(get_db, None)
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/auth/oauth2-callback
# ---------------------------------------------------------------------------


class TestOauth2Callback:
    async def test_missing_netid_header_returns_error_redirect(self, client, proxy_secret):
        """No X-Auth-Request-User → HTML page redirecting with ?error="""
        ac, _ = client
        r = await ac.get(
            "/api/auth/oauth2-callback", headers={"X-Proxy-Shared-Secret": proxy_secret}
        )
        assert r.status_code == 200
        assert "error" in r.text

    async def test_invalid_redirect_to_falls_back_to_student_login(
        self, client, mock_user, proxy_secret
    ):
        ac, _ = client
        with patch(
            "app.routers.auth.get_or_create_user_by_netid", AsyncMock(return_value=mock_user)
        ):
            r = await ac.get(
                "/api/auth/oauth2-callback",
                params={"redirect_to": "/evil/steal-tokens"},
                headers={
                    "X-Auth-Request-User": "jsmith",
                    "X-Auth-Request-Email": "jsmith@wisc.edu",
                    "X-Proxy-Shared-Secret": proxy_secret,
                },
            )
        assert r.status_code == 200
        # Must redirect to /student/login (the safe default), not the attacker path
        assert "/student/login" in r.text
        assert "steal-tokens" not in r.text

    async def test_redirect_to_staff_login_accepted(self, client, mock_user, proxy_secret):
        ac, _ = client
        with patch(
            "app.routers.auth.get_or_create_user_by_netid", AsyncMock(return_value=mock_user)
        ):
            r = await ac.get(
                "/api/auth/oauth2-callback",
                params={"redirect_to": "/staff/login"},
                headers={
                    "X-Auth-Request-User": "jsmith",
                    "X-Auth-Request-Email": "jsmith@wisc.edu",
                    "X-Proxy-Shared-Secret": proxy_secret,
                },
            )
        assert r.status_code == 200
        assert "/staff/login" in r.text

    async def test_successful_callback_embeds_temp_token(self, client, mock_user, proxy_secret):
        ac, _ = client
        with patch(
            "app.routers.auth.get_or_create_user_by_netid", AsyncMock(return_value=mock_user)
        ):
            r = await ac.get(
                "/api/auth/oauth2-callback",
                headers={
                    "X-Auth-Request-User": "jsmith",
                    "X-Auth-Request-Email": "jsmith@wisc.edu",
                    "X-Proxy-Shared-Secret": proxy_secret,
                },
            )
        assert r.status_code == 200
        assert "temp_token" in r.text
        assert "oauth2_data" in r.text

    # -- Security: the whole point of the proxy secret is that the
    # X-Auth-Request-* headers can't be trusted on their own. Each of these
    # sends a fully "valid-looking" identity header and confirms it's still
    # rejected — no temp_token anywhere in the response — without the
    # correct secret alongside it.

    async def test_no_secret_configured_rejects_even_with_valid_netid_header(
        self, client, mock_user
    ):
        """Default state (OAUTH2_PROXY_SHARED_SECRET unset) — fail closed."""
        ac, _ = client
        with patch(
            "app.routers.auth.get_or_create_user_by_netid", AsyncMock(return_value=mock_user)
        ):
            r = await ac.get(
                "/api/auth/oauth2-callback",
                headers={"X-Auth-Request-User": "jsmith", "X-Auth-Request-Email": "j@wisc.edu"},
            )
        assert r.status_code == 200
        assert "temp_token" not in r.text
        assert "error=" in r.text

    async def test_missing_secret_header_rejected(self, client, mock_user, proxy_secret):
        """Secret is configured, but this request doesn't send it at all."""
        ac, _ = client
        with patch(
            "app.routers.auth.get_or_create_user_by_netid", AsyncMock(return_value=mock_user)
        ):
            r = await ac.get(
                "/api/auth/oauth2-callback",
                headers={"X-Auth-Request-User": "jsmith", "X-Auth-Request-Email": "j@wisc.edu"},
            )
        assert r.status_code == 200
        assert "temp_token" not in r.text

    async def test_wrong_secret_rejected(self, client, mock_user, proxy_secret):
        ac, _ = client
        with patch(
            "app.routers.auth.get_or_create_user_by_netid", AsyncMock(return_value=mock_user)
        ):
            r = await ac.get(
                "/api/auth/oauth2-callback",
                headers={
                    "X-Auth-Request-User": "jsmith",
                    "X-Auth-Request-Email": "j@wisc.edu",
                    "X-Proxy-Shared-Secret": proxy_secret + "-wrong",
                },
            )
        assert r.status_code == 200
        assert "temp_token" not in r.text


# ---------------------------------------------------------------------------
# POST /api/auth/login
# ---------------------------------------------------------------------------


class TestLogin:
    async def test_password_login_success(self, client, mock_user):
        ac, _ = client
        with patch("app.routers.auth.authenticate_local", AsyncMock(return_value=mock_user)):
            r = await ac.post(
                "/api/auth/login", json={"username": "jsmith", "password": "correct-password"}
            )
        assert r.status_code == 200
        assert "access_token" in r.json()

    async def test_password_login_wrong_credentials_rejected(self, client):
        ac, _ = client
        with patch("app.routers.auth.authenticate_local", AsyncMock(return_value=None)):
            r = await ac.post(
                "/api/auth/login", json={"username": "jsmith", "password": "wrong-password"}
            )
        assert r.status_code == 401

    async def test_netid_login_works_in_development(self, client, mock_user, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "APP_ENV", "development")
        ac, _ = client
        with patch(
            "app.routers.auth.get_or_create_user_by_netid", AsyncMock(return_value=mock_user)
        ):
            r = await ac.post("/api/auth/login", json={"netid": "jsmith"})
        assert r.status_code == 200
        assert "temp_token" in r.json()

    async def test_netid_login_rejected_outside_development(self, client, monkeypatch):
        """The dev netid fallback must not work once APP_ENV isn't 'development' —
        it's a real authentication bypass (no password, no SSO) if left open."""
        from app.config import settings

        monkeypatch.setattr(settings, "APP_ENV", "production")
        ac, _ = client
        r = await ac.post("/api/auth/login", json={"netid": "jsmith"})
        assert r.status_code == 401

    async def test_missing_credentials_rejected(self, client):
        ac, _ = client
        r = await ac.post("/api/auth/login", json={})
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/auth/refresh, POST /api/auth/logout
# ---------------------------------------------------------------------------


class TestRefreshAndLogout:
    async def test_refresh_without_cookie_rejected(self, client):
        ac, _ = client
        r = await ac.post("/api/auth/refresh")
        assert r.status_code == 401

    async def test_refresh_with_garbage_cookie_rejected(self, client):
        ac, _ = client
        ac.cookies.set("refresh_token", "not.a.real.jwt")
        r = await ac.post("/api/auth/refresh")
        assert r.status_code == 401

    async def test_refresh_with_access_token_cookie_rejected(self, client):
        """An access token is not a refresh token — the endpoint must check
        token_type, not just that the JWT is validly signed."""
        ac, user = client
        from app.services.auth_service import create_access_token

        ac.cookies.set("refresh_token", create_access_token(user.id, user.role))
        r = await ac.post("/api/auth/refresh")
        assert r.status_code == 401

    async def test_refresh_with_valid_token_succeeds(self, client):
        ac, user = client
        from app.services.auth_service import create_refresh_token

        ac.cookies.set("refresh_token", create_refresh_token(user.id))
        r = await ac.post("/api/auth/refresh")
        assert r.status_code == 200
        assert "access_token" in r.json()

    async def test_logout_clears_cookie(self, client):
        ac, _ = client
        r = await ac.post("/api/auth/logout")
        assert r.status_code == 204

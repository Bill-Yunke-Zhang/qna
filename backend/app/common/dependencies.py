from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import Cookie, Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.exceptions import ForbiddenError, NotFoundError, UnauthorizedError
from ..database import get_db
from ..models.course import UserCourseAccess
from ..models.user import User
from ..services.auth_service import decode_token, get_user_by_id

logger = structlog.get_logger()

_bearer = HTTPBearer(auto_error=False)


async def _token_from_request(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    access_token: Annotated[str | None, Cookie()] = None,
) -> str | None:
    """Extract JWT from Authorization header or access_token cookie."""
    if credentials:
        return credentials.credentials
    return access_token


async def get_current_user(
    token: Annotated[str | None, Depends(_token_from_request)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if not token:
        raise UnauthorizedError("Authentication required")
    try:
        payload = decode_token(token)
    except JWTError:
        raise UnauthorizedError("Invalid or expired token")

    token_type = payload.get("token_type")
    if token_type not in ("access", "temp"):
        raise UnauthorizedError("Invalid token type")

    user = await get_user_by_id(db, payload["sub"])
    if not user:
        raise UnauthorizedError("User not found")
    return user


async def require_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if user.role != "ADMIN":
        raise ForbiddenError("Admin access required")
    return user


async def get_refresh_token(
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> str:
    if not refresh_token:
        raise UnauthorizedError("No refresh token")
    return refresh_token


# ---------------------------------------------------------------------------
# Course-scoped access — a global ADMIN may act in any course; otherwise the
# caller must hold an explicit STUDENT/STAFF grant for the course_id in the
# path (see UserCourseAccess, populated via the admin course-access endpoints).
#
# Each frontend app declares which surface it is on every request via the
# X-App-Surface header ("student" or "staff" — see each app's lib/api.ts).
# The Student app always sends "student", which clamps the effective role to
# STUDENT no matter what the account's real capability is — so a global
# ADMIN (or a STAFF member) using the Student app posts, answers, and is
# permission-checked exactly as a student would be. The header can only ever
# *restrict* capability, never grant it: it clamps the role computed from
# real course access below, it never substitutes for it.
# ---------------------------------------------------------------------------


class CourseMember:
    """Resolved course membership: the user plus their effective role."""

    def __init__(self, user: User, course_role: str):
        self.user = user
        self.course_role = course_role


async def require_course_member(
    course_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    x_app_surface: Annotated[str | None, Header(alias="X-App-Surface")] = None,
) -> CourseMember:
    if user.role == "ADMIN":
        natural_role = "STAFF"
    else:
        result = await db.execute(
            select(UserCourseAccess).where(
                UserCourseAccess.user_id == user.id,
                UserCourseAccess.course_id == course_id,
            )
        )
        access = result.scalar_one_or_none()
        if not access:
            raise NotFoundError(f"Course {course_id} not found")
        natural_role = access.role

    effective_role = "STUDENT" if x_app_surface == "student" else natural_role
    return CourseMember(user, effective_role)


async def require_course_staff(
    member: Annotated[CourseMember, Depends(require_course_member)],
) -> CourseMember:
    if member.course_role != "STAFF":
        raise ForbiddenError("Course staff access required")
    return member

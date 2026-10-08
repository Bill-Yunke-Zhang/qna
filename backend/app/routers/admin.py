from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.dependencies import require_admin
from ..common.exceptions import ConflictError, NotFoundError
from ..common.uploads import read_upload_capped
from ..database import get_db
from ..models.course import Course, CourseRoster, UserCourseAccess
from ..models.user import User
from ..schemas.admin import (
    CourseAccessGrant,
    CourseCreate,
    CourseResponse,
    CourseUpdate,
    RosterEntryPatch,
    RosterEntryResponse,
    RosterImportPayload,
    RosterUploadResult,
    StaffUploadResult,
    UserCreate,
    UserResponse,
    UserUpdate,
    UserWithAccessResponse,
)
from ..services.auth_service import hash_password
from ..services.roster_service import process_roster_csv, process_roster_rows
from ..services.staff_service import process_staff_csv

router = APIRouter(prefix="/admin", tags=["admin"])
logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------


@router.get("/courses", response_model=list[CourseResponse])
async def list_courses(
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Course]:
    result = await db.execute(
        select(Course).order_by(Course.semester.desc(), Course.name)
    )
    return list(result.scalars().all())


@router.post("/courses", response_model=CourseResponse, status_code=201)
async def create_course(
    body: CourseCreate,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Course:
    course = Course(name=body.name, semester=body.semester)
    db.add(course)
    await db.flush()
    await db.refresh(course)
    await db.commit()
    logger.info("course_created", course_id=course.id, name=body.name)
    return course


@router.get("/courses/{course_id}", response_model=CourseResponse)
async def get_course(
    course_id: int,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Course:
    course = await db.get(Course, course_id)
    if not course:
        raise NotFoundError(f"Course {course_id} not found")
    return course


@router.put("/courses/{course_id}", response_model=CourseResponse)
async def update_course(
    course_id: int,
    body: CourseUpdate,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Course:
    course = await db.get(Course, course_id)
    if not course:
        raise NotFoundError(f"Course {course_id} not found")
    if body.name is not None:
        course.name = body.name
    if body.semester is not None:
        course.semester = body.semester
    return course


# ---------------------------------------------------------------------------
# Roster
# ---------------------------------------------------------------------------


@router.get("/courses/{course_id}/roster", response_model=list[RosterEntryResponse])
async def list_roster(
    course_id: int,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[CourseRoster]:
    course = await db.get(Course, course_id)
    if not course:
        raise NotFoundError(f"Course {course_id} not found")
    result = await db.execute(
        select(CourseRoster)
        .where(CourseRoster.course_id == course_id)
        .order_by(CourseRoster.full_name)
    )
    return list(result.scalars().all())


@router.post("/courses/{course_id}/roster", response_model=RosterUploadResult)
async def upload_roster(
    course_id: int,
    file: Annotated[UploadFile, File(description="Canvas gradebook CSV export")],
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RosterUploadResult:
    course = await db.get(Course, course_id)
    if not course:
        raise NotFoundError(f"Course {course_id} not found")
    content = await read_upload_capped(file)
    result = await process_roster_csv(db, course_id, content)
    await db.commit()
    return result


@router.post("/courses/{course_id}/roster/import", response_model=RosterUploadResult)
async def import_roster_rows(
    course_id: int,
    payload: RosterImportPayload,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RosterUploadResult:
    course = await db.get(Course, course_id)
    if not course:
        raise NotFoundError(f"Course {course_id} not found")
    rows = [
        {"netid": r.netid, "full_name": r.full_name, "email": r.email}
        for r in payload.rows
    ]
    result = await process_roster_rows(db, course_id, rows)
    await db.commit()
    return result


@router.patch(
    "/courses/{course_id}/roster/{roster_id}", response_model=RosterEntryResponse
)
async def patch_roster_entry(
    course_id: int,
    roster_id: int,
    body: RosterEntryPatch,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CourseRoster:
    result = await db.execute(
        select(CourseRoster).where(
            CourseRoster.id == roster_id, CourseRoster.course_id == course_id
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise NotFoundError(f"Roster entry {roster_id} not found in course {course_id}")
    if body.is_active is not None:
        entry.is_active = body.is_active
    if body.netid is not None:
        entry.netid = body.netid.strip().lower()
    if body.full_name is not None:
        entry.full_name = body.full_name.strip()
    if body.email is not None:
        entry.email = str(body.email).lower()
    return entry


# ---------------------------------------------------------------------------
# Staff
# ---------------------------------------------------------------------------


@router.get("/courses/{course_id}/staff", response_model=list[UserResponse])
async def list_staff(
    course_id: int,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[User]:
    course = await db.get(Course, course_id)
    if not course:
        raise NotFoundError(f"Course {course_id} not found")
    result = await db.execute(
        select(User)
        .join(UserCourseAccess, UserCourseAccess.user_id == User.id)
        .where(
            UserCourseAccess.course_id == course_id, UserCourseAccess.role == "STAFF"
        )
        .order_by(User.display_name)
    )
    return list(result.scalars().all())


@router.post("/courses/{course_id}/staff", response_model=StaffUploadResult)
async def upload_staff(
    course_id: int,
    file: Annotated[
        UploadFile, File(description="CSV with netid, full_name, email columns")
    ],
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StaffUploadResult:
    course = await db.get(Course, course_id)
    if not course:
        raise NotFoundError(f"Course {course_id} not found")
    content = await read_upload_capped(file)
    result = await process_staff_csv(db, course_id, content)
    await db.commit()
    return result


# ---------------------------------------------------------------------------
# Users (local accounts)
# ---------------------------------------------------------------------------


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[User]:
    result = await db.execute(select(User).order_by(User.role, User.username))
    return list(result.scalars().all())


@router.post("/users", response_model=UserResponse, status_code=201)
async def create_user(
    body: UserCreate,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none():
        raise ConflictError(f"Username '{body.username}' is already taken")

    user = User(
        id=str(uuid.uuid4()),
        username=body.username,
        display_name=body.display_name,
        email=str(body.email) if body.email else None,
        password_hash=hash_password(body.password),
        role="USER",
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    await db.commit()
    logger.info("local_user_created", user_id=user.id, username=body.username)
    return user


@router.get("/users/{user_id}", response_model=UserWithAccessResponse)
async def get_user(
    user_id: str,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundError(f"User {user_id} not found")

    ca_result = await db.execute(
        select(UserCourseAccess).where(UserCourseAccess.user_id == user_id)
    )
    course_access = [
        {"course_id": ca.course_id, "role": ca.role} for ca in ca_result.scalars().all()
    ]

    return {
        **{
            c: getattr(user, c)
            for c in [
                "id",
                "username",
                "netid",
                "display_name",
                "email",
                "role",
                "created_at",
                "last_login",
            ]
        },
        "course_access": course_access,
    }


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    body: UserUpdate,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundError(f"User {user_id} not found")
    if body.username is not None:
        existing = await db.execute(
            select(User).where(User.username == body.username, User.id != user_id)
        )
        if existing.scalar_one_or_none():
            raise ConflictError(f"Username '{body.username}' is already taken")
        user.username = body.username
    if body.display_name is not None:
        user.display_name = body.display_name
    if body.email is not None:
        user.email = str(body.email)
    if body.password is not None:
        user.password_hash = hash_password(body.password)
    if body.role is not None:
        user.role = body.role
    return user


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: str,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundError(f"User {user_id} not found")
    if user.role == "ADMIN":
        raise ConflictError("Cannot delete an admin account")
    await db.delete(user)


# ---------------------------------------------------------------------------
# Course access management
# ---------------------------------------------------------------------------


@router.post("/users/{user_id}/course-access", status_code=204)
async def grant_course_access(
    user_id: str,
    body: CourseAccessGrant,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundError(f"User {user_id} not found")
    course = await db.get(Course, body.course_id)
    if not course:
        raise NotFoundError(f"Course {body.course_id} not found")

    result = await db.execute(
        select(UserCourseAccess).where(
            UserCourseAccess.user_id == user_id,
            UserCourseAccess.course_id == body.course_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.role = body.role  # update role if access already exists
    else:
        db.add(
            UserCourseAccess(user_id=user_id, course_id=body.course_id, role=body.role)
        )


@router.delete("/users/{user_id}/course-access/{course_id}", status_code=204)
async def revoke_course_access(
    user_id: str,
    course_id: int,
    _: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    result = await db.execute(
        select(UserCourseAccess).where(
            UserCourseAccess.user_id == user_id,
            UserCourseAccess.course_id == course_id,
        )
    )
    access = result.scalar_one_or_none()
    if not access:
        raise NotFoundError(
            f"No course access record for user {user_id} / course {course_id}"
        )
    await db.delete(access)

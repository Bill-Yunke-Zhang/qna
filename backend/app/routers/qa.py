from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.dependencies import (
    CourseMember,
    get_current_user,
    require_course_member,
    require_course_staff,
)
from ..database import get_db
from ..models.course import Course, UserCourseAccess
from ..models.user import User
from ..schemas.qa import (
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
    MyCourseResponse,
    PostAcceptPatch,
    PostCreate,
    QuestionCreate,
    QuestionDetail,
    QuestionSummary,
)
from ..services import qa_service

router = APIRouter(tags=["qa"])
logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Course picker — every course the current user has STUDENT/STAFF access to
# ---------------------------------------------------------------------------


@router.get("/courses/mine", response_model=list[MyCourseResponse])
async def get_my_courses(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict]:
    if user.role == "ADMIN":
        # ADMIN bypasses per-course grants everywhere else (see
        # require_course_member / require_course_staff) — mirror that here,
        # otherwise an admin with no explicit UserCourseAccess row gets an
        # empty course picker despite having staff access to everything.
        result = await db.execute(
            select(Course).order_by(Course.semester.desc(), Course.name)
        )
        return [
            {"id": c.id, "name": c.name, "semester": c.semester, "role": "STAFF"}
            for c in result.scalars().all()
        ]

    result = await db.execute(
        select(UserCourseAccess).where(UserCourseAccess.user_id == user.id)
    )
    access_rows = result.scalars().all()
    courses = []
    for access in access_rows:
        course = await qa_service.get_course(db, access.course_id)
        courses.append(
            {
                "id": course.id,
                "name": course.name,
                "semester": course.semester,
                "role": access.role,
            }
        )
    return courses


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


@router.get("/courses/{course_id}/categories", response_model=list[CategoryResponse])
async def list_categories(
    course_id: int,
    _: Annotated[CourseMember, Depends(require_course_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list:
    return await qa_service.list_categories(db, course_id)


@router.post(
    "/courses/{course_id}/categories", response_model=CategoryResponse, status_code=201
)
async def create_category(
    course_id: int,
    body: CategoryCreate,
    _: Annotated[CourseMember, Depends(require_course_staff)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    category = await qa_service.create_category(db, course_id, body)
    await db.commit()
    return category


@router.patch(
    "/courses/{course_id}/categories/{category_id}", response_model=CategoryResponse
)
async def update_category(
    course_id: int,
    category_id: int,
    body: CategoryUpdate,
    _: Annotated[CourseMember, Depends(require_course_staff)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await qa_service.update_category(db, course_id, category_id, body)


@router.delete("/courses/{course_id}/categories/{category_id}", status_code=204)
async def delete_category(
    course_id: int,
    category_id: int,
    _: Annotated[CourseMember, Depends(require_course_staff)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await qa_service.delete_category(db, course_id, category_id)


# ---------------------------------------------------------------------------
# Questions (threads)
# ---------------------------------------------------------------------------


@router.get("/courses/{course_id}/questions", response_model=list[QuestionSummary])
async def list_questions(
    course_id: int,
    _: Annotated[CourseMember, Depends(require_course_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
    category_id: int | None = Query(None),
    status: str | None = Query(None, pattern="^(OPEN|CLOSED)$"),
    q: str | None = Query(
        None, max_length=200, description="Keyword search over title/body"
    ),
) -> list:
    questions = await qa_service.list_questions(db, course_id, category_id, status, q)
    return [qa_service.serialize_question_summary(question) for question in questions]


@router.post(
    "/courses/{course_id}/questions", response_model=QuestionDetail, status_code=201
)
async def create_question(
    course_id: int,
    body: QuestionCreate,
    member: Annotated[CourseMember, Depends(require_course_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    question = await qa_service.create_question(db, course_id, member.user, body)
    await db.commit()
    return qa_service.serialize_question_detail(question)


@router.get(
    "/courses/{course_id}/questions/{question_id}", response_model=QuestionDetail
)
async def get_question(
    course_id: int,
    question_id: int,
    _: Annotated[CourseMember, Depends(require_course_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    question = await qa_service.get_question(db, course_id, question_id)
    return qa_service.serialize_question_detail(question)


# ---------------------------------------------------------------------------
# Posts (answers + follow-ups)
# ---------------------------------------------------------------------------


@router.post(
    "/courses/{course_id}/questions/{question_id}/posts",
    response_model=QuestionDetail,
    status_code=201,
)
async def create_post(
    course_id: int,
    question_id: int,
    body: PostCreate,
    member: Annotated[CourseMember, Depends(require_course_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    question = await qa_service.create_post(
        db, course_id, question_id, member.user, member.course_role, body
    )
    await db.commit()
    return qa_service.serialize_question_detail(question)


@router.patch(
    "/courses/{course_id}/questions/{question_id}/posts/{post_id}/accept",
    response_model=QuestionDetail,
)
async def set_post_accepted(
    course_id: int,
    question_id: int,
    post_id: int,
    body: PostAcceptPatch,
    member: Annotated[CourseMember, Depends(require_course_staff)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    question = await qa_service.set_post_accepted(
        db, course_id, question_id, post_id, member.user, body.is_accepted
    )
    await db.commit()
    return qa_service.serialize_question_detail(question)


# ---------------------------------------------------------------------------
# Closing / reopening a thread — staff-only, explicit action
# ---------------------------------------------------------------------------


@router.post(
    "/courses/{course_id}/questions/{question_id}/close", response_model=QuestionDetail
)
async def close_question(
    course_id: int,
    question_id: int,
    member: Annotated[CourseMember, Depends(require_course_staff)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    question = await qa_service.close_question(db, course_id, question_id, member.user)
    await db.commit()
    return qa_service.serialize_question_detail(question)


@router.post(
    "/courses/{course_id}/questions/{question_id}/reopen", response_model=QuestionDetail
)
async def reopen_question(
    course_id: int,
    question_id: int,
    member: Annotated[CourseMember, Depends(require_course_staff)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    question = await qa_service.reopen_question(db, course_id, question_id, member.user)
    await db.commit()
    return qa_service.serialize_question_detail(question)

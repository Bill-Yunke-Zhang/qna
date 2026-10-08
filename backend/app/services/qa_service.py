from __future__ import annotations

from datetime import datetime, timezone

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..common.exceptions import ConflictError, NotFoundError
from ..models.course import Course
from ..models.qa import Category, Post, Question, QuestionCategory
from ..models.user import User
from ..schemas.qa import CategoryCreate, CategoryUpdate, PostCreate, QuestionCreate

logger = structlog.get_logger()


def display_name(user: User) -> str:
    return user.display_name or user.username or user.netid or "Unknown"


def author_summary(user: User) -> dict:
    return {"id": user.id, "display_name": display_name(user)}


def serialize_post(post: Post) -> dict:
    return {
        "id": post.id,
        "question_id": post.question_id,
        "author": author_summary(post.author),
        "author_role": post.author_role,
        "kind": post.kind,
        "body": post.body,
        "is_accepted": post.is_accepted,
        "accepted_by": author_summary(post.accepted_by) if post.accepted_by else None,
        "accepted_at": post.accepted_at,
        "created_at": post.created_at,
    }


def serialize_question_summary(question: Question) -> dict:
    return {
        "id": question.id,
        "course_id": question.course_id,
        "title": question.title,
        "status": question.status,
        "author": author_summary(question.author),
        "categories": [link.category for link in question.category_links],
        "post_count": len(question.posts),
        "has_accepted_answer": any(p.is_accepted for p in question.posts),
        "created_at": question.created_at,
        "updated_at": question.updated_at,
    }


def serialize_question_detail(question: Question) -> dict:
    return {
        "id": question.id,
        "course_id": question.course_id,
        "title": question.title,
        "body": question.body,
        "status": question.status,
        "author": author_summary(question.author),
        "categories": [link.category for link in question.category_links],
        "posts": [serialize_post(p) for p in question.posts],
        "closed_by": author_summary(question.closed_by) if question.closed_by else None,
        "closed_at": question.closed_at,
        "created_at": question.created_at,
        "updated_at": question.updated_at,
    }


def _question_load_options():
    return (
        selectinload(Question.author),
        selectinload(Question.closed_by),
        selectinload(Question.category_links).selectinload(QuestionCategory.category),
        selectinload(Question.posts).selectinload(Post.author),
        selectinload(Question.posts).selectinload(Post.accepted_by),
    )


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


async def list_categories(db: AsyncSession, course_id: int) -> list[Category]:
    result = await db.execute(
        select(Category).where(Category.course_id == course_id).order_by(Category.name)
    )
    return list(result.scalars().all())


async def create_category(
    db: AsyncSession, course_id: int, data: CategoryCreate
) -> Category:
    existing = await db.execute(
        select(Category).where(
            Category.course_id == course_id, Category.name == data.name
        )
    )
    if existing.scalar_one_or_none():
        raise ConflictError(
            f"A category named '{data.name}' already exists in this course"
        )

    category = Category(
        course_id=course_id, name=data.name, description=data.description
    )
    db.add(category)
    await db.flush()
    await db.refresh(category)
    return category


async def update_category(
    db: AsyncSession, course_id: int, category_id: int, data: CategoryUpdate
) -> Category:
    result = await db.execute(
        select(Category).where(
            Category.id == category_id, Category.course_id == course_id
        )
    )
    category = result.scalar_one_or_none()
    if not category:
        raise NotFoundError(f"Category {category_id} not found")
    if data.name is not None:
        category.name = data.name
    if data.description is not None:
        category.description = data.description
    return category


async def delete_category(db: AsyncSession, course_id: int, category_id: int) -> None:
    result = await db.execute(
        select(Category).where(
            Category.id == category_id, Category.course_id == course_id
        )
    )
    category = result.scalar_one_or_none()
    if not category:
        raise NotFoundError(f"Category {category_id} not found")
    await db.delete(category)


# ---------------------------------------------------------------------------
# Questions (threads)
# ---------------------------------------------------------------------------


async def _get_question(db: AsyncSession, course_id: int, question_id: int) -> Question:
    # populate_existing() forces a refresh of already-loaded relationships.
    # Several call sites (create_post, set_post_accepted, close/reopen) fetch
    # the same Question twice within one request — once to check state,
    # once to build the response after a write — and without this, the
    # second fetch would return the identity-mapped object with its
    # `.posts` collection still cached from the first (now-stale) load.
    result = await db.execute(
        select(Question)
        .options(*_question_load_options())
        .where(Question.id == question_id, Question.course_id == course_id)
        .execution_options(populate_existing=True)
    )
    question = result.scalar_one_or_none()
    if not question:
        raise NotFoundError(f"Question {question_id} not found in course {course_id}")
    return question


async def list_questions(
    db: AsyncSession,
    course_id: int,
    category_id: int | None = None,
    status: str | None = None,
    q: str | None = None,
) -> list[Question]:
    query = (
        select(Question)
        .options(*_question_load_options())
        .where(Question.course_id == course_id)
        .order_by(Question.created_at.desc())
    )
    if category_id is not None:
        query = query.join(QuestionCategory).where(
            QuestionCategory.category_id == category_id
        )
    if status is not None:
        query = query.where(Question.status == status)
    if q:
        like = f"%{q}%"
        query = query.where(or_(Question.title.like(like), Question.body.like(like)))

    result = await db.execute(query)
    return list(result.unique().scalars().all())


async def get_question(db: AsyncSession, course_id: int, question_id: int) -> Question:
    return await _get_question(db, course_id, question_id)


async def create_question(
    db: AsyncSession, course_id: int, author: User, data: QuestionCreate
) -> Question:
    if data.category_ids:
        result = await db.execute(
            select(Category.id).where(
                Category.course_id == course_id, Category.id.in_(data.category_ids)
            )
        )
        found = set(result.scalars().all())
        missing = set(data.category_ids) - found
        if missing:
            raise NotFoundError(
                f"Unknown category id(s) for this course: {sorted(missing)}"
            )

    question = Question(
        course_id=course_id,
        author_user_id=author.id,
        title=data.title,
        body=data.body,
    )
    db.add(question)
    await db.flush()

    for category_id in data.category_ids:
        db.add(QuestionCategory(question_id=question.id, category_id=category_id))

    await db.flush()
    logger.info("question_created", question_id=question.id, course_id=course_id)
    return await _get_question(db, course_id, question.id)


# ---------------------------------------------------------------------------
# Posts (answers + follow-ups)
# ---------------------------------------------------------------------------


async def create_post(
    db: AsyncSession,
    course_id: int,
    question_id: int,
    author: User,
    author_role: str,
    data: PostCreate,
) -> Question:
    question = await _get_question(db, course_id, question_id)
    if question.status == "CLOSED":
        raise ConflictError("This question's thread is closed to new posts")

    post = Post(
        question_id=question.id,
        author_user_id=author.id,
        author_role=author_role,
        kind=data.kind,
        body=data.body,
    )
    db.add(post)
    await db.flush()
    logger.info(
        "post_created",
        question_id=question.id,
        post_id=post.id,
        kind=data.kind,
        author_role=author_role,
    )
    return await _get_question(db, course_id, question_id)


async def set_post_accepted(
    db: AsyncSession,
    course_id: int,
    question_id: int,
    post_id: int,
    staff_user: User,
    is_accepted: bool,
) -> Question:
    question = await _get_question(db, course_id, question_id)
    target = next((p for p in question.posts if p.id == post_id), None)
    if not target:
        raise NotFoundError(f"Post {post_id} not found in question {question_id}")
    if target.kind != "ANSWER":
        raise ConflictError("Only ANSWER posts can be marked accepted")

    if is_accepted:
        # At most one accepted post per question.
        for p in question.posts:
            if p.id != target.id and p.is_accepted:
                p.is_accepted = False
                p.accepted_by_user_id = None
                p.accepted_at = None
        target.is_accepted = True
        target.accepted_by_user_id = staff_user.id
        target.accepted_at = datetime.now(timezone.utc)
    else:
        target.is_accepted = False
        target.accepted_by_user_id = None
        target.accepted_at = None

    await db.flush()
    logger.info(
        "post_accept_toggled",
        question_id=question_id,
        post_id=post_id,
        is_accepted=is_accepted,
    )
    return await _get_question(db, course_id, question_id)


# ---------------------------------------------------------------------------
# Closing / reopening a thread
# ---------------------------------------------------------------------------


async def close_question(
    db: AsyncSession, course_id: int, question_id: int, staff_user: User
) -> Question:
    question = await _get_question(db, course_id, question_id)
    if question.status == "CLOSED":
        raise ConflictError("This question's thread is already closed")
    question.status = "CLOSED"
    question.closed_at = datetime.now(timezone.utc)
    question.closed_by_user_id = staff_user.id
    await db.flush()
    logger.info("question_closed", question_id=question_id, closed_by=staff_user.id)
    return await _get_question(db, course_id, question_id)


async def reopen_question(
    db: AsyncSession, course_id: int, question_id: int, staff_user: User
) -> Question:
    question = await _get_question(db, course_id, question_id)
    if question.status == "OPEN":
        raise ConflictError("This question's thread is already open")
    question.status = "OPEN"
    question.closed_at = None
    question.closed_by_user_id = None
    await db.flush()
    logger.info("question_reopened", question_id=question_id, reopened_by=staff_user.id)
    return await _get_question(db, course_id, question_id)


# ---------------------------------------------------------------------------
# Course lookup used by GET /courses (basic existence check)
# ---------------------------------------------------------------------------


async def get_course(db: AsyncSession, course_id: int) -> Course:
    course = await db.get(Course, course_id)
    if not course:
        raise NotFoundError(f"Course {course_id} not found")
    return course

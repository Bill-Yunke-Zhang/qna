from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .course import Course
    from .user import User


class Category(Base):
    """A staff-managed tag questions can be filed under (per course)."""

    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("course_id", "name", name="uq_category_course_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    course: Mapped[Course] = relationship("Course", back_populates="categories")
    question_links: Mapped[list[QuestionCategory]] = relationship(
        "QuestionCategory", back_populates="category", cascade="all, delete-orphan"
    )


class Question(Base):
    """The root of a Q&A thread: a student's question plus every reply."""

    __tablename__ = "questions"
    __table_args__ = (Index("ix_questions_course_status", "course_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    author_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("OPEN", "CLOSED", name="question_status"), default="OPEN", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )

    course: Mapped[Course] = relationship("Course", back_populates="questions")
    author: Mapped[User] = relationship(
        "User", back_populates="questions", foreign_keys=[author_user_id]
    )
    closed_by: Mapped[User | None] = relationship(
        "User", foreign_keys=[closed_by_user_id]
    )
    category_links: Mapped[list[QuestionCategory]] = relationship(
        "QuestionCategory", back_populates="question", cascade="all, delete-orphan"
    )
    posts: Mapped[list[Post]] = relationship(
        "Post",
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="Post.created_at",
    )


class QuestionCategory(Base):
    """Many-to-many: a question can carry more than one category tag."""

    __tablename__ = "question_categories"

    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True
    )

    question: Mapped[Question] = relationship(
        "Question", back_populates="category_links"
    )
    category: Mapped[Category] = relationship(
        "Category", back_populates="question_links"
    )


class Post(Base):
    """
    A single entry in a question's thread: either an ANSWER (attempts to
    resolve the question; can be marked accepted by staff regardless of who
    wrote it) or a FOLLOWUP (plain running discussion, never accepted).

    `author_role` snapshots the author's course role (STUDENT/STAFF) at the
    moment of posting, so a "staff answer" badge never retroactively changes
    if that person's course access is later revoked or altered.

    AI posts (`author_role = 'AI'`, see docs/design-rag.md §4.1) have no
    author user, carry the citations they were posted with, and are the only
    posts staff can retract. The CHECK constraints below are mirrored by hand
    in migration 002_rag; Alembic autogenerate doesn't detect them.
    """

    __tablename__ = "posts"
    __table_args__ = (
        Index("ix_posts_question_created", "question_id", "created_at"),
        # Also keeps admin delete_user failing for users who have posts, as it
        # did when author_user_id was NOT NULL: the ORM nulls the author, and
        # this rejects a non-AI post without one.
        CheckConstraint(
            "(author_role = 'AI') = (author_user_id IS NULL)", name="ck_posts_ai_author"
        ),
        CheckConstraint(
            "author_role = 'AI' OR citations IS NULL", name="ck_posts_citations_ai_only"
        ),
        CheckConstraint(
            "author_role = 'AI' OR retracted_at IS NULL",
            name="ck_posts_retract_ai_only",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    # Never give this FK an ON DELETE action: MySQL rejects a CHECK on a column
    # whose FK has one, and ck_posts_ai_author depends on it.
    author_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    author_role: Mapped[str] = mapped_column(
        Enum("STUDENT", "STAFF", "AI", name="post_author_role"), nullable=False
    )
    kind: Mapped[str] = mapped_column(
        Enum("ANSWER", "FOLLOWUP", name="post_kind"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_accepted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    accepted_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # none_as_null: without it SQLAlchemy writes Python None as the JSON value
    # `null`, which isn't SQL NULL, and ck_posts_citations_ai_only would reject
    # every human post that sets citations=None. Shape is validated by the
    # Pydantic Citation model on the one write path.
    citations: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    retracted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    retracted_by_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "users.id", ondelete="SET NULL", name="fk_posts_retracted_by_user_id"
        ),
        nullable=True,
    )

    question: Mapped[Question] = relationship("Question", back_populates="posts")
    author: Mapped[User | None] = relationship(
        "User", back_populates="posts", foreign_keys=[author_user_id]
    )
    accepted_by: Mapped[User | None] = relationship(
        "User", foreign_keys=[accepted_by_user_id]
    )
    retracted_by: Mapped[User | None] = relationship(
        "User", foreign_keys=[retracted_by_user_id]
    )

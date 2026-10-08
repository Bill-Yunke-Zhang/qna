from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .course import UserCourseAccess
    from .qa import Post, Question


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    netid: Mapped[str | None] = mapped_column(
        String(50), unique=True, index=True, nullable=True
    )
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )
    username: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(
        Enum("ADMIN", "USER", name="user_role"), default="USER"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    course_access: Mapped[list[UserCourseAccess]] = relationship(
        "UserCourseAccess", back_populates="user", cascade="all, delete-orphan"
    )
    questions: Mapped[list[Question]] = relationship(
        "Question", back_populates="author", foreign_keys="Question.author_user_id"
    )
    posts: Mapped[list[Post]] = relationship(
        "Post", back_populates="author", foreign_keys="Post.author_user_id"
    )

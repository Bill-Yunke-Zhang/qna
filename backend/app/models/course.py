from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

if TYPE_CHECKING:
    from .qa import Category, Question
    from .user import User


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    semester: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    roster: Mapped[list[CourseRoster]] = relationship(
        "CourseRoster", back_populates="course", cascade="all, delete-orphan"
    )
    user_access: Mapped[list[UserCourseAccess]] = relationship(
        "UserCourseAccess", back_populates="course", cascade="all, delete-orphan"
    )
    categories: Mapped[list[Category]] = relationship(
        "Category", back_populates="course", cascade="all, delete-orphan"
    )
    questions: Mapped[list[Question]] = relationship(
        "Question", back_populates="course", cascade="all, delete-orphan"
    )


class CourseRoster(Base):
    __tablename__ = "course_rosters"

    __table_args__ = (
        UniqueConstraint("course_id", "netid", name="uq_roster_course_netid"),
        Index("ix_roster_course_netid", "course_id", "netid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    netid: Mapped[str] = mapped_column(String(50), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    course: Mapped[Course] = relationship("Course", back_populates="roster")


class UserCourseAccess(Base):
    __tablename__ = "user_course_access"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(
        Enum("STUDENT", "STAFF", name="course_role"), nullable=False
    )

    user: Mapped[User] = relationship("User", back_populates="course_access")
    course: Mapped[Course] = relationship("Course", back_populates="user_access")

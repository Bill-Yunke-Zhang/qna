from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
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

# index_syncs.source_key for a course's historical Q&A threads. Resources use
# Resource.source_key ("resource:{id}").
HISTORICAL_QA_SOURCE_KEY = "historical_qa"


class Resource(Base):
    """
    Course material staff register for RAG ingestion (docs/design-rag.md §7.1):
    a syllabus page, a schedule page, or a repository, fetched from a URL or
    uploaded. Uploads store no file; `link_base_url` is where citations point
    (§3.2). Chunks live only in ChromaDB; what was last ingested, per profile,
    is in `IndexSync`.
    """

    __tablename__ = "resources"
    __table_args__ = (
        CheckConstraint(
            "(origin = 'URL') = (fetch_url IS NOT NULL)", name="ck_resources_fetch_url"
        ),
        CheckConstraint(
            "origin = 'URL' OR link_base_url IS NOT NULL",
            name="ck_resources_upload_link_base",
        ),
        CheckConstraint(
            "type = 'REPO' OR repo_branch IS NULL", name="ck_resources_branch_repo_only"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(
        Enum("SYLLABUS", "SCHEDULE", "REPO", name="resource_type"), nullable=False
    )
    # Staff-chosen; the first part of every citation label from this resource.
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    origin: Mapped[str] = mapped_column(
        Enum("URL", "UPLOAD", name="resource_origin"), nullable=False
    )
    # Page URL or repo clone URL. Never contains a token (§8).
    fetch_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    link_base_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    repo_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # SET NULL so deleting the staff user who registered it keeps the resource.
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    course: Mapped[Course] = relationship("Course", back_populates="resources")
    created_by: Mapped[User | None] = relationship("User")
    index_syncs: Mapped[list[IndexSync]] = relationship(
        "IndexSync",
        back_populates="resource",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def source_key(self) -> str:
        return f"resource:{self.id}"


class IndexSync(Base):
    """
    The result of the last ingestion of one source under one profile
    (docs/design-rag.md §7.1, §7.3). `source_key` is `resource:{id}` or
    `historical_qa`, which is not a `Resource` row. Search only sees chunks
    whose `sync_id` is a row's `current_sync_id`, so switching it is what
    makes a re-sync visible. There is no "in progress" state.
    """

    __tablename__ = "index_syncs"
    __table_args__ = (
        UniqueConstraint(
            "course_id", "profile", "source_key", name="uq_index_sync_source"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    profile: Mapped[str] = mapped_column(String(64), nullable=False)
    source_key: Mapped[str] = mapped_column(String(64), nullable=False)
    # NULL for historical_qa. No CHECK pairing it with source_key: MySQL rejects
    # a CHECK on a column whose FK has a referential action (the cascade).
    resource_id: Mapped[int | None] = mapped_column(
        ForeignKey("resources.id", ondelete="CASCADE"), nullable=True
    )
    current_sync_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # Hash of the fetched documents (commit SHA for repos). NULL forces the
    # next sync to re-embed; §4.6's un-accept cleanup relies on that.
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Chunks longer than the embedding model's input limit (silently truncated).
    truncated_chunk_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    course: Mapped[Course] = relationship("Course", back_populates="index_syncs")
    resource: Mapped[Resource | None] = relationship(
        "Resource", back_populates="index_syncs"
    )

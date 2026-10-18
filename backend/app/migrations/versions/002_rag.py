"""RAG: AI posts, citations, retraction, resources and index syncs

See docs/design-rag.md §4.1 (posts), §4.7 (retraction) and §7.1 (resources,
index_syncs). The CHECK constraints are written by hand: Alembic autogenerate
doesn't detect them. MySQL enforces CHECK from 8.0.16 (Compose runs 8.0).

Revision ID: 002
Revises: 001
Create Date: 2026-10-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_AUTHOR_ROLE = sa.Enum("STUDENT", "STAFF", name="post_author_role")
_NEW_AUTHOR_ROLE = sa.Enum("STUDENT", "STAFF", "AI", name="post_author_role")


def upgrade() -> None:
    # ── posts ────────────────────────────────────────────────────────────────
    op.alter_column(
        "posts",
        "author_role",
        existing_type=_OLD_AUTHOR_ROLE,
        type_=_NEW_AUTHOR_ROLE,
        existing_nullable=False,
    )
    # The FK keeps no ON DELETE action: MySQL rejects a CHECK on a column whose
    # FK has one, and ck_posts_ai_author depends on that.
    op.alter_column(
        "posts", "author_user_id", existing_type=sa.String(36), nullable=True
    )
    op.add_column(
        "posts", sa.Column("citations", sa.JSON(none_as_null=True), nullable=True)
    )
    op.add_column("posts", sa.Column("retracted_at", sa.DateTime, nullable=True))
    op.add_column(
        "posts", sa.Column("retracted_by_user_id", sa.String(36), nullable=True)
    )
    op.create_foreign_key(
        "fk_posts_retracted_by_user_id",
        "posts",
        "users",
        ["retracted_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_posts_ai_author", "posts", "(author_role = 'AI') = (author_user_id IS NULL)"
    )
    op.create_check_constraint(
        "ck_posts_citations_ai_only", "posts", "author_role = 'AI' OR citations IS NULL"
    )
    op.create_check_constraint(
        "ck_posts_retract_ai_only",
        "posts",
        "author_role = 'AI' OR retracted_at IS NULL",
    )

    # ── resources ────────────────────────────────────────────────────────────
    op.create_table(
        "resources",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "course_id",
            sa.Integer,
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "type",
            sa.Enum("SYLLABUS", "SCHEDULE", "REPO", name="resource_type"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column(
            "origin", sa.Enum("URL", "UPLOAD", name="resource_origin"), nullable=False
        ),
        sa.Column("fetch_url", sa.String(2048), nullable=True),
        sa.Column("link_base_url", sa.String(2048), nullable=True),
        sa.Column("repo_branch", sa.String(255), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime, nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "(origin = 'URL') = (fetch_url IS NOT NULL)", name="ck_resources_fetch_url"
        ),
        sa.CheckConstraint(
            "origin = 'URL' OR link_base_url IS NOT NULL",
            name="ck_resources_upload_link_base",
        ),
        sa.CheckConstraint(
            "type = 'REPO' OR repo_branch IS NULL",
            name="ck_resources_branch_repo_only",
        ),
    )

    # ── index_syncs ──────────────────────────────────────────────────────────
    op.create_table(
        "index_syncs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "course_id",
            sa.Integer,
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("profile", sa.String(64), nullable=False),
        sa.Column("source_key", sa.String(64), nullable=False),
        sa.Column(
            "resource_id",
            sa.Integer,
            sa.ForeignKey("resources.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("current_sync_id", sa.String(36), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("commit_sha", sa.String(40), nullable=True),
        sa.Column("chunk_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "truncated_chunk_count", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column("last_synced_at", sa.DateTime, nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("last_error_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint(
            "course_id", "profile", "source_key", name="uq_index_sync_source"
        ),
    )


def downgrade() -> None:
    # author_user_id can't go back to NOT NULL while authorless rows exist.
    ai_posts = (
        op.get_bind()
        .execute(sa.text("SELECT COUNT(*) FROM posts WHERE author_role = 'AI'"))
        .scalar()
    )
    if ai_posts:
        raise RuntimeError(
            f"Refusing to downgrade: {ai_posts} AI post(s) exist. "
            "Delete them by hand first (docs/design-rag.md §12)."
        )

    op.drop_table("index_syncs")
    op.drop_table("resources")

    op.drop_constraint("ck_posts_retract_ai_only", "posts", type_="check")
    op.drop_constraint("ck_posts_citations_ai_only", "posts", type_="check")
    op.drop_constraint("ck_posts_ai_author", "posts", type_="check")
    op.drop_constraint("fk_posts_retracted_by_user_id", "posts", type_="foreignkey")
    op.drop_column("posts", "retracted_by_user_id")
    op.drop_column("posts", "retracted_at")
    op.drop_column("posts", "citations")
    op.alter_column(
        "posts", "author_user_id", existing_type=sa.String(36), nullable=False
    )
    op.alter_column(
        "posts",
        "author_role",
        existing_type=_NEW_AUTHOR_ROLE,
        type_=_OLD_AUTHOR_ROLE,
        existing_nullable=False,
    )

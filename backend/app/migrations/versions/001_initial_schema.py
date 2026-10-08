"""Initial schema — all tables

Revision ID: 001
Revises:
Create Date: 2026-07-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("netid", sa.String(50), unique=True, index=True, nullable=True),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("email", sa.String(255), unique=True, index=True, nullable=True),
        sa.Column("username", sa.String(50), unique=True, nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column(
            "role",
            sa.Enum("ADMIN", "USER", name="user_role"),
            nullable=False,
            server_default="USER",
        ),
        sa.Column(
            "created_at", sa.DateTime, nullable=False, server_default=sa.func.now()
        ),
        sa.Column("last_login", sa.DateTime, nullable=True),
    )

    op.create_table(
        "courses",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("semester", sa.String(50), nullable=False),
        sa.Column(
            "created_at", sa.DateTime, nullable=False, server_default=sa.func.now()
        ),
    )

    op.create_table(
        "course_rosters",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "course_id",
            sa.Integer,
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("netid", sa.String(50), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="1"),
        sa.Column(
            "imported_at", sa.DateTime, nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("course_id", "netid", name="uq_roster_course_netid"),
    )
    op.create_index("ix_roster_course_netid", "course_rosters", ["course_id", "netid"])

    op.create_table(
        "user_course_access",
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "course_id",
            sa.Integer,
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "role", sa.Enum("STUDENT", "STAFF", name="course_role"), nullable=False
        ),
    )

    op.create_table(
        "categories",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "course_id",
            sa.Integer,
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column(
            "created_at", sa.DateTime, nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("course_id", "name", name="uq_category_course_name"),
    )

    op.create_table(
        "questions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "course_id",
            sa.Integer,
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column(
            "status",
            sa.Enum("OPEN", "CLOSED", name="question_status"),
            nullable=False,
            server_default="OPEN",
        ),
        sa.Column(
            "created_at", sa.DateTime, nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.Column("closed_at", sa.DateTime, nullable=True),
        sa.Column(
            "closed_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True
        ),
    )
    op.create_index("ix_questions_course_status", "questions", ["course_id", "status"])

    op.create_table(
        "question_categories",
        sa.Column(
            "question_id",
            sa.Integer,
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "category_id",
            sa.Integer,
            sa.ForeignKey("categories.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "posts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "question_id",
            sa.Integer,
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column(
            "author_role",
            sa.Enum("STUDENT", "STAFF", name="post_author_role"),
            nullable=False,
        ),
        sa.Column(
            "kind", sa.Enum("ANSWER", "FOLLOWUP", name="post_kind"), nullable=False
        ),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("is_accepted", sa.Boolean, nullable=False, server_default="0"),
        sa.Column(
            "accepted_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("accepted_at", sa.DateTime, nullable=True),
        sa.Column(
            "created_at", sa.DateTime, nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_posts_question_created", "posts", ["question_id", "created_at"])


def downgrade() -> None:
    op.drop_table("posts")
    op.drop_table("question_categories")
    op.drop_table("questions")
    op.drop_table("categories")
    op.drop_table("user_course_access")
    op.drop_table("course_rosters")
    op.drop_table("courses")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS post_kind")
    op.execute("DROP TYPE IF EXISTS post_author_role")
    op.execute("DROP TYPE IF EXISTS question_status")
    op.execute("DROP TYPE IF EXISTS course_role")
    op.execute("DROP TYPE IF EXISTS user_role")

"""
Unit tests for the RAG schema details that are easy to lose in a refactor
(docs/design-rag.md §4.1). The constraints themselves are enforced by MySQL
and created by migration 002_rag; these only check the ORM side matches.
"""
from __future__ import annotations


def test_citations_store_python_none_as_sql_null():
    # Without none_as_null, citations=None is written as the JSON value
    # `null`, and ck_posts_citations_ai_only rejects every human post.
    from app.models import Post

    assert Post.__table__.c.citations.type.none_as_null is True


def test_post_check_constraints_are_declared():
    from sqlalchemy import CheckConstraint

    from app.models import Post

    names = {
        c.name for c in Post.__table__.constraints if isinstance(c, CheckConstraint)
    }

    assert {
        "ck_posts_ai_author",
        "ck_posts_citations_ai_only",
        "ck_posts_retract_ai_only",
    } <= names


def test_post_author_fk_has_no_delete_action():
    # MySQL rejects a CHECK on a column whose FK has a referential action, and
    # ck_posts_ai_author covers author_user_id.
    from app.models import Post

    (fk,) = Post.__table__.c.author_user_id.foreign_keys

    assert fk.ondelete is None


def test_ai_is_a_post_author_role():
    from app.models import Post

    assert "AI" in Post.__table__.c.author_role.type.enums


def test_index_sync_source_is_unique_per_course_and_profile():
    from sqlalchemy import UniqueConstraint

    from app.models import IndexSync

    uniques = [
        tuple(col.name for col in c.columns)
        for c in IndexSync.__table__.constraints
        if isinstance(c, UniqueConstraint)
    ]

    assert ("course_id", "profile", "source_key") in uniques

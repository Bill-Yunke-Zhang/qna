"""
Unit tests for AI posts in the thread model (docs/design-rag.md §4): the
citation rules, serializing posts with no author, hiding retracted posts
from students, and retracting. MySQL is replaced by in-memory objects; the
integration tests cover the real database.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace as NS

import pytest
from pydantic import ValidationError

from app.common.exceptions import ConflictError, InvalidInputError
from app.schemas.qa import AICitations, Citation, QuestionDetail, QuestionSummary
from app.services import ai_answer_service, qa_service

NOW = datetime(2026, 10, 21, 12, 0)
STAFF = NS(id="staff-1", display_name="Pat Staff", username=None, netid=None)
STUDENT = NS(id="stu-1", display_name="Sam Student", username=None, netid=None)


def syllabus(rank=1, **kw):
    return {
        "rank": rank,
        "label": "Syllabus › Grading",
        "resource_type": "syllabus",
        "citation_url": "https://cs.example.edu/syllabus.html#:~:text=Projects",
        "similarity_score": 0.71,
        **kw,
    }


def past_question(rank=2, **kw):
    return {
        "rank": rank,
        "label": "Past question › When is P1 due?",
        "resource_type": "historical_qa",
        "question_id": 12,
        "similarity_score": 0.66,
        **kw,
    }


# ── Citations ────────────────────────────────────────────────────────────────


def test_valid_citations():
    checked = AICitations(citations=[syllabus(), past_question()])
    assert [c.rank for c in checked.citations] == [1, 2]


@pytest.mark.parametrize(
    "citation",
    [
        syllabus(citation_url=None),  # a document type needs a link
        syllabus(question_id=3),  # ...and no question_id
        past_question(question_id=None),  # Q&A needs its thread
        past_question(citation_url="https://x"),  # ...and no stored link
        syllabus(resource_type="slides"),  # not a §3.1 type
        syllabus(rank=0),
        syllabus(extra="field"),
    ],
)
def test_invalid_citation(citation):
    with pytest.raises(ValidationError):
        Citation.model_validate(citation)


@pytest.mark.parametrize("ranks", [[], [1, 2, 3, 3], [2], [1, 1], [2, 1]], ids=str)
def test_citation_list_rules(ranks):
    # 1–3 citations, ranked 1..n best first.
    with pytest.raises(ValidationError):
        AICitations(citations=[syllabus(rank=r) for r in ranks])


# ── Serializing ──────────────────────────────────────────────────────────────


def post(post_id, role="AI", author=None, retracted=False, accepted=False, **kw):
    return NS(
        id=post_id,
        question_id=5,
        author=author,
        author_role=role,
        kind="ANSWER",
        body=f"post {post_id}",
        is_accepted=accepted,
        accepted_by=STAFF if accepted else None,
        accepted_at=NOW if accepted else None,
        created_at=NOW,
        citations=[syllabus()] if role == "AI" else None,
        retracted_at=NOW if retracted else None,
        retracted_by=STAFF if retracted else None,
        **kw,
    )


def question(*posts):
    return NS(
        id=5,
        course_id=1,
        title="When is P1 due?",
        body="Can't find it.",
        status="OPEN",
        author=STUDENT,
        category_links=[],
        posts=list(posts),
        closed_by=None,
        closed_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def test_ai_post_serializes_with_no_author_and_its_citations():
    detail = qa_service.serialize_question_detail(question(post(1)), "STUDENT")
    (p,) = QuestionDetail.model_validate(detail).posts
    assert p.author is None and p.author_role == "AI"
    assert p.citations[0].label == "Syllabus › Grading"
    assert p.retracted_at is None


def test_students_never_see_retracted_posts_staff_do():
    q = question(post(1, retracted=True), post(2, role="STAFF", author=STAFF))
    student = qa_service.serialize_question_detail(q, "STUDENT")
    staff = qa_service.serialize_question_detail(q, "STAFF")
    assert [p["id"] for p in student["posts"]] == [2]
    assert [p["id"] for p in staff["posts"]] == [1, 2]
    retracted = QuestionDetail.model_validate(staff).posts[0]
    assert retracted.retracted_by.display_name == "Pat Staff"


def test_retracted_by_a_deleted_user_is_still_retracted():
    p = post(1, retracted=True)
    p.retracted_by = None  # ON DELETE SET NULL
    out = qa_service.serialize_post(p)
    assert out["retracted_at"] == NOW and out["retracted_by"] is None


@pytest.mark.parametrize(
    ("posts", "count", "has_ai"),
    [
        ([], 0, False),
        ([post(1)], 1, True),
        ([post(1, retracted=True)], 0, False),
        ([post(1, retracted=True), post(2, role="STUDENT", author=STUDENT)], 1, False),
    ],
)
def test_summary_counts_ignore_retracted_posts(posts, count, has_ai):
    summary = QuestionSummary.model_validate(
        qa_service.serialize_question_summary(question(*posts))
    )
    assert (summary.post_count, summary.has_ai_answer) == (count, has_ai)


# ── Retracting and accepting ─────────────────────────────────────────────────


class FakeDB:
    def __init__(self, question=None):
        self.added = []
        self.question = question
        self.flushes = 0

    async def flush(self):
        self.flushes += 1
        for i, obj in enumerate(self.added, start=100):
            obj.id = getattr(obj, "id", None) or i

    async def execute(self, statement):
        pass

    async def get(self, model, key):
        return self.question

    def add(self, obj):
        self.added.append(obj)


@pytest.fixture
def thread(monkeypatch):
    q = question()

    async def get_question(db, course_id, question_id):
        return q

    monkeypatch.setattr(qa_service, "_get_question", get_question)
    return q


def editable(post_id, role="AI", accepted=False):
    p = post(post_id, role=role, author=None if role == "AI" else STAFF)
    p.is_accepted = accepted
    p.accepted_by_user_id = "staff-1" if accepted else None
    p.retracted_by_user_id = None
    return p


async def test_retract_hides_and_unaccepts_and_is_idempotent(thread):
    thread.posts = [editable(1, accepted=True)]
    db = FakeDB()
    await qa_service.retract_ai_post(db, 1, 5, 1, NS(id="staff-2"))
    p = thread.posts[0]
    assert p.retracted_at is not None and p.retracted_by_user_id == "staff-2"
    assert p.is_accepted is False and p.accepted_by_user_id is None

    first = p.retracted_at
    await qa_service.retract_ai_post(db, 1, 5, 1, NS(id="staff-3"))
    assert (p.retracted_at, p.retracted_by_user_id) == (first, "staff-2")
    assert db.flushes == 1


async def test_only_ai_posts_can_be_retracted(thread):
    thread.posts = [editable(1, role="STAFF")]
    with pytest.raises(InvalidInputError):
        await qa_service.retract_ai_post(FakeDB(), 1, 5, 1, NS(id="staff-2"))


async def test_retracted_post_cannot_be_accepted(thread):
    thread.posts = [editable(1)]
    await qa_service.retract_ai_post(FakeDB(), 1, 5, 1, NS(id="staff-2"))
    with pytest.raises(ConflictError, match="retracted"):
        await qa_service.set_post_accepted(FakeDB(), 1, 5, 1, NS(id="s"), True)
    # Un-accepting it is harmless.
    await qa_service.set_post_accepted(FakeDB(), 1, 5, 1, NS(id="s"), False)


async def test_ai_post_is_accepted_through_the_existing_flow(thread):
    thread.posts = [editable(1)]
    _, unaccepted = await qa_service.set_post_accepted(
        FakeDB(), 1, 5, 1, NS(id="staff-1"), True
    )
    assert thread.posts[0].is_accepted is True and unaccepted is False


# ── Creating ─────────────────────────────────────────────────────────────────


async def test_create_ai_post():
    db = FakeDB(NS(id=5, status="OPEN"))
    p = await ai_answer_service.create_ai_post(
        db, 5, "P1 is due Sep 15.", [syllabus(), Citation(**past_question())]
    )
    assert (p.author_user_id, p.author_role, p.kind) == (None, "AI", "ANSWER")
    # Stored without None fields, so the JSON matches the type's shape.
    assert "question_id" not in p.citations[0]
    assert p.citations[1]["question_id"] == 12 and "citation_url" not in p.citations[1]


@pytest.mark.parametrize(
    ("q", "answer", "citations", "error"),
    [
        (None, "x", [syllabus()], "not found"),
        (NS(id=5, status="CLOSED"), "x", [syllabus()], "closed"),
        (NS(id=5, status="OPEN"), "  ", [syllabus()], "empty"),
        (NS(id=5, status="OPEN"), "x", [], "Invalid AI citations"),
        (NS(id=5, status="OPEN"), "x", [syllabus(citation_url=None)], "Invalid"),
    ],
)
async def test_create_ai_post_refuses(q, answer, citations, error):
    with pytest.raises(Exception, match=error):
        await ai_answer_service.create_ai_post(FakeDB(q), 5, answer, citations)

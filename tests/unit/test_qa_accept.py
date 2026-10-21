"""
Unit tests for when `set_post_accepted` reports that an accepted answer lost
its acceptance (docs/design-rag.md §4.6). That report clears the course's
historical Q&A `content_hash` and makes the router drop the thread's chunks,
so it must be exact: a false positive drops a thread that is still accepted.
"""

from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from app.services import qa_service


class FakeDB:
    def __init__(self):
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)

    async def flush(self):
        pass


def post(post_id, accepted):
    return NS(
        id=post_id,
        kind="ANSWER",
        is_accepted=accepted,
        accepted_by_user_id="staff" if accepted else None,
        accepted_at=None,
        retracted_at=None,
    )


@pytest.mark.parametrize(
    ("accepted", "target", "is_accepted", "expected"),
    [
        ((), 1, True, False),  # first accept in the thread
        ((1,), 1, True, False),  # accepting the already-accepted answer
        ((1,), 2, True, True),  # switching to another answer
        ((1,), 1, False, True),  # un-accepting the accepted answer
        ((), 1, False, False),  # un-accepting when nothing is accepted
        ((2,), 1, False, False),  # un-accepting a non-accepted answer (review of !17)
    ],
)
async def test_unaccepted_only_when_an_accepted_answer_loses_it(
    monkeypatch, accepted, target, is_accepted, expected
):
    question = NS(posts=[post(1, 1 in accepted), post(2, 2 in accepted)])

    async def get_question(db, course_id, question_id):
        return question

    monkeypatch.setattr(qa_service, "_get_question", get_question)
    db = FakeDB()
    _, unaccepted = await qa_service.set_post_accepted(
        db, 1, 5, target, NS(id="staff"), is_accepted
    )

    assert unaccepted is expected
    # The content_hash UPDATE runs exactly when cleanup is reported.
    assert bool(db.statements) is expected
    still = {p.id for p in question.posts if p.is_accepted}
    if is_accepted:
        assert still == {target}
    else:
        assert still == set(accepted) - {target}

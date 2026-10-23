"""
Unit tests for live answering (docs/design-rag.md §5.4): when a new question
gets an AI answer, and every way it gets none. The pipeline and the database
are replaced with fakes; what's tested is the task's own rules.
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace as NS

import pytest

from app.schemas.qa import AICitations
from app.services import ai_answer_service as svc
from app.services.rag import clients, compare, pipeline
from app.services.rag.pipeline import RagResult, RetrievedChunk

COURSE, QUESTION = 3, 41
TEXT = "When is P1 due?\n\nI can't find the deadline."


def chunk(resource_type="syllabus", score=0.7, **meta):
    defaults = {
        "label": f"Syllabus › {score}",
        "citation_url": f"https://cs.example.edu/syllabus.html#:~:text={score}",
    }
    if resource_type == "historical_qa":
        defaults = {"label": "Past question › P1 deadline", "question_id": 12}
    return RetrievedChunk(
        resource_type=resource_type,
        source_url="https://cs.example.edu/syllabus.html",
        similarity_score=score,
        text="…",
        metadata={**defaults, **meta},
    )


MATCH = RagResult(matched=True, chunks=[chunk()], answer="P1 is due Sep 15.")


@pytest.fixture
def env(monkeypatch):
    """Fakes for the pipeline, the DB reads and the posting; returns the calls."""
    state = NS(result=MATCH, run_calls=[], posted=[], text=TEXT, error=None)

    async def run(course_id, text, config, *, caller, deadline):
        state.run_calls.append(
            NS(
                course_id=course_id,
                text=text,
                config=config,
                caller=caller,
                deadline=deadline,
            )
        )
        if state.error:
            raise state.error
        return state.result

    async def question_text(question_id):
        return state.text

    async def post(question_id, answer, citations):
        state.posted.append((question_id, answer, citations))

    monkeypatch.setattr(pipeline, "run", run)
    monkeypatch.setattr(svc, "_question_text", question_text)
    monkeypatch.setattr(svc, "_post_if_still_open", post)
    monkeypatch.setattr(compare, "active_or_ended_within", lambda s: False)
    monkeypatch.setattr(svc, "_live_waiting", 0)
    monkeypatch.setattr(svc, "_last_config_warning", {})
    monkeypatch.setattr(svc.settings, "RAG_LIVE_ENABLED", True)
    return state


# ── Posting ──────────────────────────────────────────────────────────────────


async def test_a_match_is_posted_with_its_citations(env):
    await svc.answer_question(COURSE, QUESTION)
    ((qid, answer, citations),) = env.posted
    assert (qid, answer) == (QUESTION, "P1 is due Sep 15.")
    assert citations[0]["rank"] == 1 and citations[0]["citation_url"]
    AICitations.model_validate({"citations": citations})  # what create_ai_post checks


async def test_runs_the_live_configuration_on_title_and_body(env, monkeypatch):
    monkeypatch.setattr(svc.settings, "RAG_LIVE_THRESHOLD", 0.42)
    before = time.monotonic()
    await svc.answer_question(COURSE, QUESTION)
    (call,) = env.run_calls
    assert (call.course_id, call.text, call.caller) == (COURSE, TEXT, "LIVE")
    assert call.config.similarity_threshold == 0.42
    assert call.config.ingestion_profile == svc.settings.RAG_LIVE_PROFILE
    assert call.config.generation_model == svc.settings.RAG_LIVE_MODEL
    assert call.config.system_prompt == svc.settings.RAG_LIVE_SYSTEM_PROMPT
    budget = call.deadline - before
    assert (
        svc.settings.RAG_LIVE_DEADLINE_S - 1
        < budget
        <= svc.settings.RAG_LIVE_DEADLINE_S + 1
    )


# ── Nothing is posted ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "result",
    [
        RagResult(matched=False, chunks=[], answer=None),
        RagResult(matched=True, chunks=[chunk()], answer="P1 is due", truncated=True),
        RagResult(
            matched=True, chunks=[chunk()], answer="I don't have enough information."
        ),
        RagResult(matched=True, chunks=[chunk()], answer=""),
        RagResult(matched=True, chunks=[chunk(citation_url=None)], answer="P1 is due."),
    ],
    ids=["no-match", "truncated", "refusal", "empty", "no-citable-chunk"],
)
async def test_nothing_is_posted(env, result):
    env.result = result
    await svc.answer_question(COURSE, QUESTION)
    assert env.posted == []


async def test_disabled_does_nothing(env, monkeypatch):
    monkeypatch.setattr(svc.settings, "RAG_LIVE_ENABLED", False)
    await svc.answer_question(COURSE, QUESTION)
    assert env.run_calls == [] and env.posted == []


async def test_pauses_during_compare_traffic(env, monkeypatch):
    monkeypatch.setattr(compare, "active_or_ended_within", lambda s: True)
    await svc.answer_question(COURSE, QUESTION)
    assert env.run_calls == [] and env.posted == []


async def test_deleted_question_isnt_run(env):
    env.text = None
    await svc.answer_question(COURSE, QUESTION)
    assert env.run_calls == []


@pytest.mark.parametrize(
    "error",
    [
        pipeline.ProfileNotIngested("course_3__sliding-window"),
        pipeline.ModelNotAvailable("qwen2.5:1.5b"),
        clients.ServiceUnavailable("ollama", "down"),
        NotImplementedError("the RAG pipeline isn't built yet"),
        RuntimeError("anything else"),
    ],
    ids=lambda e: type(e).__name__,
)
async def test_failures_post_nothing_and_never_raise(env, error):
    env.error = error
    await svc.answer_question(COURSE, QUESTION)  # must not raise
    assert env.posted == []
    assert svc._live_waiting == 0


async def test_a_posting_failure_is_swallowed(env, monkeypatch):
    async def broken(*args):
        raise RuntimeError("db gone")

    monkeypatch.setattr(svc, "_post_if_still_open", broken)
    await svc.answer_question(COURSE, QUESTION)  # must not raise


async def test_config_problems_warn_once_per_course(env, monkeypatch):
    warned = []
    monkeypatch.setattr(
        svc.logger,
        "warning",
        lambda event, **kw: warned.append((event, kw["course_id"])),
    )
    env.error = pipeline.ProfileNotIngested("not ingested")
    for course in (COURSE, COURSE, COURSE, COURSE + 1):
        await svc.answer_question(course, QUESTION)
    assert warned == [
        ("ai_answers_off_for_course", COURSE),
        ("ai_answers_off_for_course", COURSE + 1),
    ]


async def test_backlog_cap(env, monkeypatch):
    # Tasks wait inside run(); past RAG_LIVE_MAX_WAITING a new one is skipped.
    monkeypatch.setattr(svc.settings, "RAG_LIVE_MAX_WAITING", 2)
    release = asyncio.Event()

    async def slow_run(*args, **kwargs):
        env.run_calls.append(args)
        await release.wait()
        return MATCH

    monkeypatch.setattr(pipeline, "run", slow_run)
    waiting = [asyncio.create_task(svc.answer_question(COURSE, q)) for q in (1, 2)]
    await asyncio.sleep(0)
    await svc.answer_question(COURSE, 3)  # skipped right away
    assert len(env.run_calls) == 2
    release.set()
    await asyncio.gather(*waiting)
    assert svc._live_waiting == 0 and len(env.posted) == 2


# ── The thread re-check before posting ───────────────────────────────────────


def post(role="STUDENT", kind="ANSWER", accepted=False):
    return NS(author_role=role, kind=kind, is_accepted=accepted)


@pytest.mark.parametrize(
    ("question", "reason"),
    [
        (None, "deleted"),
        (NS(status="CLOSED", posts=[]), "closed"),
        (NS(status="OPEN", posts=[post("AI")]), "has_ai_post"),
        (NS(status="OPEN", posts=[post(accepted=True)]), "has_accepted_answer"),
        (NS(status="OPEN", posts=[post("STAFF")]), "has_staff_answer"),
        (NS(status="OPEN", posts=[]), None),
        (NS(status="OPEN", posts=[post("STUDENT")]), None),  # peers don't stop it
        (NS(status="OPEN", posts=[post("STAFF", kind="FOLLOWUP")]), None),
    ],
)
def test_skip_reason(question, reason):
    assert svc.skip_reason(question) == reason


# ── Citations ────────────────────────────────────────────────────────────────


def test_citations_are_the_best_three_distinct_sources():
    chunks = [
        chunk(score=0.9),
        chunk(score=0.9),  # same citation_url: deduplicated
        chunk("historical_qa", score=0.8),
        chunk("historical_qa", score=0.75),  # same question_id
        chunk(score=0.7),
        chunk(score=0.6),  # a fourth source: left out
    ]
    cites = svc.citations_from(chunks)
    assert [c["rank"] for c in cites] == [1, 2, 3]
    assert [c["similarity_score"] for c in cites] == [0.9, 0.8, 0.7]
    assert cites[1] == {
        "rank": 2,
        "label": "Past question › P1 deadline",
        "resource_type": "historical_qa",
        "similarity_score": 0.8,
        "question_id": 12,
    }
    assert "question_id" not in cites[0]
    AICitations.model_validate({"citations": cites})


# ── Refusals ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "answer",
    [
        "I don't have enough information to answer that.",
        "I do not know based on the context.",
        "The provided context does not contain the answer.",
        "The context doesn't say.",
        "Sorry, I can't help with that.",
        "There is not enough information in the context.",
        '  "I cannot answer this from the material."',
        # How qwen2.5:1.5b actually phrases them (Bill's eval run, review of !30):
        # the participle after the noun, or the subject first.
        "The context provided does not contain any information about office hours.",
        "Midterm 1 is not mentioned in the provided information.",
        "The information given doesn't say when P4 is due.",
        "The provided materials do not cover regrades.",
        "Office hours are not covered in the context.",
        # From the review of main (10/23): a lead-in, "there is no", curly quotes.
        "Unfortunately, the provided context does not mention the midterm date.",
        "Based on the provided context, there is no information about the midterm.",
        "I am sorry, but I cannot find that in the material.",
        "I don’t have enough information to answer that.",
        "The context doesn’t say when P4 is due.",
    ],
)
def test_short_refusals_are_suppressed(answer):
    assert svc.is_refusal(answer)


@pytest.mark.parametrize(
    "answer",
    [
        "Projects are 60% of the grade.",
        "I think the answer is 3 slip days.",
        "The syllabus does not cover regrades, but the rubric says to email your TA.",
        # A refusal phrase mid-answer isn't suppressed (§5.3).
        "Slip days: 3. The context does not say whether they roll over.",
        # Long enough to be a real answer despite the opening.
        "The provided context does not say directly. " + "Detail " * 40,
        # "not mentioned" only counts as the answer's first and only clause.
        "There are 3 slip days; rollover is not mentioned in the provided context.",
        "You get 5 slip days. Rollover is not mentioned in the context.",
        "Slip days: 5. Whether they roll over is not covered in the information.",
        # The participle form with no refusal in it.
        "The context provided shows that each student gets 5 slip days.",
        # An answer that only starts like an apology.
        "Unfortunately, slip days can't be used on the Final Project.",
    ],
)
def test_real_and_partial_answers_are_posted(answer):
    assert not svc.is_refusal(answer)


def test_an_overlong_label_is_clipped_not_fatal():
    # Citation.label allows 500 characters; a longer one used to fail
    # create_ai_post's validation and lose the whole answer.
    (cite,) = svc.citations_from(
        [chunk(label="Course repo › " + "deep heading › " * 50)]
    )
    assert len(cite["label"]) == 500 and cite["label"].endswith("…")
    AICitations.model_validate({"citations": [cite]})

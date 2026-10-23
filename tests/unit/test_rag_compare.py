"""
Unit tests for the compare endpoint (docs/design-rag.md §5.3, §11).

The app runs in-process through httpx's ASGITransport, and pipeline.run is
replaced, so this checks the endpoint's own job: the exact response shape the
harness reads, that it writes nothing, the status code for every pipeline
error, access control, the time budget, and the compare-activity record the
live path pauses on. CPU measurement is checked against fake cpu_times.
"""

from __future__ import annotations

import time
from collections import namedtuple
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

COURSE = 7
MISSING_COURSE = 99

BODY = {
    "question": "How many slip days does each team get?",
    "ingestion_profile": "sliding-window",
    "similarity_threshold": 0.55,
    "system_prompt": "Answer only from the context.",
    "generation_model": "qwen2.5:1.5b",
}


class FakeDb:
    """Knows one course; fails the test on any write."""

    def __init__(self):
        self.courses = {COURSE: SimpleNamespace(id=COURSE)}

    async def get(self, model, key):
        assert model.__name__ == "Course", f"unexpected get({model.__name__})"
        return self.courses.get(key)

    def add(self, obj):
        raise AssertionError("the compare endpoint must not create rows")

    async def flush(self):
        raise AssertionError("the compare endpoint must not write")

    async def commit(self):
        pass  # get_db commits every request; nothing was added

    async def rollback(self):
        pass


def matched_result(**overrides):
    from app.services.rag import pipeline

    fields = dict(
        matched=True,
        chunks=[
            pipeline.RetrievedChunk(
                resource_type="syllabus",
                source_url="https://aicoding.example/syllabus.html",
                similarity_score=0.81,
                text="Each team has three slip days for the projects.",
                metadata={"title": "Syllabus › Late policy"},
            )
        ],
        answer="Each team gets three slip days.",
        metrics=pipeline.RagMetrics(
            embedding_time_ms=12.5, retrieval_time_ms=3.0, generation_time_ms=900.0
        ),
    )
    return pipeline.RagResult(**{**fields, **overrides})


@pytest.fixture
def runs(monkeypatch):
    """Replaces pipeline.run; records each call. Set `runs.result` or `runs.error`."""
    from app.services.rag import compare, pipeline

    calls = []

    async def fake_run(course_id, question_text, config, *, caller, deadline):
        calls.append(
            dict(
                course_id=course_id,
                question_text=question_text,
                config=config,
                caller=caller,
                deadline=deadline,
                active_during=compare.active_or_ended_within(0),
            )
        )
        if calls_ns.error is not None:
            raise calls_ns.error
        return calls_ns.result

    calls_ns = SimpleNamespace(calls=calls, result=matched_result(), error=None)
    monkeypatch.setattr(pipeline, "run", fake_run)
    monkeypatch.setattr(compare, "_active", 0)
    monkeypatch.setattr(compare, "_last_ended", None)
    return calls_ns


async def _client_as(role, fake_db):
    from app.common.dependencies import CourseMember, require_course_member
    from app.database import get_db
    from app.main import app

    async def member():
        return CourseMember(SimpleNamespace(id="u-1", role="USER"), role)

    async def db():
        yield fake_db

    app.dependency_overrides[require_course_member] = member
    app.dependency_overrides[get_db] = db
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest_asyncio.fixture
async def client(runs):
    from app.main import app

    async with await _client_as("STAFF", FakeDb()) as ac:
        yield ac
    app.dependency_overrides.clear()


def url(course_id=COURSE) -> str:
    return f"/api/courses/{course_id}/rag/compare"


# ── Response shape ───────────────────────────────────────────────────────────


async def test_match_returns_exact_contract(client, runs):
    r = await client.post(url(), json=BODY)

    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"matched", "retrieved_chunks", "answer", "metrics"}
    assert body["matched"] is True
    assert body["answer"] == "Each team gets three slip days."
    [chunk] = body["retrieved_chunks"]
    # No metadata or other internals leak into the contract.
    assert chunk == {
        "resource_type": "syllabus",
        "source_url": "https://aicoding.example/syllabus.html",
        "similarity_score": 0.81,
        "text": "Each team has three slip days for the projects.",
    }
    metrics = body["metrics"]
    assert set(metrics) == {
        "embedding_time_ms",
        "retrieval_time_ms",
        "generation_time_ms",
        "cpu_percent",
    }
    assert metrics["embedding_time_ms"] == 12.5
    assert metrics["generation_time_ms"] == 900.0
    assert 0.0 <= metrics["cpu_percent"] <= 100.0


async def test_no_match_returns_null_answer_and_no_chunks(client, runs):
    from app.services.rag import pipeline

    runs.result = pipeline.RagResult(matched=False, chunks=[], answer=None)

    r = await client.post(url(), json=BODY)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["matched"] is False
    assert body["answer"] is None
    assert body["retrieved_chunks"] == []
    assert body["metrics"]["generation_time_ms"] == 0.0


async def test_answer_is_null_whenever_not_matched(client, runs):
    # Defensive: the contract says null when matched is false, whatever run() says.
    runs.result = matched_result(matched=False, chunks=[])

    r = await client.post(url(), json=BODY)

    assert r.json()["answer"] is None


async def test_truncated_answer_is_still_200(client, runs):
    runs.result = matched_result(answer="Each team gets", truncated=True)

    r = await client.post(url(), json=BODY)

    assert r.status_code == 200
    assert r.json()["answer"] == "Each team gets"


async def test_passes_the_body_to_the_pipeline(client, runs, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "RAG_COMPARE_BUDGET_S", 150.0)
    before = time.monotonic()

    r = await client.post(url(), json=BODY)

    assert r.status_code == 200
    [call] = runs.calls
    assert call["course_id"] == COURSE
    assert call["question_text"] == BODY["question"]
    assert call["caller"] == "COMPARE"
    config = call["config"]
    assert config.ingestion_profile == "sliding-window"
    assert config.similarity_threshold == 0.55
    assert config.system_prompt == BODY["system_prompt"]
    assert config.generation_model == "qwen2.5:1.5b"
    # A total budget from arrival, not from when generation starts.
    assert before + 150.0 <= call["deadline"] <= time.monotonic() + 150.0


# ── Errors: never a silent fallback ──────────────────────────────────────────


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        ("UnknownProfile", 422, "INVALID_INPUT"),
        ("ModelNotAvailable", 422, "INVALID_INPUT"),
        ("ProfileNotIngested", 404, "NOT_FOUND"),
        ("ProfileStale", 409, "CONFLICT"),
    ],
)
async def test_pipeline_errors_map_to_status(client, runs, error, status, code):
    from app.services.rag import pipeline

    runs.error = getattr(pipeline, error)()

    r = await client.post(url(), json=BODY)

    assert r.status_code == status, r.text
    assert r.json()["error"] == code


async def test_unpulled_model_names_the_model(client, runs):
    from app.services.rag import pipeline

    runs.error = pipeline.ModelNotAvailable()

    r = await client.post(url(), json={**BODY, "generation_model": "llama9:70b"})

    assert "llama9:70b" in r.json()["message"]


async def test_service_down_is_503(client, runs):
    from app.services.rag import clients

    runs.error = clients.ServiceUnavailable("infinity", "ConnectError: refused")

    r = await client.post(url(), json=BODY)

    assert r.status_code == 503, r.text
    body = r.json()
    assert body["error"] == "SERVICE_UNAVAILABLE"
    assert body["message"].startswith("infinity is unavailable")


async def test_unknown_course_is_404_before_the_pipeline(client, runs):
    # A global admin passes require_course_staff for any course_id.
    r = await client.post(url(MISSING_COURSE), json=BODY)

    assert r.status_code == 404
    assert runs.calls == []


# ── Validation ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "body",
    [
        {k: v for k, v in BODY.items() if k != "generation_model"},
        {**BODY, "extra_field": 1},
        {**BODY, "question": ""},
        {**BODY, "similarity_threshold": 1.5},
        {**BODY, "similarity_threshold": "high"},
        {**BODY, "ingestion_profile": ""},
    ],
    ids=[
        "missing",
        "extra",
        "empty-question",
        "threshold-range",
        "threshold-type",
        "empty-profile",
    ],
)
async def test_invalid_body_is_422(client, runs, body):
    r = await client.post(url(), json=body)

    assert r.status_code == 422
    assert runs.calls == []


async def test_empty_system_prompt_is_allowed(client, runs):
    # It's used literally; an empty one is a valid (if unwise) configuration.
    r = await client.post(url(), json={**BODY, "system_prompt": ""})

    assert r.status_code == 200


# ── Access ───────────────────────────────────────────────────────────────────


async def test_students_cannot_compare(runs):
    from app.main import app

    try:
        async with await _client_as("STUDENT", FakeDb()) as ac:
            r = await ac.post(url(), json=BODY)
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 403
    assert runs.calls == []


# ── Compare activity (live answering pauses on it) ───────────────────────────


async def test_activity_is_recorded_during_and_after_a_call(client, runs):
    from app.services.rag import compare

    assert not compare.active_or_ended_within(60)

    await client.post(url(), json=BODY)

    assert runs.calls[0]["active_during"] is True
    assert compare._active == 0
    assert compare.active_or_ended_within(60)


async def test_activity_is_recorded_when_the_pipeline_fails(client, runs):
    from app.services.rag import compare, pipeline

    runs.error = pipeline.ProfileStale()

    await client.post(url(), json=BODY)

    assert compare._active == 0
    assert compare.active_or_ended_within(60)


def test_activity_expires_after_the_quiet_period(monkeypatch):
    from app.services.rag import compare

    monkeypatch.setattr(compare, "_active", 0)
    monkeypatch.setattr(compare, "_last_ended", time.monotonic() - 61)

    assert not compare.active_or_ended_within(60)
    assert compare.active_or_ended_within(120)


# ── CPU measurement ──────────────────────────────────────────────────────────

LinuxTimes = namedtuple(
    "LinuxTimes", "user nice system idle iowait irq softirq steal guest guest_nice"
)


def test_cpu_percent_is_busy_over_total(monkeypatch):
    from app.services.rag import compare

    samples = iter(
        [
            LinuxTimes(100, 0, 50, 800, 50, 0, 0, 0, 10, 0),
            # +60 busy (user 40, system 20), +40 idle (idle 30, iowait 10).
            # Guest time grew too but is already in user, so it isn't counted twice.
            LinuxTimes(140, 0, 70, 830, 60, 0, 0, 0, 30, 0),
        ]
    )
    monkeypatch.setattr(compare.psutil, "cpu_times", lambda: next(samples))

    window = compare.CpuWindow()

    assert window.percent() == 60.0


def test_cpu_percent_with_no_elapsed_time_is_zero(monkeypatch):
    from app.services.rag import compare

    same = LinuxTimes(100, 0, 50, 800, 50, 0, 0, 0, 0, 0)
    monkeypatch.setattr(compare.psutil, "cpu_times", lambda: same)

    assert compare.CpuWindow().percent() == 0.0

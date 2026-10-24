"""
Unit tests for the course RAG health check (docs/design-rag.md §5.1, §10):
it's green only when everything a live answer or a harness run needs is in
place, and it names each thing that isn't. Services and the database are
fakes.
"""

from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from app.services.rag import clients, health
from app.services.rag.profiles import get_profile

COURSE = 9
LIVE = "sliding-window"
MINILM = "sentence-transformers/all-MiniLM-L6-v2"
GTE = "Alibaba-NLP/gte-Qwen2-1.5B-instruct"


def row(
    profile=LIVE, source="resource:1", sync="s1", content="h1", chunks=10, error=None
):
    return NS(
        profile=profile,
        source_key=source,
        current_sync_id=sync,
        content_hash=content,
        chunk_count=chunks,
        last_error=error,
    )


def ingested(profile=LIVE, **kw):
    """A profile with one resource and historical Q&A, both current."""
    return [
        row(profile, **kw),
        row(profile, source="historical_qa", content="q1", chunks=4),
    ]


class FakeDB:
    def __init__(self, rows):
        self.rows = rows

    async def scalars(self, statement):
        return list(self.rows)


@pytest.fixture
def env(monkeypatch):
    state = NS(
        services={
            "ollama": {"ok": True, "models": ["qwen2.5:1.5b", "qwen2.5:3b"]},
            "infinity": {"ok": True, "models": [MINILM]},
            "chromadb": {"ok": True},
        },
        collections={LIVE: get_profile(LIVE).hash()},  # profile name -> stored hash
    )

    async def fake_health():
        return state.services

    async def get_collection(name):
        profile = name.split("__", 1)[1]
        if profile not in state.collections:
            return None
        return NS(metadata={"profile_hash": state.collections[profile]})

    monkeypatch.setattr(clients, "health", fake_health)
    monkeypatch.setattr(clients, "get_collection", get_collection)
    monkeypatch.setattr(health.settings, "RAG_LIVE_ENABLED", True)
    return state


async def check(rows, **kw):
    return await health.course_health(rows, COURSE, **kw)


async def test_load_index_syncs_reads_the_course_rows():
    rows = ingested()
    assert await health.load_index_syncs(FakeDB(rows), COURSE) == rows


async def test_profiles_are_checked_concurrently(env, monkeypatch):
    # One ChromaDB round trip per profile; they shouldn't queue behind each other.
    import asyncio

    running = {"now": 0, "max": 0}

    async def slow_get_collection(name):
        running["now"] += 1
        running["max"] = max(running["max"], running["now"])
        await asyncio.sleep(0.01)
        running["now"] -= 1
        return None

    monkeypatch.setattr(clients, "get_collection", slow_get_collection)
    await check([], profiles=["type-tailored", "embedding-alt", "embedding-cls"])
    assert running["max"] == 4


async def test_green_when_everything_is_in_place(env):
    report = await check(ingested())
    assert report["ok"] is True and report["problems"] == []
    assert report["live"]["ok"] is True and report["live"]["problems"] == []
    (live,) = report["profiles"]
    assert live == {
        "name": LIVE,
        "embedding_model": MINILM,
        "collection": True,
        "hash_matches": True,
        "embedding_model_loaded": True,
        "sources": 2,
        "chunks": 14,
        "problems": [],
    }
    assert report["generation_models"] == [{"model": "qwen2.5:1.5b", "pulled": True}]


async def test_a_service_down(env):
    env.services["chromadb"] = {"ok": False, "error": "connection refused"}
    report = await check(ingested())
    assert report["ok"] is False
    assert "chromadb is unreachable: connection refused" in report["problems"]
    assert report["profiles"][0]["collection"] is None  # unknown, not "missing"
    assert report["live"]["ok"] is False


async def test_ollama_down_leaves_models_unknown(env):
    env.services["ollama"] = {"ok": False, "error": "down"}
    report = await check(ingested())
    assert report["generation_models"] == [{"model": "qwen2.5:1.5b", "pulled": None}]
    assert report["live"]["ok"] is False


async def test_nothing_ingested(env):
    env.collections = {}
    report = await check([])
    assert (
        "profile 'sliding-window': nothing ingested for this course"
        in report["problems"]
    )
    assert report["live"]["ok"] is False


async def test_stale_collection(env):
    env.collections[LIVE] = "0" * 16
    report = await check(ingested())
    assert any("different profile definition" in p for p in report["problems"])
    assert report["profiles"][0]["hash_matches"] is False


async def test_eval_profiles_named_in_the_request_are_checked(env):
    # embedding-alt: ingested, but its model isn't loaded; type-tailored: never ingested.
    env.collections["embedding-alt"] = get_profile("embedding-alt").hash()
    rows = ingested() + ingested("embedding-alt")
    report = await check(rows, profiles=["type-tailored", "embedding-alt"])
    names = [p["name"] for p in report["profiles"]]
    assert names == [LIVE, "type-tailored", "embedding-alt"]
    assert (
        f"profile 'embedding-alt': embedding model {GTE} isn't loaded in Infinity"
        in report["problems"]
    )
    assert (
        "profile 'type-tailored': nothing ingested for this course"
        in report["problems"]
    )
    assert report["live"]["ok"] is True  # the live profile itself is fine


async def test_profiles_with_content_are_checked_without_being_named(env):
    env.collections["type-tailored"] = "stale"
    report = await check(ingested() + ingested("type-tailored"))
    assert [p["name"] for p in report["profiles"]] == [LIVE, "type-tailored"]
    assert report["ok"] is False


async def test_unknown_profile_name(env):
    report = await check(ingested(), profiles=["sliding-windw"])
    assert "profile 'sliding-windw': no such ingestion profile" in report["problems"]


async def test_eval_generation_model_not_pulled(env):
    report = await check(ingested(), generation_models=["qwen2.5:3b", "llama3.2"])
    assert report["generation_models"] == [
        {"model": "qwen2.5:1.5b", "pulled": True},
        {"model": "qwen2.5:3b", "pulled": True},
        {"model": "llama3.2", "pulled": False},
    ]
    assert report["problems"] == [
        "generation model 'llama3.2' isn't pulled into Ollama"
    ]
    assert report["live"]["ok"] is True


async def test_failed_sync(env):
    report = await check(ingested(error="HTTP 404 from https://x"))
    assert (
        "profile 'sliding-window': resource:1 last sync failed: HTTP 404 from https://x"
        in report["problems"]
    )


async def test_historical_qa_not_indexed(env):
    report = await check([row()])
    assert any("historical Q&A isn't indexed" in p for p in report["problems"])


async def test_version_mismatch_across_profiles(env):
    env.collections["type-tailored"] = get_profile("type-tailored").hash()
    rows = ingested() + ingested("type-tailored", content="h2")
    report = await check(rows)
    assert report["version_mismatch"] == ["resource:1"]
    assert any(
        p.startswith("resource:1 is on different versions") for p in report["problems"]
    )


async def test_cleared_qa_hash_is_not_a_mismatch(env):
    # §4.6 clears content_hash on un-accept for every profile at once.
    env.collections["type-tailored"] = get_profile("type-tailored").hash()
    rows = ingested() + ingested("type-tailored")
    for r in rows:
        if r.source_key == "historical_qa":
            r.content_hash = None
    report = await check(rows)
    assert report["version_mismatch"] == [] and report["ok"] is True


async def test_live_answering_disabled(env, monkeypatch):
    monkeypatch.setattr(health.settings, "RAG_LIVE_ENABLED", False)
    report = await check(ingested())
    assert report["live"]["ok"] is False
    assert report["live"]["problems"][0].startswith("live answering is disabled")
    assert report["ok"] is True  # the eval side can still be green


async def test_a_cleared_hash_next_to_a_real_one_is_not_a_mismatch(env):
    # After a re-index of only one profile, the other still has the NULL from
    # §4.6. NULL means "re-embed on the next sync", not another version; the
    # staff Resources list (resource_service.source_status) treats it the same.
    env.collections["type-tailored"] = get_profile("type-tailored").hash()
    rows = ingested() + ingested("type-tailored")
    rows[3].content_hash = None  # type-tailored's historical_qa row
    report = await check(rows)
    assert report["version_mismatch"] == []

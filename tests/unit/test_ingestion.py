"""
Unit tests for the ingestion task (docs/design-rag.md §7.3).

ChromaDB, Infinity and MySQL are replaced with in-memory fakes, so this
checks the task's logic: what is visible when, what survives a failure, and
what is skipped. The real services are covered by the integration tests.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from app.services.rag import chunking, clients, ingestion
from app.services.rag.chunking import Section
from app.services.rag.fetchers import FetchError
from app.services.rag.ingestion import Document, SyncInProgress, web_document

COURSE = 7
SOURCE = "resource:3"
PAGE = "https://cs.example.edu/syllabus.html"


class FakeCounter:
    _TOKEN = re.compile(r"\w+|[^\w\s]")

    def token_starts(self, text: str) -> list[int]:
        return [m.start() for m in self._TOKEN.finditer(text)]


class FakeCollection:
    def __init__(self, name, metadata):
        self.name = name
        self.metadata = metadata
        self.items: dict[str, dict] = {}

    def matching(self, where) -> list[str]:
        def ok(meta, clause):
            if "$and" in clause:
                return all(ok(meta, c) for c in clause["$and"])
            ((field, cond),) = clause.items()
            if isinstance(cond, dict) and "$ne" in cond:
                return meta.get(field) != cond["$ne"]
            return meta.get(field) == cond

        return [i for i, item in self.items.items() if ok(item["metadata"], where)]

    def sync_ids(self) -> set[str]:
        return {item["metadata"]["sync_id"] for item in self.items.values()}


class FakeStore:
    def __init__(self):
        self.rows: dict[tuple, SimpleNamespace] = {}

    async def get(self, course_id, profile, source_key):
        return self.rows.get((course_id, profile, source_key))

    async def save(self, course_id, profile, source_key, resource_id, **fields):
        row = self.rows.setdefault(
            (course_id, profile, source_key),
            SimpleNamespace(
                resource_id=resource_id,
                current_sync_id=None,
                content_hash=None,
                commit_sha=None,
                chunk_count=0,
                truncated_chunk_count=0,
                last_synced_at=None,
                last_error=None,
                last_error_at=None,
            ),
        )
        for name, value in fields.items():
            setattr(row, name, value)


@pytest.fixture
def env(monkeypatch):
    """Fakes for every service the task touches; returns their state."""
    state = SimpleNamespace(
        collections={}, store=FakeStore(), embedded=[], fail_models=set()
    )

    async def get_or_create_collection(name, metadata):
        return state.collections.setdefault(name, FakeCollection(name, dict(metadata)))

    async def add_chunks(collection, ids, embeddings, documents, metadatas):
        assert len(ids) == len(embeddings) == len(documents) == len(metadatas)
        for meta in metadatas:
            assert all(v is not None for v in meta.values())
        for i, e, d, m in zip(ids, embeddings, documents, metadatas):
            collection.items[i] = {"embedding": e, "document": d, "metadata": m}

    async def delete_chunks(collection, where):
        for i in collection.matching(where):
            del collection.items[i]

    async def embed(texts, model):
        if model in state.fail_models:
            raise clients.ServiceUnavailable("infinity", "down")
        state.embedded.append((model, list(texts)))
        return [[float(len(t) % 7), 1.0] for t in texts]

    monkeypatch.setattr(clients, "get_or_create_collection", get_or_create_collection)
    monkeypatch.setattr(clients, "add_chunks", add_chunks)
    monkeypatch.setattr(clients, "delete_chunks", delete_chunks)
    monkeypatch.setattr(clients, "embed", embed)
    monkeypatch.setattr(chunking, "default_counter", lambda: FakeCounter())
    monkeypatch.setattr(ingestion, "store", state.store)
    monkeypatch.setattr(ingestion.settings, "CLEANUP_GRACE_S", 0)
    monkeypatch.setattr(ingestion, "_syncing", set())
    return state


def page(body: str) -> str:
    return (
        "<nav>Home</nav><main><h1>Syllabus</h1>"
        f"<h2>Grading</h2><p>{body}</p>"
        "<h2>Late policy</h2><p>Late work loses ten percent per day, up to "
        "three days, after which it is not accepted for any reason at all.</p>"
        "<h2>Office hours</h2><p>Office hours are Monday at two and Thursday "
        "at four in the computer sciences building, room 1240.</p>"
        "</main>"
    )


def loader(html: str):
    async def load():
        return [web_document(html, PAGE, "syllabus")]

    return load


async def run(load, profiles=("sliding-window",), **kwargs):
    await ingestion.claim(COURSE, SOURCE)
    await ingestion.ingest(
        course_id=COURSE,
        source_key=SOURCE,
        resource_id=3,
        title="Course syllabus",
        profiles=list(profiles),
        load=load,
        **kwargs,
    )


def collection(env, profile="sliding-window") -> FakeCollection:
    return env.collections[f"course_{COURSE}__{profile}"]


def row(env, profile="sliding-window"):
    return env.store.rows[(COURSE, profile, SOURCE)]


# ── Happy path ───────────────────────────────────────────────────────────────


async def test_web_page_is_ingested_under_each_profile(env):
    await run(
        loader(page("Projects are 60% and exams 40% of the grade.")),
        profiles=("sliding-window", "type-tailored"),
    )
    for profile in ("sliding-window", "type-tailored"):
        r = row(env, profile)
        coll = collection(env, profile)
        assert r.last_error is None and r.current_sync_id
        assert r.chunk_count == len(coll.items) == 3
        assert coll.sync_ids() == {r.current_sync_id}
        assert coll.metadata["profile_hash"] == ingestion.get_profile(profile).hash()
    assert not ingestion.is_syncing(COURSE, SOURCE)


async def test_chunk_metadata_and_embedded_text(env):
    await run(loader(page("Projects are 60% and exams 40% of the grade.")))
    items = list(collection(env).items.items())
    chunk_id, item = items[0]
    meta = item["metadata"]
    sync_id = row(env).current_sync_id

    assert chunk_id == f"{SOURCE}:{sync_id}:0"
    assert item["document"] == "Projects are 60% and exams 40% of the grade."
    assert meta["label"] == "Course syllabus › Syllabus › Grading"
    assert meta["heading_path"] == "Syllabus › Grading"
    assert meta["source_url"] == PAGE
    assert meta["citation_url"].startswith(PAGE + "#:~:text=")
    assert meta["resource_type"] == "syllabus"
    assert meta["resource_id"] == 3 and meta["source_key"] == SOURCE
    assert meta["sync_id"] == sync_id and meta["chunk_index"] == 0
    # The heading line is embedded with the text, but not stored with it.
    model, texts = env.embedded[-1]
    assert model == ingestion.get_profile("sliding-window").embedding_model
    assert (
        texts[0] == "Syllabus › Grading\nProjects are 60% and exams 40% of the grade."
    )


# ── Re-sync ──────────────────────────────────────────────────────────────────


async def test_resync_switches_then_removes_the_old_version(env):
    await run(loader(page("Projects are 60% of the grade.")))
    first = row(env).current_sync_id

    await run(loader(page("Projects are 70% of the grade.")))
    second = row(env).current_sync_id

    assert second != first
    assert collection(env).sync_ids() == {second}
    docs = [i["document"] for i in collection(env).items.values()]
    assert "Projects are 70% of the grade." in docs
    assert "Projects are 60% of the grade." not in docs


async def test_unchanged_content_is_not_reembedded(env):
    html = page("Projects are 60% of the grade.")
    await run(loader(html))
    first = row(env).current_sync_id
    row(env).last_synced_at = None
    calls = len(env.embedded)

    await run(loader(html))

    assert len(env.embedded) == calls
    assert row(env).current_sync_id == first
    assert row(env).last_synced_at is not None


async def test_changed_link_target_is_reembedded(env):
    html = page("Projects are 60% of the grade.")
    await run(loader(html))
    first = row(env).current_sync_id

    async def moved():
        return [web_document(html, "https://new.example.edu/syllabus.html", "syllabus")]

    await run(moved)
    assert row(env).current_sync_id != first


# ── Failures ─────────────────────────────────────────────────────────────────


async def test_fetch_failure_keeps_the_current_version(env):
    await run(loader(page("Projects are 60% of the grade.")))
    current = row(env).current_sync_id

    async def broken():
        raise FetchError("HTTP 503 from https://cs.example.edu/syllabus.html")

    await run(broken, profiles=("sliding-window", "type-tailored"))

    assert row(env).current_sync_id == current
    assert row(env).last_error == "HTTP 503 from https://cs.example.edu/syllabus.html"
    assert row(env).last_error_at is not None
    assert row(env, "type-tailored").last_error.startswith("HTTP 503")
    assert collection(env).sync_ids() == {current}
    assert not ingestion.is_syncing(COURSE, SOURCE)


async def test_failed_profile_does_not_block_the_others(env):
    env.fail_models.add(ingestion.get_profile("embedding-alt").embedding_model)
    await run(
        loader(page("Projects are 60% of the grade.")),
        profiles=("embedding-alt", "sliding-window"),
    )
    assert row(env, "embedding-alt").last_error == "infinity unavailable: down"
    assert row(env, "embedding-alt").current_sync_id is None
    assert collection(env, "embedding-alt").items == {}
    assert row(env, "sliding-window").last_error is None
    assert row(env, "sliding-window").chunk_count == 3


async def test_error_clears_on_the_next_successful_sync(env):
    html = page("Projects are 60% of the grade.")
    await run(loader(html))
    env.fail_models.add(ingestion.get_profile("sliding-window").embedding_model)
    await run(loader(page("Projects are 70% of the grade.")))
    assert row(env).last_error

    env.fail_models.clear()
    # Same content as the last good sync, but the error means it must not
    # be skipped as unchanged.
    await run(loader(page("Projects are 70% of the grade.")))
    assert row(env).last_error is None and row(env).last_error_at is None


async def test_changed_profile_is_refused(env):
    name = f"course_{COURSE}__sliding-window"
    env.collections[name] = FakeCollection(name, {"profile_hash": "old"})
    await run(loader(page("Projects are 60% of the grade.")))
    assert row(env).last_error == "profile changed"
    assert env.collections[name].items == {}


async def test_unknown_profile_is_recorded(env):
    await run(loader(page("Projects are 60% of the grade.")), profiles=("nope",))
    assert (
        "unknown ingestion profile"
        in env.store.rows[(COURSE, "nope", SOURCE)].last_error
    )


# ── Registry ─────────────────────────────────────────────────────────────────


async def test_a_source_can_only_be_claimed_once(env):
    await ingestion.claim(COURSE, SOURCE)
    with pytest.raises(SyncInProgress):
        await ingestion.claim(COURSE, SOURCE)
    await ingestion.claim(COURSE, "resource:4")  # other sources are free
    await ingestion.release(COURSE, SOURCE)
    await ingestion.claim(COURSE, SOURCE)


# ── Atomic documents ─────────────────────────────────────────────────────────


async def test_unchunked_types_are_one_chunk_per_section(env):
    text = "Q: When is P1 due?\nA: Sep 15.\n" + "word " * 300
    first_end = text.index("\nword")
    qa = Document(
        resource_type="historical_qa",
        key="qa",
        text=text,
        sections=(
            Section(0, first_end, ("When is P1 due?",)),
            Section(first_end + 1, len(text.rstrip()), ("Long thread",)),
        ),
        locate=lambda chunk: {"source_url": "/questions/1"},
    )

    async def load():
        return [qa]

    await run(load)
    assert row(env).chunk_count == 2
    # The 300-word thread is over MiniLM's 256-token input limit.
    assert row(env).truncated_chunk_count == 1
    labels = sorted(i["metadata"]["label"] for i in collection(env).items.values())
    assert labels == [
        "Course syllabus › Long thread",
        "Course syllabus › When is P1 due?",
    ]

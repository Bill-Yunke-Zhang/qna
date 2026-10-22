"""
Unit tests for the ingestion task (docs/design-rag.md §7.3).

ChromaDB, Infinity and MySQL are replaced with in-memory fakes, so this
checks the task's logic: what is visible when, what survives a failure, and
what is skipped. The real services are covered by the integration tests.
"""

from __future__ import annotations

import io
import re
import zipfile
from types import SimpleNamespace

import pytest

from app.services.rag import chunking, clients, ingestion
from app.services.rag.chunking import Section
from app.services.rag.fetchers import FetchError, UploadError
from app.services.rag.fetchers import QAThread as FetchedThread
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


def zip_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


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
    # The page's h1 is only dropped from the label when it repeats the title.
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


# ── Historical Q&A ───────────────────────────────────────────────────────────

QA = ingestion.HISTORICAL_QA_SOURCE_KEY


def thread(qid=1, post_id=10, title="When is P1 due?", answer="Sep 15 at 11:59pm."):
    return FetchedThread(qid, title, "I can't find the P1 deadline.", post_id, answer)


def qa_loader(*threads):
    async def load():
        return [ingestion.qa_document(t) for t in threads]

    return load


async def run_qa(load, profiles=("sliding-window",)):
    await ingestion.claim(COURSE, QA)
    await ingestion.ingest(
        course_id=COURSE,
        source_key=QA,
        resource_id=None,
        title=ingestion.HISTORICAL_QA_TITLE,
        profiles=list(profiles),
        load=load,
    )


async def test_qa_thread_is_one_chunk_with_its_ids(env):
    await run_qa(qa_loader(thread(), thread(qid=2, post_id=20, title="Room?")))
    items = sorted(
        collection(env).items.values(), key=lambda i: i["metadata"]["question_id"]
    )
    assert len(items) == 2
    meta, doc = items[0]["metadata"], items[0]["document"]
    assert meta["label"] == "Past question › When is P1 due?"
    assert meta["resource_type"] == "historical_qa"
    assert meta["source_key"] == QA and "resource_id" not in meta
    assert meta["source_url"] == "/questions/1" and "citation_url" not in meta
    assert (meta["question_id"], meta["accepted_post_id"]) == (1, 10)
    # The prompt tags the question and the answer separately (§5.5).
    assert doc[: meta["answer_start"]].strip() == "I can't find the P1 deadline."
    assert doc[meta["answer_start"] :] == "Sep 15 at 11:59pm."
    # The title is embedded but not stored.
    assert "When is P1 due?" not in doc
    assert any(
        t.startswith("When is P1 due?\nI can't find") for t in env.embedded[-1][1]
    )


async def test_qa_reindex_skips_unchanged_threads(env):
    await run_qa(qa_loader(thread()))
    embedded = len(env.embedded)
    await run_qa(qa_loader(thread()))
    assert len(env.embedded) == embedded


async def test_qa_title_or_accepted_post_change_reembeds(env):
    await run_qa(qa_loader(thread()))
    first = env.store.rows[(COURSE, "sliding-window", QA)].content_hash
    await run_qa(qa_loader(thread(title="When is Project 1 due?")))
    second = env.store.rows[(COURSE, "sliding-window", QA)].content_hash
    await run_qa(qa_loader(thread(title="When is Project 1 due?", post_id=11)))
    third = env.store.rows[(COURSE, "sliding-window", QA)].content_hash
    assert len({first, second, third}) == 3
    (item,) = collection(env).items.values()
    assert item["metadata"]["accepted_post_id"] == 11


async def test_no_eligible_threads_is_an_empty_sync(env):
    await run_qa(qa_loader())
    r = env.store.rows[(COURSE, "sliding-window", QA)]
    assert r.last_error is None and r.current_sync_id and r.chunk_count == 0


@pytest.fixture
def drop_env(env, monkeypatch):
    async def get_collection(name):
        return env.collections.get(name)

    async def get_chunk_metadata(collection, where):
        return [collection.items[i]["metadata"] for i in collection.matching(where)]

    monkeypatch.setattr(clients, "get_collection", get_collection)
    monkeypatch.setattr(clients, "get_chunk_metadata", get_chunk_metadata)
    return env


async def test_drop_qa_thread_removes_it_from_every_profile(drop_env):
    env = drop_env
    profiles = ("sliding-window", "type-tailored")
    await run_qa(qa_loader(thread(), thread(qid=2, post_id=20)), profiles=profiles)

    await ingestion.drop_qa_thread(COURSE, 1)

    for profile in profiles:
        items = collection(env, profile).items.values()
        assert [i["metadata"]["question_id"] for i in items] == [2]
        assert env.store.rows[(COURSE, profile, QA)].chunk_count == 1


async def test_drop_qa_thread_leaves_other_sources_and_survives_errors(
    drop_env, monkeypatch
):
    env = drop_env
    await run(loader(page("Projects are 60% of the grade.")))
    await run_qa(qa_loader(thread()))

    async def broken(collection, where):
        raise clients.ServiceUnavailable("chromadb", "down")

    fake_delete = clients.delete_chunks
    monkeypatch.setattr(clients, "delete_chunks", broken)
    await ingestion.drop_qa_thread(COURSE, 1)  # logged, not raised
    assert env.store.rows[(COURSE, "sliding-window", QA)].chunk_count == 1

    monkeypatch.setattr(clients, "delete_chunks", fake_delete)
    # Unknown thread, missing collections: nothing to do.
    await ingestion.drop_qa_thread(COURSE, 99)
    await ingestion.drop_qa_thread(COURSE + 1, 1)
    assert row(env).chunk_count == 3


# ── Uploads ──────────────────────────────────────────────────────────────────

VIEW_URL = (
    "https://git.example.edu/course/-/blob/main/eval/sample_data/web/syllabus.html"
)


def test_uploaded_page_links_to_where_people_view_it():
    html = page("Projects are 60% and exams 40% of the grade.").encode()
    (doc,) = ingestion.parse_upload("SYLLABUS", VIEW_URL, "syllabus.html", html)
    assert doc.resource_type == "syllabus" and doc.key == VIEW_URL
    first = doc.locate(
        ingestion.Chunk(doc.sections[0].start, doc.sections[0].end, (), 1)
    )
    assert first["source_url"] == VIEW_URL
    assert first["citation_url"].startswith(VIEW_URL + "#:~:text=")


@pytest.mark.parametrize(
    ("resource_type", "filename", "message"),
    [
        ("SYLLABUS", "notes.md", "single .html file"),
        ("SCHEDULE", "pages.zip", "single .html file"),
        ("REPO", "page.html", "must be a .zip, .md or .pdf"),
        ("REPO", "repo.md", "have no text"),
    ],
)
def test_upload_must_fit_the_resource_type(resource_type, filename, message):
    data = b"# Notes\n" if filename.endswith(".md") else zip_bytes({"a.md": b"# A"})
    with pytest.raises(UploadError, match=message):
        ingestion.parse_upload(resource_type, VIEW_URL, filename, data)


def test_uploaded_page_without_content_is_refused():
    with pytest.raises(FetchError, match="characters of text"):
        ingestion.parse_upload(
            "SCHEDULE", VIEW_URL, "schedule.html", b"<main><div id=weeks></div></main>"
        )


async def test_uploaded_documents_are_ingested_as_parsed(env):
    docs = ingestion.parse_upload(
        "SYLLABUS", VIEW_URL, "s.html", page("Projects are 60%.").encode()
    )
    await run(ingestion.documents_loader(docs))
    assert row(env).chunk_count == 3
    assert {i["metadata"]["source_url"] for i in collection(env).items.values()} == {
        VIEW_URL
    }


# ── Labels ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("title", "heading_path", "label"),
    [
        ("Syllabus", ("Syllabus", "Grading"), "Syllabus › Grading"),
        ("syllabus ", ("Syllabus",), "syllabus "),
        (
            "Course syllabus",
            ("Syllabus", "Grading"),
            "Course syllabus › Syllabus › Grading",
        ),
        ("Schedule", ("Week 6", "Schedule"), "Schedule › Week 6 › Schedule"),
        ("Syllabus", (), "Syllabus"),
    ],
)
def test_label_drops_a_first_heading_that_repeats_the_title(title, heading_path, label):
    assert ingestion._label(title, heading_path) == label


async def test_repeated_title_is_left_out_of_the_label_only(env):
    await run(loader(page("Projects are 60% of the grade.")))
    # Same page, resource titled like its h1.
    await ingestion.claim(COURSE, "resource:4")
    await ingestion.ingest(
        course_id=COURSE,
        source_key="resource:4",
        resource_id=4,
        title="Syllabus",
        profiles=["sliding-window"],
        load=loader(page("Projects are 60% of the grade.")),
    )
    meta = next(
        i["metadata"]
        for i in collection(env).items.values()
        if i["metadata"]["source_key"] == "resource:4"
        and i["metadata"]["chunk_index"] == 0
    )
    assert meta["label"] == "Syllabus › Grading"
    assert meta["heading_path"] == "Syllabus › Grading"

"""
Unit tests for the staff resource endpoints (docs/design-rag.md §7.2, §7.5).

The app runs in-process through httpx's ASGITransport. The database is a
small in-memory fake that only knows the queries resource_service makes, and
ingestion.ingest is replaced so no background work runs. What's checked:
access control, validation, the 202/404/409/422 contract, and that the
sync claim is always released if scheduling fails.
"""

from __future__ import annotations

import io
import zipfile
from datetime import datetime
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

COURSE = 7
OTHER_COURSE = 8

PAGE = (
    "<html><body><main><h1>Syllabus</h1><h2>Late policy</h2><p>"
    + "Each team has three slip days for the projects. " * 10
    + "</p></main></body></html>"
)


class FakeDb:
    """Holds Course, Resource and IndexSync objects; answers resource_service's queries."""

    def __init__(self):
        self.courses = {
            COURSE: SimpleNamespace(id=COURSE),
            OTHER_COURSE: SimpleNamespace(id=OTHER_COURSE),
        }
        self.resources: dict[int, object] = {}
        self.syncs: list[object] = []
        self.deleted: list[object] = []
        self.commits = 0
        self._next_id = 1

    async def get(self, model, key):
        name = model.__name__
        if name == "Course":
            return self.courses.get(key)
        if name == "Resource":
            return self.resources.get(key)
        raise AssertionError(f"unexpected get({name})")

    def add(self, obj):
        obj.id = self._next_id
        self._next_id += 1
        self.resources[obj.id] = obj

    async def flush(self):
        pass

    async def refresh(self, obj):
        obj.created_at = datetime(2026, 10, 21, 9, 0)

    async def commit(self):
        self.commits += 1

    async def delete(self, obj):
        self.deleted.append(obj)
        self.resources.pop(obj.id, None)

    async def scalars(self, stmt):
        entity = stmt.column_descriptions[0]
        params = stmt.compile().params
        course_id = next(v for k, v in params.items() if k.startswith("course_id"))
        source_key = next(
            (v for k, v in params.items() if k.startswith("source_key")), None
        )
        if entity["entity"].__name__ == "Resource":
            return [r for r in self.resources.values() if r.course_id == course_id]
        rows = [
            s
            for s in self.syncs
            if s.course_id == course_id
            and (source_key is None or s.source_key == source_key)
        ]
        if entity["name"] == "profile":
            return [s.profile for s in rows]
        return rows


def sync_row(source_key, profile, content_hash="h1", **fields):
    defaults = dict(
        course_id=COURSE,
        source_key=source_key,
        profile=profile,
        content_hash=content_hash,
        last_synced_at=datetime(2026, 10, 21, 8, 0),
        chunk_count=3,
        truncated_chunk_count=0,
        commit_sha=None,
        last_error=None,
        last_error_at=None,
    )
    return SimpleNamespace(**{**defaults, **fields})


@pytest.fixture
def fake_db():
    return FakeDb()


@pytest.fixture
def ingested(monkeypatch):
    """Replaces ingestion.ingest; records each call and releases the claim like the real task."""
    from app.services.rag import ingestion

    calls = []

    async def fake_ingest(**kwargs):
        calls.append(kwargs)
        await ingestion.release(kwargs["course_id"], kwargs["source_key"])

    monkeypatch.setattr(ingestion, "ingest", fake_ingest)
    monkeypatch.setattr(ingestion, "_syncing", set())
    return calls


@pytest.fixture
def public_dns(monkeypatch):
    from app.services.rag import fetchers

    async def resolve(host, port):
        return {"internal.example": ["10.0.0.5"]}.get(host, ["93.184.216.34"])

    monkeypatch.setattr(fetchers, "_resolve", resolve)


@pytest_asyncio.fixture
async def client(fake_db, ingested, public_dns):
    from app.common.dependencies import CourseMember, require_course_staff
    from app.database import get_db
    from app.main import app

    user = SimpleNamespace(id="staff-1", role="USER")

    async def staff():
        return CourseMember(user, "STAFF")

    async def db():
        yield fake_db

    app.dependency_overrides[require_course_staff] = staff
    app.dependency_overrides[get_db] = db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


def base(course_id=COURSE) -> str:
    return f"/api/courses/{course_id}"


def url_resource(**overrides):
    return {
        "type": "SYLLABUS",
        "title": "Syllabus",
        "fetch_url": "https://aicoding.example/syllabus.html",
        **overrides,
    }


def upload(name="syllabus.html", data=PAGE.encode(), **form):
    fields = {
        "type": "SYLLABUS",
        "title": "Syllabus",
        "link_base_url": "https://aicoding.example/syllabus.html",
        **form,
    }
    return {"data": fields, "files": {"file": (name, data, "application/octet-stream")}}


# ── Access ───────────────────────────────────────────────────────────────────


async def test_students_cannot_reach_resources(fake_db):
    # The real require_course_staff runs on top of a member whose effective
    # role is STUDENT (e.g. anyone using the Student app).
    from app.common.dependencies import CourseMember, require_course_member
    from app.database import get_db
    from app.main import app

    async def member():
        return CourseMember(SimpleNamespace(id="s-1", role="USER"), "STUDENT")

    async def db():
        yield fake_db

    app.dependency_overrides[require_course_member] = member
    app.dependency_overrides[get_db] = db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            r = await ac.get(f"{base()}/resources")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 403


# ── Register by URL ──────────────────────────────────────────────────────────


async def test_register_url_resource_starts_a_sync(client, fake_db, ingested):
    r = await client.post(f"{base()}/resources", json=url_resource())

    assert r.status_code == 202, r.text
    body = r.json()
    assert body["origin"] == "URL" and body["fetch_url"].endswith("syllabus.html")
    assert fake_db.commits == 1
    [call] = ingested
    assert call["course_id"] == COURSE
    assert call["source_key"] == f"resource:{body['id']}"
    assert call["resource_id"] == body["id"]
    assert call["profiles"] == ["sliding-window"]  # RAG_LIVE_PROFILE


async def test_register_validates_profiles(client, ingested):
    r = await client.post(
        f"{base()}/resources", json=url_resource(profiles=["sliding-window", "nope"])
    )
    assert r.status_code == 422
    assert "nope" in r.json()["message"]
    assert ingested == []


async def test_register_refuses_private_addresses(client, fake_db):
    r = await client.post(
        f"{base()}/resources", json=url_resource(fetch_url="http://internal.example/x")
    )
    assert r.status_code == 422
    assert fake_db.resources == {}


@pytest.mark.parametrize(
    "overrides",
    [
        {"type": "REPO"},  # no branch
        {"type": "SYLLABUS", "repo_branch": "main"},  # branch on a page
    ],
)
async def test_register_checks_repo_branch(client, overrides):
    r = await client.post(f"{base()}/resources", json=url_resource(**overrides))
    assert r.status_code == 422


async def test_register_repo_must_be_on_gitlab_host(client):
    r = await client.post(
        f"{base()}/resources",
        json=url_resource(
            type="REPO", repo_branch="main", fetch_url="https://github.com/x/y.git"
        ),
    )
    assert r.status_code == 422
    assert "git.doit.wisc.edu" in r.json()["message"]


async def test_register_repo_by_url(client, fake_db, ingested):
    r = await client.post(
        f"{base()}/resources",
        json=url_resource(
            type="REPO",
            title="Course repo",
            repo_branch="main",
            fetch_url="https://git.doit.wisc.edu/course/repo/-/tree/main",
        ),
    )
    assert r.status_code == 202, r.text
    # Stored as the project URL, whatever page of it was pasted.
    assert r.json()["fetch_url"] == "https://git.doit.wisc.edu/course/repo"
    assert r.json()["repo_branch"] == "main"
    [call] = ingested
    assert call["load"].__qualname__.startswith("repo_loader")

    rid = r.json()["id"]
    r = await client.post(f"{base()}/resources/{rid}/sync", json={})
    assert r.status_code == 202, r.text
    assert ingested[1]["load"].__qualname__.startswith("repo_loader")


@pytest.mark.parametrize(
    ("fetch_url", "branch"),
    [
        ("http://git.doit.wisc.edu/course/repo", "main"),  # not https
        ("https://git.doit.wisc.edu/repo", "main"),  # not a project
        ("https://git.doit.wisc.edu/course/repo", "--upload-pack=x"),
    ],
)
async def test_register_repo_refuses_bad_urls_and_branches(
    client, fake_db, fetch_url, branch
):
    r = await client.post(
        f"{base()}/resources",
        json=url_resource(type="REPO", repo_branch=branch, fetch_url=fetch_url),
    )
    assert r.status_code == 422
    assert fake_db.resources == {}


async def test_register_in_missing_course_is_404(client):
    r = await client.post(f"{base(999)}/resources", json=url_resource())
    assert r.status_code == 404


# ── Upload ───────────────────────────────────────────────────────────────────


async def test_upload_is_parsed_in_the_request(client, fake_db, ingested):
    r = await client.post(
        f"{base()}/resources/upload", **upload(profiles="sliding-window,type-tailored")
    )

    assert r.status_code == 202, r.text
    assert r.json()["origin"] == "UPLOAD"
    [call] = ingested
    assert call["profiles"] == ["sliding-window", "type-tailored"]
    [document] = await call["load"]()
    assert document.resource_type == "syllabus"
    assert document.key == "https://aicoding.example/syllabus.html"


async def test_bad_upload_is_422_and_stores_nothing(client, fake_db, ingested):
    r = await client.post(f"{base()}/resources/upload", **upload(name="notes.txt"))
    assert r.status_code == 422
    assert fake_db.resources == {} and ingested == []


async def test_upload_needs_an_http_link_base(client):
    r = await client.post(
        f"{base()}/resources/upload", **upload(link_base_url="javascript:alert(1)")
    )
    assert r.status_code == 422


async def test_zip_with_unsafe_path_is_422(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("../evil.md", "# hi")
    r = await client.post(
        f"{base()}/resources/upload",
        **upload(name="repo.zip", data=buf.getvalue(), type="REPO"),
    )
    assert r.status_code == 422


# ── Re-sync, replace, delete ─────────────────────────────────────────────────


async def make_url_resource(client) -> int:
    r = await client.post(f"{base()}/resources", json=url_resource())
    return r.json()["id"]


async def test_resync_defaults_to_the_profiles_it_already_has(
    client, fake_db, ingested
):
    rid = await make_url_resource(client)
    fake_db.syncs += [
        sync_row(f"resource:{rid}", "type-tailored"),
        sync_row(f"resource:{rid}", "sliding-window"),
    ]
    r = await client.post(f"{base()}/resources/{rid}/sync")

    assert r.status_code == 202, r.text
    assert ingested[-1]["profiles"] == ["sliding-window", "type-tailored"]
    assert [s["profile"] for s in r.json()["syncs"]] == [
        "sliding-window",
        "type-tailored",
    ]


async def test_resync_while_syncing_is_409(client, ingested):
    from app.services.rag import ingestion

    rid = await make_url_resource(client)
    await ingestion.claim(COURSE, f"resource:{rid}")
    r = await client.post(f"{base()}/resources/{rid}/sync")
    assert r.status_code == 409


async def test_resource_from_another_course_is_404(client):
    rid = await make_url_resource(client)
    r = await client.post(f"{base(OTHER_COURSE)}/resources/{rid}/sync")
    assert r.status_code == 404


async def test_upload_resources_are_replaced_not_resynced(client):
    r = await client.post(f"{base()}/resources/upload", **upload())
    rid = r.json()["id"]
    r = await client.post(f"{base()}/resources/{rid}/sync")
    assert r.status_code == 409


async def test_replace_upload_keeps_the_resource(client, ingested):
    r = await client.post(f"{base()}/resources/upload", **upload())
    rid = r.json()["id"]
    r = await client.put(
        f"{base()}/resources/{rid}/upload",
        files={"file": ("syllabus.html", PAGE.replace("three", "four").encode())},
    )
    assert r.status_code == 202, r.text
    assert r.json()["id"] == rid
    assert ingested[-1]["source_key"] == f"resource:{rid}"


async def test_url_resources_cannot_take_an_upload(client):
    rid = await make_url_resource(client)
    r = await client.put(
        f"{base()}/resources/{rid}/upload", files={"file": ("s.html", PAGE.encode())}
    )
    assert r.status_code == 409


async def test_delete_removes_chunks_and_row(client, fake_db, monkeypatch):
    from app.services.rag import clients
    from app.services.rag.profiles import PROFILES

    rid = await make_url_resource(client)
    deleted = []

    async def get_collection(name):
        return name

    async def delete_chunks(collection, where):
        deleted.append((collection, where))

    monkeypatch.setattr(clients, "get_collection", get_collection)
    monkeypatch.setattr(clients, "delete_chunks", delete_chunks)
    r = await client.delete(f"{base()}/resources/{rid}")

    assert r.status_code == 204
    assert rid not in fake_db.resources
    assert {w["source_key"] for _, w in deleted} == {f"resource:{rid}"}
    # Every profile's collection, including ones added later.
    assert {c for c, _ in deleted} == {
        p.collection_name(COURSE) for p in PROFILES.values()
    }
    assert f"course_{COURSE}__sliding-window" in {c for c, _ in deleted}


async def test_delete_still_works_with_chromadb_down(client, fake_db, monkeypatch):
    from app.services.rag import clients

    rid = await make_url_resource(client)

    async def down(name):
        raise clients.ServiceUnavailable("chromadb", "refused")

    monkeypatch.setattr(clients, "get_collection", down)
    r = await client.delete(f"{base()}/resources/{rid}")
    assert r.status_code == 204
    assert rid not in fake_db.resources


async def test_delete_while_syncing_is_409(client, fake_db):
    from app.services.rag import ingestion

    rid = await make_url_resource(client)
    await ingestion.claim(COURSE, f"resource:{rid}")
    r = await client.delete(f"{base()}/resources/{rid}")
    assert r.status_code == 409
    assert rid in fake_db.resources


# ── Historical Q&A and the list ──────────────────────────────────────────────


async def test_reindex_historical_qa(client, ingested):
    r = await client.post(
        f"{base()}/historical-qa/sync", json={"profiles": ["type-tailored"]}
    )
    assert r.status_code == 202, r.text
    [call] = ingested
    assert call["source_key"] == "historical_qa"
    assert call["resource_id"] is None
    assert call["profiles"] == ["type-tailored"]


async def test_list_reports_status_and_version_mismatch(client, fake_db):
    rid = await make_url_resource(client)
    fake_db.syncs += [
        sync_row(f"resource:{rid}", "sliding-window", content_hash="a"),
        sync_row(
            f"resource:{rid}", "type-tailored", content_hash="b", last_error="boom"
        ),
        sync_row("historical_qa", "sliding-window"),
    ]
    r = await client.get(f"{base()}/resources")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["live_profile"] == "sliding-window"
    assert "sliding-window" in body["profiles"]
    [resource] = body["resources"]
    assert resource["version_mismatch"] is True
    assert resource["syncs"][1]["last_error"] == "boom"
    assert body["historical_qa"]["version_mismatch"] is False
    assert len(body["historical_qa"]["syncs"]) == 1


# ── The claim is never left behind ───────────────────────────────────────────


async def test_claim_is_released_if_scheduling_fails(monkeypatch, ingested):
    from fastapi import BackgroundTasks

    from app.services import resource_service
    from app.services.rag import ingestion

    tasks = BackgroundTasks()

    def broken(*args, **kwargs):
        raise RuntimeError("scheduler broke")

    monkeypatch.setattr(tasks, "add_task", broken)
    with pytest.raises(RuntimeError):
        await resource_service.start_sync(
            tasks,
            course_id=COURSE,
            source_key="resource:1",
            resource_id=1,
            title="t",
            profiles=["sliding-window"],
            load=None,
        )
    assert not ingestion.is_syncing(COURSE, "resource:1")

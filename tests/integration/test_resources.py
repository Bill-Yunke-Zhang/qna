"""
Integration tests for course-resource ingestion (T4/T7, docs/design-rag.md
§3.2, §7, §8), against the live stack: who may manage resources, what is
refused before anything is stored, and what an ingestion actually produces
under each profile.

Access-control and validation tests need only the backend. The ingestion
tests also need Infinity and ChromaDB, and the retrieval checks Ollama with
the baseline model; they are skipped, with the reason, when those aren't
reachable (override the probe URLs with TEST_INFINITY_URL, TEST_CHROMA_URL
and TEST_OLLAMA_URL). A sync runs in the background and stays "syncing" for
CLEANUP_GRACE_S (30 s) after its new chunks go live, so those tests take a
while.
"""

from __future__ import annotations

import io
import os
import pathlib
import time
import uuid
import zipfile

import httpx
import pytest

from .conftest import admin_headers

_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
SAMPLE = _REPO_ROOT / "eval" / "sample_data"
SYLLABUS = (SAMPLE / "web" / "syllabus.html").read_bytes()
VIEW_URL = (
    "https://git.example.edu/course/-/blob/main/eval/sample_data/web/syllabus.html"
)
REPO_BASE = "https://git.example.edu/course/-/blob/main/eval/sample_data/repo"
BASELINE_MODEL = "qwen2.5:1.5b"
SYNC_TIMEOUT_S = 240


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _base(base_url: str, course_id: int) -> str:
    return f"{base_url}/api/courses/{course_id}"


def _upload(
    base_url,
    course_id,
    token,
    *,
    data=SYLLABUS,
    name="syllabus.html",
    type="SYLLABUS",
    title="Syllabus",
    link=VIEW_URL,
    profiles="sliding-window",
):
    return httpx.post(
        f"{_base(base_url, course_id)}/resources/upload",
        data={
            "type": type,
            "title": title,
            "link_base_url": link,
            "profiles": profiles,
        },
        files={"file": (name, data, "application/octet-stream")},
        headers=_headers(token),
        timeout=60.0,
    )


def _list(base_url, course_id, token) -> dict:
    r = httpx.get(
        f"{_base(base_url, course_id)}/resources", headers=_headers(token), timeout=10.0
    )
    assert r.status_code == 200, r.text
    return r.json()


def _wait_synced(base_url, course_id, token, resource_id=None) -> dict:
    """The resource (or historical Q&A) once its sync has fully ended."""
    deadline = time.monotonic() + SYNC_TIMEOUT_S
    while True:
        listing = _list(base_url, course_id, token)
        if resource_id is None:
            source = listing["historical_qa"]
        else:
            source = next(r for r in listing["resources"] if r["id"] == resource_id)
        if not source["syncing"]:
            return source
        assert time.monotonic() < deadline, (
            f"sync still running after {SYNC_TIMEOUT_S}s"
        )
        time.sleep(2)


def _syncs(source: dict) -> dict:
    return {s["profile"]: s for s in source["syncs"]}


def _reachable(url: str) -> bool:
    try:
        return httpx.get(url, timeout=3.0).status_code < 500
    except httpx.HTTPError:
        return False


@pytest.fixture(scope="module")
def rag_services():
    infinity = os.environ.get("TEST_INFINITY_URL", "http://127.0.0.1:7997/health")
    chroma = os.environ.get("TEST_CHROMA_URL", "http://127.0.0.1:8001/api/v2/heartbeat")
    missing = [
        name
        for name, url in (("Infinity", infinity), ("ChromaDB", chroma))
        if not _reachable(url)
    ]
    if missing:
        pytest.skip(f"{' and '.join(missing)} not reachable; ingestion needs them")


@pytest.fixture(scope="module")
def baseline_model(rag_services):
    url = os.environ.get("TEST_OLLAMA_URL", "http://127.0.0.1:11434")
    try:
        tags = httpx.get(f"{url}/api/tags", timeout=3.0).json().get("models", [])
    except (httpx.HTTPError, ValueError):
        pytest.skip("Ollama not reachable; retrieval checks need it")
    if not any(m.get("name", "").startswith(BASELINE_MODEL) for m in tags):
        pytest.skip(f"{BASELINE_MODEL} isn't pulled into Ollama")


@pytest.fixture()
def other_course(base_url, admin_token) -> int:
    r = httpx.post(
        f"{base_url}/api/admin/courses",
        json={"name": f"Other Course {uuid.uuid4().hex[:8]}", "semester": "Test"},
        headers=admin_headers(admin_token),
        timeout=10.0,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ── Access control ───────────────────────────────────────────────────────────


class TestResourceAccess:
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("GET", "/resources"),
            ("POST", "/resources"),
            ("POST", "/resources/upload"),
            ("POST", "/resources/1/sync"),
            ("PUT", "/resources/1/upload"),
            ("DELETE", "/resources/1"),
            ("POST", "/historical-qa/sync"),
        ],
    )
    def test_students_get_403_on_every_resource_endpoint(
        self, base_url, course_id, student_token, method, path
    ):
        r = httpx.request(
            method,
            f"{_base(base_url, course_id)}{path}",
            headers=_headers(student_token),
            timeout=10.0,
        )
        assert r.status_code == 403, r.text

    def test_unauthenticated_is_rejected(self, base_url, course_id):
        r = httpx.get(f"{_base(base_url, course_id)}/resources", timeout=10.0)
        assert r.status_code in (401, 403), r.text

    def test_staff_surface_header_cannot_unlock_it_for_a_student(
        self, base_url, course_id, student_token
    ):
        r = httpx.get(
            f"{_base(base_url, course_id)}/resources",
            headers={**_headers(student_token), "X-App-Surface": "staff"},
            timeout=10.0,
        )
        assert r.status_code == 403, r.text

    def test_student_surface_clamps_staff_to_student(
        self, base_url, course_id, staff_token
    ):
        r = httpx.get(
            f"{_base(base_url, course_id)}/resources",
            headers={**_headers(staff_token), "X-App-Surface": "student"},
            timeout=10.0,
        )
        assert r.status_code == 403, r.text

    def test_staff_of_one_course_cannot_see_another(
        self, base_url, other_course, staff_token
    ):
        # staff_token is staff in `course_id` only.
        r = httpx.get(
            f"{_base(base_url, other_course)}/resources",
            headers=_headers(staff_token),
            timeout=10.0,
        )
        assert r.status_code == 404, r.text

    def test_a_resource_cannot_be_reached_through_another_course(
        self, base_url, course_id, other_course, admin_token, staff_token
    ):
        # A non-REPO upload with bad content is refused before anything runs,
        # so register a URL resource instead: the admin is staff everywhere.
        r = httpx.post(
            f"{_base(base_url, course_id)}/resources",
            json={
                "type": "SYLLABUS",
                "title": "S",
                "fetch_url": "https://example.com/syllabus.html",
            },
            headers=_headers(staff_token),
            timeout=30.0,
        )
        assert r.status_code == 202, r.text
        rid = r.json()["id"]
        # Same resource id under the other course's path: 404, for every action.
        for method, path in (
            ("POST", f"/resources/{rid}/sync"),
            ("DELETE", f"/resources/{rid}"),
        ):
            r = httpx.request(
                method,
                f"{_base(base_url, other_course)}{path}",
                headers=_headers(admin_token),
                timeout=10.0,
            )
            assert r.status_code == 404, (method, path, r.text)
        assert any(
            x["id"] == rid for x in _list(base_url, course_id, staff_token)["resources"]
        )

    def test_unknown_course_is_404_for_admin(self, base_url, admin_token):
        r = httpx.get(
            f"{_base(base_url, 999_999_999)}/resources",
            headers=_headers(admin_token),
            timeout=10.0,
        )
        assert r.status_code == 404, r.text


# ── Refused before anything is stored ────────────────────────────────────────


class TestResourceValidation:
    @pytest.mark.parametrize(
        "body",
        [
            {
                "type": "SYLLABUS",
                "title": "S",
                "fetch_url": "http://169.254.169.254/latest/meta-data/",
            },
            {
                "type": "SYLLABUS",
                "title": "S",
                "fetch_url": "http://127.0.0.1:8000/api/health",
            },
            {"type": "SYLLABUS", "title": "S", "fetch_url": "file:///etc/passwd"},
            {
                "type": "SYLLABUS",
                "title": "S",
                "fetch_url": "https://example.com/s.html",
                "profiles": ["nope"],
            },
            {
                "type": "SYLLABUS",
                "title": "S",
                "fetch_url": "https://example.com/s.html",
                "profiles": [],
            },
            {
                "type": "REPO",
                "title": "R",
                "fetch_url": "https://git.doit.wisc.edu/course/repo",
            },
            {
                "type": "REPO",
                "title": "R",
                "fetch_url": "https://github.com/course/repo",
                "repo_branch": "main",
            },
            {
                "type": "REPO",
                "title": "R",
                "fetch_url": "http://git.doit.wisc.edu/course/repo",
                "repo_branch": "main",
            },
            {
                "type": "REPO",
                "title": "R",
                "fetch_url": "https://git.doit.wisc.edu/course/repo",
                "repo_branch": "--upload-pack=x",
            },
            {
                "type": "SYLLABUS",
                "title": "S",
                "fetch_url": "https://example.com/s.html",
                "repo_branch": "main",
            },
        ],
        ids=[
            "cloud-metadata",
            "loopback",
            "file-scheme",
            "unknown-profile",
            "no-profiles",
            "repo-no-branch",
            "repo-other-host",
            "repo-http",
            "repo-option-branch",
            "branch-on-page",
        ],
    )
    def test_bad_registrations_are_422_and_store_nothing(
        self, base_url, course_id, staff_token, body
    ):
        r = httpx.post(
            f"{_base(base_url, course_id)}/resources",
            json=body,
            headers=_headers(staff_token),
            timeout=30.0,
        )
        assert r.status_code == 422, r.text
        assert _list(base_url, course_id, staff_token)["resources"] == []

    def _zip(self, files: dict[str, bytes]) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for name, data in files.items():
                z.writestr(name, data)
        return buf.getvalue()

    @pytest.mark.parametrize(
        "upload",
        [
            {"name": "notes.txt", "data": b"plain text"},
            {"name": "syllabus.html", "data": b"<main><p>too short</p></main>"},
            {"name": "page.md", "data": b"# A page\nText", "type": "SYLLABUS"},
            {"name": "page.html", "data": SYLLABUS, "link": "javascript:alert(1)"},
            {"name": "repo.zip", "data": "zip-traversal", "type": "REPO"},
            {"name": "repo.zip", "data": "zip-no-docs", "type": "REPO"},
            {"name": "repo.zip", "data": b"not a zip", "type": "REPO"},
            {"name": "slides.pdf", "data": b"%PDF-1.7 broken", "type": "REPO"},
            {"name": "page.html", "data": SYLLABUS, "profiles": "sliding-window,nope"},
        ],
        ids=[
            "wrong-type",
            "empty-page",
            "md-as-syllabus",
            "js-link",
            "zip-traversal",
            "zip-no-md-or-pdf",
            "bad-zip",
            "broken-pdf",
            "unknown-profile",
        ],
    )
    def test_bad_uploads_are_422_and_store_nothing(
        self, base_url, course_id, staff_token, upload
    ):
        upload = dict(upload)
        if upload["data"] == "zip-traversal":
            upload["data"] = self._zip({"../evil.md": b"# Evil\nText"})
        elif upload["data"] == "zip-no-docs":
            upload["data"] = self._zip({"notes.txt": b"text"})
        r = _upload(base_url, course_id, staff_token, **upload)
        assert r.status_code == 422, r.text
        assert _list(base_url, course_id, staff_token)["resources"] == []

    def test_listing_names_every_profile_and_the_live_one(
        self, base_url, course_id, staff_token
    ):
        listing = _list(base_url, course_id, staff_token)
        assert {
            "sliding-window",
            "type-tailored",
            "embedding-alt",
            "embedding-cls",
        } <= set(listing["profiles"])
        assert listing["live_profile"] in listing["profiles"]
        assert listing["resources"] == []
        assert listing["historical_qa"] == {
            "syncing": False,
            "version_mismatch": False,
            "syncs": [],
        }


# ── Ingestion (needs Infinity and ChromaDB) ──────────────────────────────────


@pytest.mark.usefixtures("rag_services")
class TestIngestion:
    def test_upload_ingests_under_each_requested_profile(
        self, base_url, course_id, staff_token
    ):
        r = _upload(
            base_url, course_id, staff_token, profiles="sliding-window,type-tailored"
        )
        assert r.status_code == 202, r.text
        body = r.json()
        assert body["origin"] == "UPLOAD" and body["link_base_url"] == VIEW_URL
        assert body["syncing"] is True

        source = _wait_synced(base_url, course_id, staff_token, body["id"])
        syncs = _syncs(source)
        assert set(syncs) == {"sliding-window", "type-tailored"}
        for s in syncs.values():
            assert s["last_error"] is None and s["last_synced_at"] is not None
            assert s["chunk_count"] > 5
        assert source["version_mismatch"] is False
        # Different fallback chunkers give different chunks of the same page.
        assert (
            syncs["sliding-window"]["chunk_count"]
            != syncs["type-tailored"]["chunk_count"]
        )

    def test_replace_keeps_the_resource_and_its_profiles(
        self, base_url, course_id, staff_token
    ):
        r = _upload(base_url, course_id, staff_token, profiles="sliding-window")
        rid = r.json()["id"]
        first = _syncs(_wait_synced(base_url, course_id, staff_token, rid))[
            "sliding-window"
        ]

        # A URL re-sync is refused for an upload; a new file is the way.
        r = httpx.post(
            f"{_base(base_url, course_id)}/resources/{rid}/sync",
            json={},
            headers=_headers(staff_token),
        )
        assert r.status_code == 409, r.text

        page = (
            "<html><body><main><h1>Office hours</h1><h2>Where</h2><p>"
            + "Office hours are on Tuesdays from 2 to 4 pm in room 1240. " * 12
            + "</p></main></body></html>"
        ).encode()
        r = httpx.put(
            f"{_base(base_url, course_id)}/resources/{rid}/upload",
            files={"file": ("page.html", page, "text/html")},
            headers=_headers(staff_token),
            timeout=60.0,
        )
        assert r.status_code == 202, r.text
        assert r.json()["id"] == rid

        after = _wait_synced(base_url, course_id, staff_token, rid)
        # The default for a replacement is the profiles it already had.
        assert set(_syncs(after)) == {"sliding-window"}
        second = _syncs(after)["sliding-window"]
        assert second["last_error"] is None
        assert second["chunk_count"] < first["chunk_count"]
        assert len(_list(base_url, course_id, staff_token)["resources"]) == 1

    def test_repo_zip_ingests_markdown_and_pdf(self, base_url, course_id, staff_token):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for path in sorted((SAMPLE / "repo").rglob("*")):
                if path.is_file():
                    z.write(path, path.relative_to(SAMPLE / "repo").as_posix())
        r = _upload(
            base_url,
            course_id,
            staff_token,
            data=buf.getvalue(),
            name="repo.zip",
            type="REPO",
            title="Course repo",
            link=REPO_BASE,
            profiles="sliding-window,type-tailored",
        )
        assert r.status_code == 202, r.text
        syncs = _syncs(_wait_synced(base_url, course_id, staff_token, r.json()["id"]))
        assert syncs["sliding-window"]["last_error"] is None
        assert syncs["type-tailored"]["last_error"] is None
        # 5 markdown files and a 19-page deck: type-tailored keeps the PDF's
        # pages apart, so it can't have fewer chunks.
        assert syncs["sliding-window"]["chunk_count"] > 19
        assert (
            syncs["type-tailored"]["chunk_count"]
            >= syncs["sliding-window"]["chunk_count"]
        )

    def test_a_second_sync_of_the_same_source_is_409(
        self, base_url, course_id, staff_token
    ):
        r = _upload(base_url, course_id, staff_token, profiles="sliding-window")
        rid = r.json()["id"]
        r = httpx.put(
            f"{_base(base_url, course_id)}/resources/{rid}/upload",
            files={"file": ("syllabus.html", SYLLABUS, "text/html")},
            headers=_headers(staff_token),
            timeout=60.0,
        )
        assert r.status_code == 409, r.text
        # And it can't be deleted mid-sync either.
        r = httpx.delete(
            f"{_base(base_url, course_id)}/resources/{rid}",
            headers=_headers(staff_token),
        )
        assert r.status_code == 409, r.text
        _wait_synced(base_url, course_id, staff_token, rid)

    def test_delete_removes_the_resource(self, base_url, course_id, staff_token):
        rid = _upload(base_url, course_id, staff_token).json()["id"]
        _wait_synced(base_url, course_id, staff_token, rid)
        r = httpx.delete(
            f"{_base(base_url, course_id)}/resources/{rid}",
            headers=_headers(staff_token),
        )
        assert r.status_code == 204, r.text
        assert _list(base_url, course_id, staff_token)["resources"] == []
        r = httpx.delete(
            f"{_base(base_url, course_id)}/resources/{rid}",
            headers=_headers(staff_token),
        )
        assert r.status_code == 404, r.text

    def test_reindex_indexes_threads_with_an_accepted_human_answer(
        self, base_url, course_id, staff_token, student_token, category_id
    ):
        def ask(title):
            r = httpx.post(
                f"{_base(base_url, course_id)}/questions",
                json={
                    "title": title,
                    "body": f"{title}? Asking for my project.",
                    "category_ids": [category_id],
                },
                headers=_headers(student_token),
            )
            assert r.status_code == 201, r.text
            return r.json()["id"]

        def answer(qid, accept):
            r = httpx.post(
                f"{_base(base_url, course_id)}/questions/{qid}/posts",
                json={
                    "kind": "ANSWER",
                    "body": "Use docker compose down -v, then up --build.",
                },
                headers=_headers(staff_token),
            )
            assert r.status_code == 201, r.text
            if accept:
                pid = r.json()["posts"][-1]["id"]
                r = httpx.patch(
                    f"{_base(base_url, course_id)}/questions/{qid}/posts/{pid}/accept",
                    json={"is_accepted": True},
                    headers=_headers(staff_token),
                )
                assert r.status_code == 200, r.text

        answer(ask("How do I reset my database"), accept=True)
        answer(ask("Is this answered but unverified"), accept=False)
        ask("Nobody answered this one")

        r = httpx.post(
            f"{_base(base_url, course_id)}/historical-qa/sync",
            json={"profiles": ["sliding-window"]},
            headers=_headers(staff_token),
        )
        assert r.status_code == 202, r.text
        qa = _syncs(_wait_synced(base_url, course_id, staff_token))["sliding-window"]
        assert qa["last_error"] is None
        # One chunk per thread with an accepted answer, never split.
        assert qa["chunk_count"] == 1


# ── Retrieval sees the ingested content, and only this course's ──────────────


@pytest.mark.usefixtures("baseline_model")
class TestIngestedContentIsRetrievable:
    COMPARE = {
        "question": "How many slip days does each student get?",
        "ingestion_profile": "sliding-window",
        "similarity_threshold": 0.3,
        "system_prompt": "Only use the information provided in the tagged context to answer questions.",
        "generation_model": BASELINE_MODEL,
    }

    def test_compare_retrieves_from_the_upload_and_courses_stay_apart(
        self, base_url, course_id, other_course, staff_token, admin_token
    ):
        rid = _upload(base_url, course_id, staff_token).json()["id"]
        _wait_synced(base_url, course_id, staff_token, rid)

        r = httpx.post(
            f"{_base(base_url, course_id)}/rag/compare",
            json=self.COMPARE,
            headers=_headers(staff_token),
            timeout=180.0,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["matched"] is True and body["answer"]
        assert body["retrieved_chunks"]
        assert all(c["source_url"] == VIEW_URL for c in body["retrieved_chunks"])
        assert all(c["resource_type"] == "syllabus" for c in body["retrieved_chunks"])

        # The other course has nothing ingested: an explicit 404, never a
        # silent no-match and never this course's chunks.
        r = httpx.post(
            f"{_base(base_url, other_course)}/rag/compare",
            json=self.COMPARE,
            headers=_headers(admin_token),
            timeout=60.0,
        )
        assert r.status_code == 404, r.text

    def test_deleted_content_is_no_longer_retrieved(
        self, base_url, course_id, staff_token
    ):
        rid = _upload(base_url, course_id, staff_token).json()["id"]
        _wait_synced(base_url, course_id, staff_token, rid)
        r = httpx.delete(
            f"{_base(base_url, course_id)}/resources/{rid}",
            headers=_headers(staff_token),
        )
        assert r.status_code == 204, r.text
        r = httpx.post(
            f"{_base(base_url, course_id)}/rag/compare",
            json=self.COMPARE,
            headers=_headers(staff_token),
            timeout=180.0,
        )
        # The collection exists but has no current sync left.
        assert r.status_code == 404 or r.json()["retrieved_chunks"] == [], r.text

"""
Session-level fixtures for the QnA integration test suite.

Stack lifecycle
---------------
The `docker_stack` fixture detects whether the stack is already running
(by calling /api/health). If it is, nothing is started or stopped — the
dev stack is used as-is. If it is not, `docker compose up -d --build` is
run from the repo root and `docker compose down` is called on teardown.

Test isolation
--------------
Every test gets a freshly-created course (via the `course_id` fixture), so
category-name collisions and question lists don't leak between tests.
Courses have no DELETE endpoint, so they're left as inert records — same
convention as the rest of this course's projects.
"""
from __future__ import annotations

import logging
import pathlib
import subprocess
import time
import uuid

import httpx
import pytest

logger = logging.getLogger(__name__)

_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent


# ---------------------------------------------------------------------------
# pytest options
# ---------------------------------------------------------------------------


def pytest_addoption(parser):
    parser.addoption(
        "--base-url",
        default="http://localhost:8000",
        help="Backend base URL (default: http://localhost:8000)",
    )


@pytest.fixture(scope="session")
def base_url(request) -> str:
    return request.config.getoption("--base-url").rstrip("/")


# ---------------------------------------------------------------------------
# Docker stack lifecycle
# ---------------------------------------------------------------------------


def _is_healthy(url: str) -> bool:
    try:
        r = httpx.get(f"{url}/api/health", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


def _wait_healthy(url: str, timeout: int = 120) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _is_healthy(url):
            return
        time.sleep(2)
    raise RuntimeError(
        f"Stack at {url} did not become healthy within {timeout}s. "
        "Check `docker compose logs backend`."
    )


@pytest.fixture(scope="session")
def docker_stack(base_url: str):
    already_running = _is_healthy(base_url)

    if not already_running:
        logger.info("Stack not detected — running docker compose up --build")
        subprocess.run(["docker", "compose", "up", "-d", "--build"], check=True, cwd=_REPO_ROOT)
        logger.info("Waiting for stack to become healthy…")
        _wait_healthy(base_url)
        logger.info("Stack is healthy")

    yield

    if not already_running:
        logger.info("Tearing down stack started by this session")
        subprocess.run(["docker", "compose", "down"], check=True, cwd=_REPO_ROOT)


# ---------------------------------------------------------------------------
# Admin token (session-scoped — one login for the whole session)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def admin_token(docker_stack, base_url: str) -> str:
    """Log in as the bootstrap admin. Credentials come from .env / environment."""
    import os

    env_path = _REPO_ROOT / ".env"
    env_vars: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env_vars[k.strip()] = v.strip()

    username = env_vars.get("ADMIN_USERNAME") or os.environ.get("ADMIN_USERNAME", "admin")
    password = env_vars.get("ADMIN_PASSWORD") or os.environ.get("ADMIN_PASSWORD", "change_me_admin")

    r = httpx.post(
        f"{base_url}/api/auth/login",
        json={"username": username, "password": password},
        timeout=10.0,
    )
    assert r.status_code == 200, (
        f"Admin login failed ({r.status_code}): {r.text}\n"
        f"Set ADMIN_USERNAME / ADMIN_PASSWORD in .env or environment."
    )
    token = r.json().get("access_token")
    assert token, "Login response missing access_token"
    return token


def admin_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Dev-only netid login helper — mints a distinct STUDENT or STAFF identity
# and grants it course access, using the same dev fallback the frontend uses.
# ---------------------------------------------------------------------------


def login_as_netid(base_url: str, admin_token: str, course_id: int, role: str) -> str:
    netid = f"test-{role.lower()}-{uuid.uuid4().hex[:8]}"

    r = httpx.post(f"{base_url}/api/auth/login", json={"netid": netid}, timeout=10.0)
    assert r.status_code == 200, f"netid login failed: {r.text}"
    temp_token = r.json()["temp_token"]

    r = httpx.post(
        f"{base_url}/api/auth/exchange-temp",
        headers={"Authorization": f"Bearer {temp_token}"},
        timeout=10.0,
    )
    assert r.status_code == 200, f"exchange-temp failed: {r.text}"
    access_token = r.json()["access_token"]

    r = httpx.get(f"{base_url}/api/admin/users", headers=admin_headers(admin_token), timeout=10.0)
    assert r.status_code == 200
    user = next(u for u in r.json() if u["netid"] == netid)

    r = httpx.post(
        f"{base_url}/api/admin/users/{user['id']}/course-access",
        json={"course_id": course_id, "role": role},
        headers=admin_headers(admin_token),
        timeout=10.0,
    )
    assert r.status_code == 204, f"grant course-access failed: {r.text}"

    return access_token


@pytest.fixture()
def course_id(docker_stack, base_url: str, admin_token: str) -> int:
    tag = uuid.uuid4().hex[:8]
    r = httpx.post(
        f"{base_url}/api/admin/courses",
        json={"name": f"Test Course {tag}", "semester": "Test"},
        headers=admin_headers(admin_token),
        timeout=10.0,
    )
    assert r.status_code == 201, f"Create course failed: {r.text}"
    return r.json()["id"]


@pytest.fixture()
def student_token(base_url: str, admin_token: str, course_id: int) -> str:
    return login_as_netid(base_url, admin_token, course_id, "STUDENT")


@pytest.fixture()
def staff_token(base_url: str, admin_token: str, course_id: int) -> str:
    return login_as_netid(base_url, admin_token, course_id, "STAFF")


@pytest.fixture()
def category_id(base_url: str, course_id: int, staff_token: str) -> int:
    """A default category for tests that need one to post a question but
    aren't themselves testing category behavior (every question requires
    at least one category — see QuestionCreate.category_ids)."""
    r = httpx.post(
        f"{base_url}/api/courses/{course_id}/categories",
        json={"name": "General", "description": "Default test category"},
        headers={"Authorization": f"Bearer {staff_token}"},
        timeout=10.0,
    )
    assert r.status_code == 201, f"Create category failed: {r.text}"
    return r.json()["id"]

"""
Unit tests for cloning a repository registered by URL (docs/design-rag.md
§3.2, §7.4, §8): the project URL and branch checks, the git environment
that carries the token, and `clone_repo` against a local git repository
standing in for GitLab.

The clone tests need the `git` binary and are skipped without it (the CI
image, python:3.12-slim, has none; the backend image does).
"""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from app.config import settings
from app.services.rag import fetchers, ingestion
from app.services.rag.fetchers import FetchError

HOST = settings.GITLAB_HOST
needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


# ── Project URL and branch ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "pasted",
    [
        f"https://{HOST}/course/repo",
        f"https://{HOST}/course/repo/",
        f"https://{HOST}/course/repo.git",
        f"https://{HOST}/course/repo/-/tree/main/docs",
        f"  https://{HOST}/course/repo?tab=readme  ",
    ],
)
def test_project_url_is_normalized(pasted):
    assert fetchers.gitlab_project_url(pasted) == f"https://{HOST}/course/repo"


def test_nested_groups_are_kept():
    url = f"https://{HOST}/cdis/cs/courses/fa26/repo"
    assert fetchers.gitlab_project_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        f"http://{HOST}/course/repo",  # the token never goes over http
        "https://github.com/course/repo",
        f"https://{HOST}.evil.example/course/repo",
        f"https://user:pw@{HOST}/course/repo",
        f"https://{HOST}:8443/course/repo",
        f"https://{HOST}/repo",  # no group
        f"https://{HOST}/course/../repo",
        f"ssh://git@{HOST}/course/repo.git",
    ],
)
def test_other_urls_are_refused(url):
    with pytest.raises(FetchError):
        fetchers.gitlab_project_url(url)


@pytest.mark.parametrize("branch", ["main", "release/1.2", "fa26-p3", "v_2"])
def test_ordinary_branches_pass(branch):
    fetchers.check_branch(branch)


@pytest.mark.parametrize(
    "branch",
    ["", "-u", "--upload-pack=x", "a..b", "a//b", "/main", "main/", "a b", "a.lock."],
)
def test_odd_branches_are_refused(branch):
    with pytest.raises(FetchError):
        fetchers.check_branch(branch)


def test_blob_base_links_the_branch():
    assert (
        fetchers.repo_blob_base(f"https://{HOST}/c/r", "release/1 2")
        == f"https://{HOST}/c/r/-/blob/release/1%202"
    )


# ── The git environment ──────────────────────────────────────────────────────


def config_of(env: dict[str, str]) -> dict[str, str]:
    return {
        env[f"GIT_CONFIG_KEY_{i}"]: env[f"GIT_CONFIG_VALUE_{i}"]
        for i in range(int(env["GIT_CONFIG_COUNT"]))
    }


def test_token_goes_in_a_header_scoped_to_the_gitlab_host(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "GITLAB_ACCESS_TOKEN", "glpat-test-only")
    env = fetchers._git_env(str(tmp_path))
    config = config_of(env)

    basic = base64.b64encode(b"oauth2:glpat-test-only").decode()
    assert (
        config[f"http.https://{HOST}/.extraHeader"] == f"Authorization: Basic {basic}"
    )
    assert "http.extraHeader" not in config  # unscoped would follow redirects
    assert config["http.followRedirects"] == "false"
    assert config["protocol.allow"] == "never"
    assert config["protocol.https.allow"] == "always"
    assert env["GIT_TERMINAL_PROMPT"] == "0" and env["GIT_CONFIG_NOSYSTEM"] == "1"
    # Nothing from the backend's own environment leaks in (no other secrets).
    assert set(env) <= {"PATH", "HOME", "LC_ALL"} | {
        k for k in env if k.startswith("GIT_")
    }


def test_no_token_means_no_header(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "GITLAB_ACCESS_TOKEN", "")
    assert not any(
        "extraHeader" in k for k in config_of(fetchers._git_env(str(tmp_path)))
    )


def test_errors_never_show_the_token(monkeypatch):
    monkeypatch.setattr(settings, "GITLAB_ACCESS_TOKEN", "glpat-test-only")
    basic = base64.b64encode(b"oauth2:glpat-test-only").decode()
    text = fetchers._scrub(f"fatal: glpat-test-only and Basic {basic}")
    assert "glpat-test-only" not in text and basic not in text


# ── clone_repo against a local repository ────────────────────────────────────


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env={
            "PATH": os.environ["PATH"],
            "HOME": str(cwd),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@x",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@x",
        },
    ).stdout


@pytest.fixture
def local_remote(tmp_path, monkeypatch):
    """
    A bare repo at `{tmp}/course/repo.git` with a `main` branch, served over
    file:// for the test only (the real environment allows https alone).
    Returns the "project URL" to pass to clone_repo.
    """
    work = tmp_path / "work"
    work.mkdir()
    git(work, "init", "-q", "-b", "main")
    (work / "docs").mkdir()
    (work / "README.md").write_text("# Course\nWelcome.\n")
    (work / "docs" / "setup.md").write_text("# Setup\nRun make.\n")
    (work / "notes.txt").write_text("not ingested")
    (work / "secret.md").symlink_to("/etc/hosts")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "init")
    bare = tmp_path / "course" / "repo.git"
    bare.parent.mkdir()
    git(tmp_path, "clone", "-q", "--bare", str(work), str(bare))
    git(bare, "config", "uploadpack.allowFilter", "true")

    real_env = fetchers._git_env

    def env_with_file_protocol(home):
        env = real_env(home)
        n = int(env["GIT_CONFIG_COUNT"])
        env[f"GIT_CONFIG_KEY_{n}"] = "protocol.file.allow"
        env[f"GIT_CONFIG_VALUE_{n}"] = "always"
        env["GIT_CONFIG_COUNT"] = str(n + 1)
        return env

    monkeypatch.setattr(fetchers, "_git_env", env_with_file_protocol)
    return f"file://{tmp_path}/course/repo", git(work, "rev-parse", "HEAD").strip()


@needs_git
async def test_clone_reads_md_and_pdf_files_and_skips_symlinks(local_remote):
    url, sha = local_remote
    repo = await fetchers.clone_repo(url, "main")
    assert repo.commit_sha == sha
    assert {f.path: f.data for f in repo.files} == {
        "README.md": b"# Course\nWelcome.\n",
        "docs/setup.md": b"# Setup\nRun make.\n",
    }


@needs_git
async def test_a_missing_branch_is_a_fetch_error(local_remote):
    url, _ = local_remote
    with pytest.raises(FetchError, match="git clone failed"):
        await fetchers.clone_repo(url, "no-such-branch")


@needs_git
async def test_clone_limits_apply(local_remote, monkeypatch):
    url, _ = local_remote
    monkeypatch.setattr(settings, "UPLOAD_MAX_FILES", 1)
    with pytest.raises(FetchError, match="more than 1 .md and .pdf files"):
        await fetchers.clone_repo(url, "main")
    monkeypatch.setattr(settings, "UPLOAD_MAX_FILES", 500)
    monkeypatch.setattr(settings, "UPLOAD_MAX_ENTRY_BYTES", 5)
    with pytest.raises(FetchError, match="README.md is larger than"):
        await fetchers.clone_repo(url, "main")


@needs_git
async def test_repo_loader_links_the_branch_and_records_the_commit(
    local_remote, monkeypatch
):
    url, sha = local_remote
    real_clone = fetchers.clone_repo

    async def clone_local(project_url, branch):
        assert project_url == f"https://{HOST}/course/repo"
        return await real_clone(url, branch)

    monkeypatch.setattr(fetchers, "clone_repo", clone_local)
    resource = type(
        "R",
        (),
        {
            "origin": "URL",
            "type": "REPO",
            "repo_branch": "main",
            "fetch_url": f"https://{HOST}/course/repo",
        },
    )()
    docs = await ingestion.repo_loader(resource)()
    readme = next(d for d in docs if d.key == "README.md")
    assert readme.commit_sha == sha
    loc = readme.locate(
        ingestion.Chunk(readme.sections[0].start, readme.sections[0].end, (), 1)
    )
    assert loc["source_url"] == f"https://{HOST}/course/repo/-/blob/main/README.md"
    assert loc["commit_sha"] == sha

"""
Prepare a deployment for the T6 harness: ingest eval/sample_data/ into the
eval course under every profile eval/configs.json names, re-index the
course's historical Q&A, wait for every sync, then check /rag/health
(docs/design-rag.md §3.2, §10; deployment_instructions.md Part 8, step 5).

Run it after the first deploy (and after `scripts/seed_demo.py`, which seeds
the threads q12 and q13 expect) and again whenever the eval data or a
profile changes. It's safe to re-run: a resource that already exists is
replaced in place (same id, no duplicates), and unchanged content isn't
re-embedded.

    HARNESS_BASE_URL=http://<static-ip> HARNESS_ADMIN_PASSWORD='<VM admin password>' \\
        python scripts/ingest_eval.py

Like eval/compare_harness.py, settings come from HARNESS_<KEY> variables,
then .env, then defaults: BASE_URL, ADMIN_USERNAME, ADMIN_PASSWORD. The eval
course is the seeded "AI-Assisted Software Development" unless
--course-id is given. The course id to put in eval/configs.json is printed
at the end. Pulling the generation models is still a step on the VM
(`ollama pull`); /rag/health reports any that are missing.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
import zipfile
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE = REPO_ROOT / "eval" / "sample_data"
CONFIGS = REPO_ROOT / "eval" / "configs.json"
EVAL_COURSE_NAME = "AI-Assisted Software Development"
# Where the eval files are viewed: their GitLab blob URLs, so every chunk's
# source_url contains the eval/sample_data/... path the harness checks (§3.2).
BLOB_BASE = (
    "https://git.doit.wisc.edu/cdis/cs/courses/aicoding/fa26/student-repos/p3/"
    "qna-69/-/blob/main/eval/sample_data"
)
# gte-Qwen2 on 4 CPUs is slow; one source under all profiles can take a while.
SYNC_TIMEOUT_S = 45 * 60

OVERRIDES = {
    k[len("HARNESS_") :]: v for k, v in os.environ.items() if k.startswith("HARNESS_")
}


def env_value(key: str, default: str) -> str:
    """HARNESS_<KEY>, then .env, then the environment, then `default`."""
    if key in OVERRIDES:
        return OVERRIDES[key]
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                if k.strip() == key:
                    return v.strip()
    return os.environ.get(key, default)


def fail(message: str) -> None:
    print(f"✗ {message}", file=sys.stderr)
    sys.exit(1)


def repo_zip() -> bytes:
    """eval/sample_data/repo/ as a zip of its contents (no leading repo/)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted((SAMPLE / "repo").rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(SAMPLE / "repo").as_posix())
    return buf.getvalue()


def eval_sources(blob_base: str) -> list[dict]:
    """The three resources §3.2 uploads, each as its real type."""
    return [
        {
            "title": "Syllabus (eval snapshot)",
            "type": "SYLLABUS",
            "file": ("syllabus.html", (SAMPLE / "web" / "syllabus.html").read_bytes()),
            "link": f"{blob_base}/web/syllabus.html",
        },
        {
            "title": "Schedule (eval snapshot)",
            "type": "SCHEDULE",
            "file": ("schedule.html", (SAMPLE / "web" / "schedule.html").read_bytes()),
            "link": f"{blob_base}/web/schedule.html",
        },
        {
            "title": "Course repo (eval snapshot)",
            "type": "REPO",
            "file": ("repo.zip", repo_zip()),
            "link": f"{blob_base}/repo",
        },
    ]


def configs_profiles_and_models() -> tuple[list[str], list[str]]:
    config = json.loads(CONFIGS.read_text())
    runs = [config["baseline"], *config.get("comparisons", [])]
    profiles = list(
        dict.fromkeys(r["ingestion_profile"] for r in runs if "ingestion_profile" in r)
    )
    models = list(
        dict.fromkeys(r["generation_model"] for r in runs if "generation_model" in r)
    )
    return profiles, models


def login(client: httpx.Client, base_url: str) -> None:
    username = env_value("ADMIN_USERNAME", "admin")
    password = env_value("ADMIN_PASSWORD", "change_me_admin")
    r = client.post(
        f"{base_url}/api/auth/login", json={"username": username, "password": password}
    )
    if r.status_code != 200:
        fail(f"admin login failed ({r.status_code}); set HARNESS_ADMIN_PASSWORD")
    client.headers["Authorization"] = f"Bearer {r.json()['access_token']}"


def find_course(client: httpx.Client, base_url: str, course_id: int | None) -> int:
    r = client.get(f"{base_url}/api/admin/courses")
    r.raise_for_status()
    courses = r.json()
    if course_id is not None:
        if not any(c["id"] == course_id for c in courses):
            fail(f"course {course_id} doesn't exist")
        return course_id
    matches = [c for c in courses if c["name"] == EVAL_COURSE_NAME]
    if not matches:
        fail(
            f'no "{EVAL_COURSE_NAME}" course: run scripts/seed_demo.py first, or pass --course-id'
        )
    if len(matches) > 1:
        ids = ", ".join(str(c["id"]) for c in matches)
        fail(f'several "{EVAL_COURSE_NAME}" courses ({ids}): pass --course-id')
    return matches[0]["id"]


def upload(client, base, existing, source, profiles) -> int:
    """Create the resource, or replace the file of the one with this title."""
    current = existing.get(source["title"])
    data = {"profiles": ",".join(profiles)}
    files = {"file": source["file"]}
    if current is None:
        r = client.post(
            f"{base}/resources/upload",
            data={
                **data,
                "type": source["type"],
                "title": source["title"],
                "link_base_url": source["link"],
            },
            files=files,
        )
        action = "uploaded"
    else:
        r = client.put(
            f"{base}/resources/{current['id']}/upload", data=data, files=files
        )
        action = "replaced"
    if r.status_code == 409:
        fail(f"{source['title']} is already syncing; wait for it and re-run")
    if r.status_code != 202:
        fail(f"{source['title']}: {r.status_code} {r.text[:300]}")
    print(f"  → {action} {source['title']} (resource {r.json()['id']})")
    return r.json()["id"]


def wait_for_syncs(client, base, resource_ids) -> dict:
    deadline = time.monotonic() + SYNC_TIMEOUT_S
    while True:
        r = client.get(f"{base}/resources")
        r.raise_for_status()
        listing = r.json()
        sources = {
            res["id"]: res for res in listing["resources"] if res["id"] in resource_ids
        }
        busy = [s["title"] for s in sources.values() if s["syncing"]]
        if listing["historical_qa"]["syncing"]:
            busy.append("Past Q&A")
        if not busy:
            return listing
        if time.monotonic() > deadline:
            fail(f"still syncing after {SYNC_TIMEOUT_S // 60} min: {', '.join(busy)}")
        print(f"    syncing: {', '.join(busy)}", flush=True)
        time.sleep(15)


def report(listing, resource_ids, profiles) -> bool:
    ok = True
    rows = [r for r in listing["resources"] if r["id"] in resource_ids]
    rows.append({"title": "Past Q&A", **listing["historical_qa"]})
    print(f"\n  {'source':32} " + " ".join(f"{p:>15}" for p in profiles))
    for source in rows:
        syncs = {s["profile"]: s for s in source["syncs"]}
        cells = []
        for p in profiles:
            s = syncs.get(p)
            if s is None or s["last_error"]:
                ok = False
                cells.append(f"{'ERROR' if s else 'missing':>15}")
            else:
                cells.append(f"{s['chunk_count']:>15}")
        print(f"  {source['title'][:32]:32} " + " ".join(cells))
        for p, s in syncs.items():
            if s["last_error"]:
                print(f"    ✗ {p}: {s['last_error']}")
        if source["version_mismatch"]:
            ok = False
            print("    ✗ profiles hold different versions; re-run")
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--course-id", type=int, help="the eval course (default: the seeded one)"
    )
    parser.add_argument(
        "--profiles",
        help="comma-separated (default: every profile in eval/configs.json)",
    )
    parser.add_argument(
        "--blob-base", default=BLOB_BASE, help="where the eval files are viewed"
    )
    args = parser.parse_args()

    base_url = env_value("BASE_URL", "http://localhost:8000").rstrip("/")
    config_profiles, models = configs_profiles_and_models()
    profiles = args.profiles.split(",") if args.profiles else config_profiles

    with httpx.Client(timeout=120) as client:
        login(client, base_url)
        course_id = find_course(client, base_url, args.course_id)
        base = f"{base_url}/api/courses/{course_id}"
        print(f"→ {base_url}, course {course_id}, profiles {', '.join(profiles)}")

        r = client.get(f"{base}/resources")
        r.raise_for_status()
        existing = {res["title"]: res for res in r.json()["resources"]}
        resource_ids = {
            upload(client, base, existing, s, profiles)
            for s in eval_sources(args.blob_base)
        }

        r = client.post(f"{base}/historical-qa/sync", json={"profiles": profiles})
        if r.status_code not in (202, 409):
            fail(f"Q&A re-index: {r.status_code} {r.text[:300]}")
        print("  → re-indexing past Q&A")

        print("→ waiting for the syncs (gte-Qwen2 on CPU takes a while)")
        ok = report(wait_for_syncs(client, base, resource_ids), resource_ids, profiles)

        r = client.get(
            f"{base}/rag/health",
            params={
                "profiles": ",".join(profiles),
                "generation_models": ",".join(models),
            },
        )
        if r.status_code == 200:
            health = r.json()
            print(f"\n→ /rag/health: {'ok' if health['ok'] else 'problems'}")
            for problem in health["problems"]:
                print(f"    ✗ {problem}")
            ok = ok and health["ok"]
        else:
            print(f"\n✗ /rag/health returned {r.status_code}")
            ok = False

    configured = json.loads(CONFIGS.read_text()).get("course_id")
    print(
        f"\n→ eval course id: {course_id}"
        + (
            ""
            if configured == course_id
            else f"  (eval/configs.json says {configured}: update it)"
        )
    )
    if not ok:
        sys.exit(1)
    print("✓ ready for eval/compare_harness.py")


if __name__ == "__main__":
    main()

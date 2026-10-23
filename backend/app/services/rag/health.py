"""
Whether a course's RAG setup can answer right now (docs/design-rag.md §5.1,
§5.4, §10), for `GET /api/courses/{course_id}/rag/health`.

Checked: the three services are up; every profile asked about (the live one,
any the request names, e.g. the eval profiles from eval/configs.json, and
every profile the course has content under) has a collection built with the
current profile definition, its embedding model loaded in Infinity, its
sources synced without errors and historical Q&A indexed; every generation
model asked about (the live one and any the request names) is pulled; and no
source is on different versions across profiles.

Never raises for a problem it finds: each becomes a line in `problems`, and
`ok` is true only when there are none. That's the "green" the deploy and
grading checklists wait for (§10).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import settings
from ...models import IndexSync
from ...models.resource import HISTORICAL_QA_SOURCE_KEY
from . import clients
from .profiles import PROFILES


async def course_health(
    db: AsyncSession,
    course_id: int,
    profiles: Sequence[str] = (),
    generation_models: Sequence[str] = (),
) -> dict[str, Any]:
    services = await clients.health()
    rows = list(
        await db.scalars(select(IndexSync).where(IndexSync.course_id == course_id))
    )
    by_profile: dict[str, list[IndexSync]] = defaultdict(list)
    for row in rows:
        by_profile[row.profile].append(row)

    problems = [
        f"{name} is unreachable: {s.get('error', 'no detail')}"
        for name, s in services.items()
        if not s.get("ok")
    ]
    names = list(
        dict.fromkeys([settings.RAG_LIVE_PROFILE, *profiles, *sorted(by_profile)])
    )
    profile_reports = []
    for name in names:
        report = await _profile_health(
            course_id, name, by_profile.get(name, []), services
        )
        profile_reports.append(report)
        problems += [f"profile {name!r}: {p}" for p in report["problems"]]

    models = list(dict.fromkeys([settings.RAG_LIVE_MODEL, *generation_models]))
    model_reports = [_model_health(m, services["ollama"]) for m in models]
    problems += [
        f"generation model {m['model']!r} isn't pulled into Ollama"
        for m in model_reports
        if m["pulled"] is False
    ]

    mismatched = _version_mismatches(rows)
    problems += [
        f"{key} is on different versions across profiles; re-sync it under all of them"
        for key in mismatched
    ]

    live_profile = profile_reports[0]
    live_model = model_reports[0]
    live_problems = [
        f"profile {live_profile['name']!r}: {p}" for p in live_profile["problems"]
    ]
    if live_model["pulled"] is not True:
        live_problems.append(f"model {live_model['model']!r} isn't available")
    if (
        not services["ollama"].get("ok")
        or not services["infinity"].get("ok")
        or not services["chromadb"].get("ok")
    ):
        live_problems.insert(0, "a RAG service is unreachable")
    if not settings.RAG_LIVE_ENABLED:
        live_problems.insert(0, "live answering is disabled (RAG_LIVE_ENABLED)")

    return {
        "ok": not problems,
        "problems": problems,
        "services": services,
        "live": {
            "ok": not live_problems,
            "enabled": settings.RAG_LIVE_ENABLED,
            "profile": settings.RAG_LIVE_PROFILE,
            "model": settings.RAG_LIVE_MODEL,
            "threshold": settings.RAG_LIVE_THRESHOLD,
            "problems": live_problems,
        },
        "profiles": profile_reports,
        "generation_models": model_reports,
        "version_mismatch": mismatched,
    }


async def _profile_health(
    course_id: int,
    name: str,
    rows: Sequence[IndexSync],
    services: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    profile = PROFILES.get(name)
    report: dict[str, Any] = {
        "name": name,
        "embedding_model": profile.embedding_model if profile else None,
        "collection": None,  # unknown while ChromaDB is down
        "hash_matches": None,
        "embedding_model_loaded": None,
        "sources": 0,
        "chunks": 0,
        "problems": [],
    }
    problems = report["problems"]
    if profile is None:
        problems.append("no such ingestion profile")
        return report

    current = [r for r in rows if r.current_sync_id]
    report["sources"] = len(current)
    report["chunks"] = sum(r.chunk_count for r in current)

    if services["chromadb"].get("ok"):
        try:
            collection = await clients.get_collection(
                profile.collection_name(course_id)
            )
        except clients.ServiceUnavailable as exc:
            problems.append(f"ChromaDB error: {exc.detail}")
            collection = None
        else:
            report["collection"] = collection is not None
            if collection is None:
                problems.append("nothing ingested for this course")
            else:
                stored = (collection.metadata or {}).get("profile_hash")
                report["hash_matches"] = stored == profile.hash()
                if not report["hash_matches"]:
                    problems.append(
                        "collection was built with a different profile definition; re-sync"
                    )
    if services["infinity"].get("ok"):
        loaded = profile.embedding_model in services["infinity"].get("models", [])
        report["embedding_model_loaded"] = loaded
        if not loaded:
            problems.append(
                f"embedding model {profile.embedding_model} isn't loaded in Infinity"
            )

    for row in rows:
        if row.last_error:
            problems.append(f"{row.source_key} last sync failed: {row.last_error}")
    if report["collection"] and not any(
        r.source_key == HISTORICAL_QA_SOURCE_KEY and r.current_sync_id for r in rows
    ):
        problems.append("historical Q&A isn't indexed (Re-index Q&A threads)")
    return report


def _model_health(model: str, ollama: dict[str, Any]) -> dict[str, Any]:
    if not ollama.get("ok"):
        return {"model": model, "pulled": None}  # unknown while Ollama is down
    pulled = clients.normalize_model_tag(model) in ollama.get("models", [])
    return {"model": model, "pulled": pulled}


def _version_mismatches(rows: Sequence[IndexSync]) -> list[str]:
    """Sources whose profiles hold different content (§7.3)."""
    hashes: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row.content_hash:
            hashes[row.source_key].add(row.content_hash)
    return sorted(key for key, found in hashes.items() if len(found) > 1)

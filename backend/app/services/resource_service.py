"""
Staff resource management (docs/design-rag.md §3.2, §7.2, §7.5, §8).

Registers syllabus, schedule and repository sources, reports each source's
sync status per ingestion profile, and starts syncs through
`rag/ingestion.py`. Ingestion itself runs as a background task; this module
only validates the request, writes the `resources` row and claims the source.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlsplit

import structlog
from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.exceptions import ConflictError, InvalidInputError, NotFoundError
from ..config import settings
from ..models.course import Course
from ..models.resource import HISTORICAL_QA_SOURCE_KEY, IndexSync, Resource
from ..models.user import User
from .rag import clients, fetchers, ingestion
from .rag.profiles import PROFILES

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def parse_profiles_field(value: str | None) -> list[str] | None:
    """A multipart `profiles` field: comma-separated names, or absent."""
    if value is None or not value.strip():
        return None
    return [name.strip() for name in value.split(",") if name.strip()]


def resolve_profiles(requested: Sequence[str] | None, default: list[str]) -> list[str]:
    """The requested profiles (de-duplicated, all known), or `default`."""
    if requested is None:
        return default
    names = list(dict.fromkeys(requested))
    if not names:
        raise InvalidInputError("profiles must name at least one profile")
    unknown = [n for n in names if n not in PROFILES]
    if unknown:
        raise InvalidInputError(f"unknown ingestion profile(s): {', '.join(unknown)}")
    return names


async def default_profiles(
    db: AsyncSession, course_id: int, source_key: str
) -> list[str]:
    """
    Every profile the source is already ingested under, so a re-sync keeps
    its profiles on the same version (§7.3); the live profile for a new one.
    """
    rows = await db.scalars(
        select(IndexSync.profile).where(
            IndexSync.course_id == course_id, IndexSync.source_key == source_key
        )
    )
    existing = sorted(p for p in rows if p in PROFILES)
    return existing or [settings.RAG_LIVE_PROFILE]


def check_link_base_url(url: str) -> None:
    """Where people view an upload: only an absolute http(s) URL (§3.2)."""
    try:
        parts = urlsplit(url)
    except ValueError:
        raise InvalidInputError("link_base_url is not a valid URL") from None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise InvalidInputError("link_base_url must be an http(s) URL")


async def check_fetch_url(resource_type: str, url: str) -> None:
    """
    The SSRF check (§8) before anything is stored. A repository must also
    be on GITLAB_HOST: the access token is only ever sent there.
    """
    try:
        await fetchers.check_url(url)
    except fetchers.UnsafeURL as exc:
        raise InvalidInputError(str(exc)) from None
    if resource_type == "REPO":
        if urlsplit(url).hostname != settings.GITLAB_HOST:
            raise InvalidInputError(
                f"repository URLs must be on {settings.GITLAB_HOST}"
            )
        # The shallow-clone loader isn't built yet.
        raise InvalidInputError(
            "registering a repository by URL isn't supported yet; upload a zip"
        )


async def require_course(db: AsyncSession, course_id: int) -> None:
    # A global admin passes require_course_staff for any course_id, so check
    # it exists before writing a row that references it.
    if await db.get(Course, course_id) is None:
        raise NotFoundError(f"Course {course_id} not found")


async def get_resource(db: AsyncSession, course_id: int, resource_id: int) -> Resource:
    resource = await db.get(Resource, resource_id)
    if resource is None or resource.course_id != course_id:
        raise NotFoundError(f"Resource {resource_id} not found")
    return resource


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def _sync_status(row: IndexSync) -> dict[str, Any]:
    return {
        "profile": row.profile,
        "last_synced_at": row.last_synced_at,
        "chunk_count": row.chunk_count,
        "truncated_chunk_count": row.truncated_chunk_count,
        "commit_sha": row.commit_sha,
        "last_error": row.last_error,
        "last_error_at": row.last_error_at,
    }


def source_status(
    course_id: int, source_key: str, rows: Sequence[IndexSync]
) -> dict[str, Any]:
    hashes = {r.content_hash for r in rows if r.content_hash}
    return {
        "syncing": ingestion.is_syncing(course_id, source_key),
        "version_mismatch": len(hashes) > 1,
        "syncs": [_sync_status(r) for r in sorted(rows, key=lambda r: r.profile)],
    }


def resource_response(resource: Resource, rows: Sequence[IndexSync]) -> dict[str, Any]:
    return {
        "id": resource.id,
        "type": resource.type,
        "title": resource.title,
        "origin": resource.origin,
        "fetch_url": resource.fetch_url,
        "link_base_url": resource.link_base_url,
        "repo_branch": resource.repo_branch,
        "created_at": resource.created_at,
        **source_status(resource.course_id, resource.source_key, rows),
    }


async def list_resources(db: AsyncSession, course_id: int) -> dict[str, Any]:
    resources = await db.scalars(
        select(Resource)
        .where(Resource.course_id == course_id)
        .order_by(Resource.created_at, Resource.id)
    )
    rows = await db.scalars(select(IndexSync).where(IndexSync.course_id == course_id))
    by_key: dict[str, list[IndexSync]] = defaultdict(list)
    for row in rows:
        by_key[row.source_key].append(row)
    return {
        "live_profile": settings.RAG_LIVE_PROFILE,
        "profiles": list(PROFILES),
        "resources": [resource_response(r, by_key[r.source_key]) for r in resources],
        "historical_qa": source_status(
            course_id, HISTORICAL_QA_SOURCE_KEY, by_key[HISTORICAL_QA_SOURCE_KEY]
        ),
    }


async def source_rows(
    db: AsyncSession, course_id: int, source_key: str
) -> list[IndexSync]:
    rows = await db.scalars(
        select(IndexSync).where(
            IndexSync.course_id == course_id, IndexSync.source_key == source_key
        )
    )
    return list(rows)


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


async def create_resource(
    db: AsyncSession,
    course_id: int,
    user: User,
    *,
    resource_type: str,
    title: str,
    origin: str,
    fetch_url: str | None = None,
    link_base_url: str | None = None,
    repo_branch: str | None = None,
) -> Resource:
    resource = Resource(
        course_id=course_id,
        type=resource_type,
        title=title,
        origin=origin,
        fetch_url=fetch_url,
        link_base_url=link_base_url,
        repo_branch=repo_branch,
        created_by_user_id=user.id,
    )
    db.add(resource)
    await db.flush()
    await db.refresh(resource)  # created_at comes from the server default
    logger.info("resource_created", course_id=course_id, resource_id=resource.id)
    return resource


async def delete_resource(db: AsyncSession, course_id: int, resource: Resource) -> None:
    """
    Removes the source's chunks from every profile's collection, then the
    row (`index_syncs` rows go with it). With ChromaDB down the row is still
    deleted: its chunks have no current `sync_id` left, so search can't see
    them (§7.3).
    """
    if ingestion.is_syncing(course_id, resource.source_key):
        raise ConflictError("This resource is syncing; delete it when the sync ends")
    where = {"source_key": resource.source_key}
    for profile in PROFILES.values():
        try:
            collection = await clients.get_collection(
                profile.collection_name(course_id)
            )
            if collection is not None:
                await clients.delete_chunks(collection, where)
        except clients.ServiceUnavailable:
            logger.warning(
                "resource_chunk_delete_failed",
                course_id=course_id,
                resource_id=resource.id,
                profile=profile.name,
                exc_info=True,
            )
    await db.delete(resource)
    logger.info("resource_deleted", course_id=course_id, resource_id=resource.id)


async def start_sync(
    background_tasks: BackgroundTasks,
    *,
    course_id: int,
    source_key: str,
    resource_id: int | None,
    title: str,
    profiles: list[str],
    load: ingestion.Loader,
) -> None:
    """
    Claims the source and schedules `ingestion.ingest`, which releases the
    claim when it ends. The claim is the last thing that can fail: if
    scheduling raises, it's released here, or the source would answer 409
    until the backend restarts.
    """
    try:
        await ingestion.claim(course_id, source_key)
    except ingestion.SyncInProgress:
        raise ConflictError("This source is already syncing") from None
    try:
        background_tasks.add_task(
            ingestion.ingest,
            course_id=course_id,
            source_key=source_key,
            resource_id=resource_id,
            title=title,
            profiles=profiles,
            load=load,
        )
    except BaseException:
        await ingestion.release(course_id, source_key)
        raise
    logger.info(
        "sync_started", course_id=course_id, source_key=source_key, profiles=profiles
    )

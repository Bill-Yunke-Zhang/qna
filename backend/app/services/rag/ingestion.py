"""
The ingestion task and the sync registry (docs/design-rag.md §7.2, §7.3).

A request handler claims the source, then schedules `ingest` as a
background task, which releases the claim when it ends:

    await ingestion.claim(course_id, resource.source_key)   # SyncInProgress → 409
    background_tasks.add_task(
        ingestion.ingest,
        course_id=course_id,
        source_key=resource.source_key,
        resource_id=resource.id,
        title=resource.title,
        profiles=profile_names,
        load=ingestion.web_page_loader(resource),
    )

`load` returns the source's `Document`s. Web pages have a loader here;
uploads, repos and historical Q&A only need to produce `Document`s too.

For each requested profile, one at a time (to leave CPU for Ollama): chunk,
embed, insert under a new `sync_id`, then switch `index_syncs.current_sync_id`
to it. Searches filter on the current `sync_id`s, so new chunks are invisible
until the switch and old ones right after it; the old ones are deleted
`CLEANUP_GRACE_S` later. A failed profile records `last_error` and keeps its
previous version current; the other profiles still run. If the fetched
content hashes to what a profile already has, it is not re-embedded.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select

from ...config import settings
from ...database import AsyncSessionLocal
from ...models import IndexSync, Resource
from . import clients, fetchers
from .chunking import (
    HEADING_SEPARATOR,
    Chunk,
    Section,
    count_tokens,
    finish_chunks,
    heading_path_label,
    plan_chunks,
    web_citation,
    web_sections,
)
from .profiles import CHUNKED_RESOURCE_TYPES, Profile, get_profile

logger = structlog.get_logger()

# Bump when what gets embedded or stored per chunk changes without the
# profile changing (e.g. the heading line below). It is part of the content
# hash, so the next sync re-embeds instead of skipping as "unchanged".
INGEST_FORMAT = 1

# Chunks added to ChromaDB per request.
_ADD_BATCH = 100

# Input limits in tokens, special tokens included. Text past the limit is
# silently dropped when embedding, so such chunks are counted and logged
# (§6.2). Counted with the chunking tokenizer, which is exact for MiniLM and
# an estimate for the others.
EMBEDDING_INPUT_LIMITS = {
    "sentence-transformers/all-MiniLM-L6-v2": 256,
    "BAAI/bge-small-en-v1.5": 512,
    "Alibaba-NLP/gte-Qwen2-1.5B-instruct": 8192,
}


# ── Documents ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Document:
    """
    One parsed document of a source: its text, its structural sections, and
    how to locate a chunk in it.

    `locate(chunk)` returns the chunk's location metadata (§3.1):
    `source_url` and, where a link can point inside the document,
    `citation_url` plus the type's fields (`heading_path`, `fragment_*`,
    `line_start`, `page_start`, ...). Values must be str, int, float or bool.
    `key` identifies the document within the source (page URL, file path);
    it is part of the content hash, so a changed link target re-embeds.
    """

    resource_type: str
    key: str
    text: str
    sections: tuple[Section, ...]
    locate: Callable[[Chunk], dict[str, Any]]


Loader = Callable[[], Awaitable[list[Document]]]


def web_document(html: str, page_url: str, resource_type: str) -> Document:
    """A syllabus or schedule page; citations link to `page_url` (§3.2)."""
    doc = fetchers.parse_html(html)
    fetchers.check_has_content(doc)
    return Document(
        resource_type=resource_type,
        key=page_url,
        text=doc.text,
        sections=tuple(web_sections(doc)),
        locate=lambda chunk: web_citation(page_url, doc, chunk),
    )


_WEB_TYPES = {"SYLLABUS": "syllabus", "SCHEDULE": "schedule"}


def web_page_loader(resource: Resource) -> Loader:
    """Fetches a URL-origin syllabus or schedule resource when the task runs."""
    if resource.origin != "URL" or resource.type not in _WEB_TYPES:
        raise ValueError(f"not a URL web page resource: {resource.type}")
    fetch_url = resource.fetch_url
    page_url = resource.link_base_url or fetch_url
    resource_type = _WEB_TYPES[resource.type]

    async def load() -> list[Document]:
        html = await fetchers.fetch_web_page(fetch_url)
        return [await asyncio.to_thread(web_document, html, page_url, resource_type)]

    return load


def content_hash(documents: Iterable[Document]) -> str:
    digest = hashlib.sha256(f"format:{INGEST_FORMAT}".encode())
    for d in sorted(documents, key=lambda d: (d.key, d.resource_type)):
        for part in (d.resource_type, d.key, d.text):
            digest.update(b"\0" + part.encode())
    return digest.hexdigest()


# ── Sync registry ────────────────────────────────────────────────────────────
#
# One claim per (course, source) covers the whole multi-profile action. It's
# in-process on purpose: the design already requires a single backend process
# (§7.3), and a restart clears the registry along with the lost task.


class SyncInProgress(Exception):
    """The source is already being synced (the request returns 409)."""


_syncing: set[tuple[int, str]] = set()
_registry_lock = asyncio.Lock()


async def claim(course_id: int, source_key: str) -> None:
    async with _registry_lock:
        if (course_id, source_key) in _syncing:
            raise SyncInProgress(f"{source_key} is already syncing")
        _syncing.add((course_id, source_key))


async def release(course_id: int, source_key: str) -> None:
    async with _registry_lock:
        _syncing.discard((course_id, source_key))


def is_syncing(course_id: int, source_key: str) -> bool:
    """For deleting a resource, which returns 409 while it syncs (§7.3)."""
    return (course_id, source_key) in _syncing


# ── index_syncs ──────────────────────────────────────────────────────────────


class SyncStore:
    """Reads and writes `index_syncs` rows. Tests swap in a fake."""

    async def get(self, course_id: int, profile: str, source_key: str):
        async with AsyncSessionLocal() as db:
            return await self._row(db, course_id, profile, source_key)

    async def save(
        self,
        course_id: int,
        profile: str,
        source_key: str,
        resource_id: int | None,
        **fields: Any,
    ) -> None:
        """Create or update the row with `fields`."""
        async with AsyncSessionLocal() as db:
            row = await self._row(db, course_id, profile, source_key)
            if row is None:
                row = IndexSync(
                    course_id=course_id,
                    profile=profile,
                    source_key=source_key,
                    resource_id=resource_id,
                )
                db.add(row)
            for name, value in fields.items():
                setattr(row, name, value)
            await db.commit()

    @staticmethod
    async def _row(db, course_id: int, profile: str, source_key: str):
        return await db.scalar(
            select(IndexSync).where(
                IndexSync.course_id == course_id,
                IndexSync.profile == profile,
                IndexSync.source_key == source_key,
            )
        )


store = SyncStore()


def _now() -> datetime:
    # Naive UTC, like the server-side func.now() defaults.
    return datetime.now(UTC).replace(tzinfo=None)


# ── The task ─────────────────────────────────────────────────────────────────


class ProfileChanged(Exception):
    """The collection was made under a different version of the profile."""


async def ingest(
    *,
    course_id: int,
    source_key: str,
    resource_id: int | None,
    title: str,
    profiles: Sequence[str],
    load: Loader,
    commit_sha: str | None = None,
) -> None:
    """
    Background task: load the source, then ingest it under each profile.
    The caller must have `claim`ed the source; this releases it. Never
    raises: every failure ends up in `index_syncs.last_error`.
    """
    log = logger.bind(course_id=course_id, source_key=source_key)
    try:
        try:
            documents = await load()
        except Exception as exc:
            log.warning("ingest_load_failed", error=_error_text(exc), exc_info=True)
            for name in profiles:
                await _record_error(course_id, name, source_key, resource_id, exc)
            return

        new_hash = content_hash(documents)
        cleanups: list[tuple[Any, str]] = []
        for name in profiles:
            try:
                done = await _ingest_profile(
                    course_id=course_id,
                    source_key=source_key,
                    resource_id=resource_id,
                    title=title,
                    profile=get_profile(name),
                    documents=documents,
                    content_hash=new_hash,
                    commit_sha=commit_sha,
                )
                if done:
                    cleanups.append(done)
            except Exception as exc:
                log.warning(
                    "ingest_profile_failed",
                    profile=name,
                    error=_error_text(exc),
                    exc_info=True,
                )
                await _record_error(course_id, name, source_key, resource_id, exc)

        if cleanups:
            # One grace period for all profiles, rather than one per profile.
            await asyncio.sleep(settings.CLEANUP_GRACE_S)
            for collection, sync_id in cleanups:
                try:
                    await _delete_other_syncs(collection, source_key, sync_id)
                except Exception:
                    # Leftovers are invisible (wrong sync_id) and are removed
                    # by the next successful sync.
                    log.warning("ingest_cleanup_failed", exc_info=True)
    finally:
        await release(course_id, source_key)


async def _ingest_profile(
    *,
    course_id: int,
    source_key: str,
    resource_id: int | None,
    title: str,
    profile: Profile,
    documents: Sequence[Document],
    content_hash: str,
    commit_sha: str | None,
) -> tuple[Any, str] | None:
    """
    Returns `(collection, new sync_id)` for cleanup after a switch, or None
    if the content was unchanged.
    """
    collection = await clients.get_or_create_collection(
        profile.collection_name(course_id),
        metadata={
            "embedding_model": profile.embedding_model,
            "profile_hash": profile.hash(),
        },
    )
    if (collection.metadata or {}).get("profile_hash") != profile.hash():
        raise ProfileChanged("profile changed")

    row = await store.get(course_id, profile.name, source_key)
    if (
        row is not None
        and row.current_sync_id
        and row.content_hash == content_hash
        and row.last_error is None
    ):
        await store.save(
            course_id, profile.name, source_key, resource_id, last_synced_at=_now()
        )
        return None

    records = await _chunk_records(profile, title, documents)
    sync_id = str(uuid.uuid4())
    try:
        vectors = await clients.embed(
            [r.embed_text for r in records], profile.embedding_model
        )
        for start in range(0, len(records), _ADD_BATCH):
            batch = records[start : start + _ADD_BATCH]
            await clients.add_chunks(
                collection,
                ids=[f"{source_key}:{sync_id}:{start + i}" for i in range(len(batch))],
                embeddings=vectors[start : start + _ADD_BATCH],
                documents=[r.text for r in batch],
                metadatas=[
                    _metadata(r, source_key, resource_id, sync_id, start + i)
                    for i, r in enumerate(batch)
                ],
            )
    except Exception:
        # Not current, so invisible either way; remove what made it in.
        try:
            await clients.delete_chunks(
                collection, {"$and": [{"source_key": source_key}, {"sync_id": sync_id}]}
            )
        except Exception:
            pass
        raise

    truncated = sum(r.truncated for r in records)
    if truncated:
        logger.warning(
            "ingest_chunks_truncated",
            source_key=source_key,
            profile=profile.name,
            count=truncated,
        )
    # The switch: from here on, searches see the new chunks only.
    await store.save(
        course_id,
        profile.name,
        source_key,
        resource_id,
        current_sync_id=sync_id,
        content_hash=content_hash,
        commit_sha=commit_sha,
        chunk_count=len(records),
        truncated_chunk_count=truncated,
        last_synced_at=_now(),
        last_error=None,
        last_error_at=None,
    )
    return collection, sync_id


@dataclass(frozen=True)
class _Record:
    text: str
    embed_text: str
    label: str
    resource_type: str
    token_count: int
    truncated: bool
    location: dict[str, Any]


async def _chunk_records(
    profile: Profile, title: str, documents: Sequence[Document]
) -> list[_Record]:
    records = []
    for doc in documents:
        chunks = await _chunk(profile, doc)
        records.extend(
            await asyncio.to_thread(_build_records, profile, title, doc, chunks)
        )
    return records


def _build_records(
    profile: Profile, title: str, doc: Document, chunks: Sequence[Chunk]
) -> list[_Record]:
    limit = EMBEDDING_INPUT_LIMITS.get(profile.embedding_model)
    records = []
    for chunk in chunks:
        text = chunk.text(doc.text)
        heading = heading_path_label(chunk.heading_path)
        # The heading line goes into the embedding, not the stored text (Text
        # Fragments are built from the stored text). Schedule entries carry
        # their dates in the heading.
        embed_text = profile.document_prefix + (
            f"{heading}\n{text}" if heading else text
        )
        records.append(
            _Record(
                text=text,
                embed_text=embed_text,
                label=HEADING_SEPARATOR.join(p for p in (title, heading) if p),
                resource_type=doc.resource_type,
                token_count=chunk.token_count,
                # +2 for the [CLS]/[SEP]-style special tokens.
                truncated=bool(limit and count_tokens(embed_text) + 2 > limit),
                location=doc.locate(chunk),
            )
        )
    return records


async def _chunk(profile: Profile, doc: Document) -> list[Chunk]:
    """The three chunking steps (§7.3); embedding never runs in a thread."""
    if doc.resource_type not in CHUNKED_RESOURCE_TYPES:
        # Historical Q&A: each section (one thread) is one atomic chunk.
        return [
            Chunk(
                s.start,
                s.end,
                s.heading_path,
                await asyncio.to_thread(count_tokens, doc.text[s.start : s.end]),
            )
            for s in doc.sections
        ]
    chunker = profile.chunker_for(doc.resource_type)
    plan = await asyncio.to_thread(plan_chunks, doc.text, doc.sections, chunker)
    vectors: list[list[float]] = []
    if plan.units_to_embed:
        vectors = await clients.embed(
            [profile.document_prefix + u for u in plan.units_to_embed],
            profile.embedding_model,
        )
    return await asyncio.to_thread(finish_chunks, plan, vectors)


def _metadata(
    record: _Record,
    source_key: str,
    resource_id: int | None,
    sync_id: str,
    index: int,
) -> dict[str, Any]:
    metadata = {
        **record.location,
        "label": record.label,
        "resource_type": record.resource_type,
        "source_key": source_key,
        "sync_id": sync_id,
        "chunk_index": index,
        "token_count": record.token_count,
    }
    if resource_id is not None:
        metadata["resource_id"] = resource_id
    # ChromaDB rejects None; fields that don't apply are left out (§3.1).
    return {k: v for k, v in metadata.items() if v is not None}


async def _delete_other_syncs(collection: Any, source_key: str, sync_id: str) -> None:
    """Old versions and leftovers of crashed runs, never the current one."""
    await clients.delete_chunks(
        collection,
        {"$and": [{"source_key": source_key}, {"sync_id": {"$ne": sync_id}}]},
    )


async def _record_error(
    course_id: int,
    profile: str,
    source_key: str,
    resource_id: int | None,
    exc: Exception,
) -> None:
    """Keeps the current version; only the error fields change."""
    try:
        await store.save(
            course_id,
            profile,
            source_key,
            resource_id,
            last_error=_error_text(exc),
            last_error_at=_now(),
        )
    except Exception:
        logger.error(
            "ingest_record_error_failed",
            course_id=course_id,
            profile=profile,
            source_key=source_key,
            exc_info=True,
        )


def _error_text(exc: BaseException) -> str:
    """Shown to staff in the Resources page; no secrets reach here (§8)."""
    if isinstance(
        exc, (fetchers.FetchError, clients.ServiceUnavailable, ProfileChanged)
    ):
        text = str(exc)
    elif isinstance(exc, KeyError):  # get_profile
        text = str(exc.args[0]) if exc.args else "unknown profile"
    else:
        text = f"{type(exc).__name__}: {exc}"
    return text[:1000]

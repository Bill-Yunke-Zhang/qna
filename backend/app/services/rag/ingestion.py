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

`load` returns the source's `Document`s. Loaders here: `web_page_loader`
(URL syllabus/schedule), `documents_loader` (uploads, parsed in the request
by `parse_upload`, including repo zips via `repo_documents`) and
`historical_qa_loader`.

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
from ...models.resource import HISTORICAL_QA_SOURCE_KEY
from . import clients, fetchers
from .chunking import (
    HEADING_SEPARATOR,
    Chunk,
    Section,
    count_tokens,
    finish_chunks,
    heading_path_label,
    markdown_citation,
    markdown_sections,
    pdf_citation,
    plan_chunks,
    sections_for,
    web_citation,
    web_sections,
)
from .profiles import CHUNKED_RESOURCE_TYPES, PROFILES, Profile, get_profile

logger = structlog.get_logger()

# Bump when what gets embedded or stored per chunk changes without the
# profile changing (e.g. the heading line below). It is part of the content
# hash, so the next sync re-embeds instead of skipping as "unchanged".
# 2: labels drop a first heading equal to the resource title.
INGEST_FORMAT = 2

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


def parse_upload(
    resource_type: str, link_base_url: str, filename: str, data: bytes
) -> list[Document]:
    """
    An uploaded file as `Document`s, checked and parsed in the request
    (§7.2), so a bad upload is a 422 rather than a `last_error`. Raises
    `fetchers.UploadError` (or `FetchError` for an empty page). CPU-bound;
    run it with `asyncio.to_thread`, then pass the result to
    `documents_loader`.
    """
    files = fetchers.read_upload(filename, data)
    if resource_type in _WEB_TYPES:
        html_types = (".html", ".htm")
        if len(files) != 1 or not files[0].path.lower().endswith(html_types):
            raise fetchers.UploadError(
                "a syllabus or schedule upload must be a single .html file"
            )
        html = files[0].data.decode("utf-8", "replace")
        return [web_document(html, link_base_url, _WEB_TYPES[resource_type])]
    if resource_type == "REPO":
        if not any(f.path.lower().endswith(fetchers.ZIP_MEMBER_TYPES) for f in files):
            raise fetchers.UploadError(
                "a repository upload must be a .zip, .md or .pdf file"
            )
        documents = repo_documents(files, link_base_url)
        if not documents:
            raise fetchers.UploadError("the upload's .md and .pdf files have no text")
        return documents
    raise fetchers.UploadError(f"uploading a {resource_type} isn't supported")


def repo_documents(
    files: Sequence[fetchers.UploadedFile],
    base_url: str,
    commit_sha: str | None = None,
) -> list[Document]:
    """
    A repo's `.md` and `.pdf` files as `repo_markdown` and `repo_pdf`
    documents (§7.4); anything else is skipped. `base_url` is where the files
    are viewed: a zip's `link_base_url`, or a clone's `.../-/blob/{branch}`.
    Files with no text are left out. Raises `FetchError` for an unreadable
    PDF. CPU-bound; run it in a thread.
    """
    documents = []
    for file in sorted(files, key=lambda f: f.path):
        lower = file.path.lower()
        if lower.endswith(".md"):
            doc = markdown_document(file, base_url, commit_sha)
        elif lower.endswith(".pdf"):
            doc = pdf_document(file, base_url, commit_sha)
        else:
            continue
        if doc.sections:
            documents.append(doc)
    return documents


def markdown_document(
    file: fetchers.UploadedFile, base_url: str, commit_sha: str | None = None
) -> Document:
    """
    Split by heading (`markdown_sections`). The file path heads every
    section's heading path, so it is embedded and labels the chunk
    ("{title} › p2-buzzer/instructions.md › Setup"), and so different files'
    identical headings stay apart.
    """
    text = file.data.decode("utf-8", "replace").replace("\r\n", "\n")
    path = file.path
    sections = tuple(
        Section(s.start, s.end, (path, *s.heading_path))
        for s in markdown_sections(text)
    )
    return Document(
        resource_type="repo_markdown",
        key=path,
        text=text,
        sections=sections,
        locate=lambda chunk: markdown_citation(base_url, path, text, chunk, commit_sha),
    )


def pdf_document(
    file: fetchers.UploadedFile, base_url: str, commit_sha: str | None = None
) -> Document:
    """One section per page with text; `sections_for` merges them for every
    chunker but `PerPage`."""
    pdf = fetchers.parse_pdf(file.path, file.data)
    path = file.path
    ends = [*pdf.page_starts[1:], len(pdf.text) + 2]
    sections = tuple(
        Section(start, end - 2, (path,))
        for start, end in zip(pdf.page_starts, ends, strict=True)
        if pdf.text[start : end - 2].strip()
    )
    return Document(
        resource_type="repo_pdf",
        key=path,
        text=pdf.text,
        sections=sections,
        locate=lambda chunk: pdf_citation(
            base_url, path, pdf.page_starts, chunk, commit_sha
        ),
    )


def documents_loader(documents: list[Document]) -> Loader:
    """For sources parsed before the task starts (uploads). Kept in memory
    only, so a backend restart loses them and staff upload again (§7.2)."""

    async def load() -> list[Document]:
        return documents

    return load


HISTORICAL_QA_TITLE = "Past question"


def qa_document(thread: fetchers.QAThread) -> Document:
    """
    One thread as one atomic section (§7.4). The title is the heading, so it
    is embedded and labels the chunk ("Past question › {title}"), but not
    stored: the stored text is the question body, a blank line, then the
    accepted answer, which starts at `answer_start` so the prompt can tag the
    two parts separately (§5.5).
    """
    text = f"{thread.question}\n\n{thread.answer}"
    location = {
        # Relative to either app's base; there is no citation_url (§3.1).
        "source_url": f"/questions/{thread.question_id}",
        "question_id": thread.question_id,
        "accepted_post_id": thread.accepted_post_id,
        "answer_start": len(thread.question) + 2,
    }
    return Document(
        resource_type="historical_qa",
        # Includes the post, so accepting a different answer with the same
        # text still re-embeds (the stored accepted_post_id changes).
        key=f"question:{thread.question_id}:answer:{thread.accepted_post_id}",
        text=text,
        sections=(Section(0, len(text), (thread.title,)),),
        locate=lambda chunk: location,
    )


def historical_qa_loader(course_id: int) -> Loader:
    """Reads the course's eligible threads when the task runs. Ingest with
    `source_key=HISTORICAL_QA_SOURCE_KEY`, `resource_id=None` and
    `title=HISTORICAL_QA_TITLE`."""

    async def load() -> list[Document]:
        async with AsyncSessionLocal() as db:
            threads = await fetchers.read_historical_qa(db, course_id)
        return [qa_document(t) for t in threads]

    return load


def content_hash(documents: Iterable[Document]) -> str:
    digest = hashlib.sha256(f"format:{INGEST_FORMAT}".encode())
    for d in sorted(documents, key=lambda d: (d.key, d.resource_type)):
        for part in (d.resource_type, d.key, d.text):
            digest.update(b"\0" + part.encode())
        # Headings are embedded with each chunk (a Q&A thread's title is only
        # there), so a changed heading must re-embed too.
        for section in d.sections:
            digest.update(b"\1" + HEADING_SEPARATOR.join(section.heading_path).encode())
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
                label=_label(title, chunk.heading_path),
                resource_type=doc.resource_type,
                token_count=chunk.token_count,
                # +2 for the [CLS]/[SEP]-style special tokens.
                truncated=bool(limit and count_tokens(embed_text) + 2 > limit),
                location=doc.locate(chunk),
            )
        )
    return records


def _label(title: str, heading_path: Sequence[str]) -> str:
    """
    "{resource title} › {heading path}" (§3.1). A page's top heading is often
    the resource title itself ("Syllabus › Syllabus › Grading"), so a first
    heading equal to the title is left out of the label only; it is still
    embedded and stored as `heading_path`.
    """
    path = list(heading_path)
    if (
        path
        and " ".join(path[0].split()).casefold() == " ".join(title.split()).casefold()
    ):
        path = path[1:]
    return HEADING_SEPARATOR.join(p for p in (title, heading_path_label(path)) if p)


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
    sections = sections_for(chunker, doc.resource_type, doc.sections)
    plan = await asyncio.to_thread(plan_chunks, doc.text, sections, chunker)
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


# ── Un-accept cleanup (§4.6) ─────────────────────────────────────────────────


async def drop_qa_thread(course_id: int, question_id: int) -> None:
    """
    Background task after an accepted answer lost its acceptance: delete the
    thread's historical Q&A chunks from every profile's collection and lower
    `chunk_count` by the current ones. Only cleanup; the query-time check is
    what stops the old answer being cited. `set_post_accepted` has already
    cleared `content_hash` in the same commit, so the next re-index brings
    the thread back. Never raises: a failure is logged and the next re-index
    removes the chunks.
    """
    where = {
        "$and": [
            {"source_key": HISTORICAL_QA_SOURCE_KEY},
            {"question_id": question_id},
        ]
    }
    for profile in PROFILES.values():
        log = logger.bind(
            course_id=course_id, question_id=question_id, profile=profile.name
        )
        try:
            collection = await clients.get_collection(
                profile.collection_name(course_id)
            )
            if collection is None:
                continue
            found = await clients.get_chunk_metadata(collection, where)
            if not found:
                continue
            await clients.delete_chunks(collection, where)
            row = await store.get(course_id, profile.name, HISTORICAL_QA_SOURCE_KEY)
            if row is None:
                continue
            current = sum(m.get("sync_id") == row.current_sync_id for m in found)
            if current:
                await store.save(
                    course_id,
                    profile.name,
                    HISTORICAL_QA_SOURCE_KEY,
                    None,
                    chunk_count=max(row.chunk_count - current, 0),
                )
        except Exception:
            log.warning("qa_thread_cleanup_failed", exc_info=True)

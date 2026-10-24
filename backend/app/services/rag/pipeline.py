"""
The shared RAG pipeline (docs/design-rag.md §5.3). One `run()` serves both the
compare endpoint and live answering, so the eval measures the code students
get. It never writes to the database.

`RagConfig`, `RagResult` and the errors `run()` raises are the contract the
compare endpoint maps to status codes. `run()` checks the request, retrieves
with the similarity threshold, builds the tagged prompt (prompt.py) and
generates through `generation_gate`, which serves one generation at a time
and lets compare calls go before waiting live ones.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Literal

import structlog
from sqlalchemy import select

from ...config import settings
from ...database import AsyncSessionLocal
from ...models.qa import Post
from ...models.resource import IndexSync
from . import clients, prompt
from .profiles import PROFILES

logger = structlog.get_logger()

# Who is asking. Compare calls go through the generation gate before waiting
# live tasks (§5.3).
Caller = Literal["COMPARE", "LIVE"]


@dataclass(frozen=True)
class RagConfig:
    """The per-request settings (§6.1); the compare body's fields, by name."""

    ingestion_profile: str
    similarity_threshold: float
    system_prompt: str
    generation_model: str


@dataclass(frozen=True)
class RetrievedChunk:
    """A chunk that passed the threshold, i.e. one that went into the prompt."""

    resource_type: str
    # The document with no location; the harness checks
    # `expected_source in source_url` (§3.1).
    source_url: str
    similarity_score: float
    text: str
    # The chunk's full ChromaDB metadata, for citations on the live path.
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RagMetrics:
    """Named as in the compare contract, so the response needs no mapping.

    `cpu_percent` isn't here: it covers the whole request, so the compare
    endpoint measures it around `run()`.
    """

    embedding_time_ms: float = 0.0
    retrieval_time_ms: float = 0.0
    generation_time_ms: float = 0.0


@dataclass(frozen=True)
class RagResult:
    matched: bool
    chunks: list[RetrievedChunk]
    answer: str | None  # None when matched is False
    # The deadline cut generation short. Compare returns the partial answer;
    # the live path never posts it.
    truncated: bool = False
    metrics: RagMetrics = field(default_factory=RagMetrics)


# ── Errors (§5.3). Every one is an error, never a silent `matched: false`. ───


class PipelineError(Exception):
    """A request the pipeline can't serve on this deployment."""


class UnknownProfile(PipelineError):
    """`ingestion_profile` isn't in `PROFILES`."""


class ModelNotAvailable(PipelineError):
    """`generation_model` isn't pulled into Ollama. Checked before retrieval."""


class ProfileNotIngested(PipelineError):
    """The course has no collection for this profile."""


class ProfileStale(PipelineError):
    """The collection's stored profile hash differs from the profile in code."""


class GenerationGate:
    """
    One generation at a time for the whole process (Ollama runs one anyway,
    §5.3). When it frees up, a waiting COMPARE caller always goes before a
    waiting LIVE one, so a harness call waits behind at most the one live
    generation already running. Waiting counts against the caller's deadline.
    """

    def __init__(self) -> None:
        self._busy = False
        self._waiting: dict[Caller, deque[asyncio.Future[None]]] = {
            "COMPARE": deque(),
            "LIVE": deque(),
        }

    @asynccontextmanager
    async def acquire(self, caller: Caller, deadline: float) -> AsyncIterator[bool]:
        """Yields True with the gate held, or False if the deadline passed first."""
        if not self._busy:
            self._busy = True
        else:
            waiter: asyncio.Future[None] = asyncio.get_running_loop().create_future()
            self._waiting[caller].append(waiter)
            try:
                await asyncio.wait_for(
                    asyncio.shield(waiter), max(deadline - time.monotonic(), 0)
                )
            except TimeoutError:
                if waiter.done():  # handed the gate just as time ran out
                    self._release()
                else:
                    self._waiting[caller].remove(waiter)
                yield False
                return
            except BaseException:
                if waiter.done():
                    self._release()
                else:
                    self._waiting[caller].remove(waiter)
                raise
        try:
            yield True
        finally:
            self._release()

    def _release(self) -> None:
        for caller in ("COMPARE", "LIVE"):
            queue = self._waiting[caller]
            while queue:
                waiter = queue.popleft()
                if not waiter.done():
                    waiter.set_result(None)  # the gate passes to it, still busy
                    return
        self._busy = False


generation_gate = GenerationGate()


async def _current_sync_ids(course_id: int, profile_name: str) -> list[str]:
    async with AsyncSessionLocal() as db:
        rows = await db.scalars(
            select(IndexSync.current_sync_id).where(
                IndexSync.course_id == course_id,
                IndexSync.profile == profile_name,
                IndexSync.current_sync_id.is_not(None),
            )
        )
        return [r for r in rows if r]


async def _still_accepted(post_ids: Sequence[int]) -> set[int]:
    """Which of these posts are still an accepted, non-retracted human answer."""
    if not post_ids:
        return set()
    async with AsyncSessionLocal() as db:
        rows = await db.scalars(
            select(Post.id).where(
                Post.id.in_(post_ids),
                Post.is_accepted.is_(True),
                Post.retracted_at.is_(None),
                Post.author_role != "AI",
            )
        )
        return set(rows)


def _ms(start: float) -> float:
    return round((time.monotonic() - start) * 1000, 1)


def _budget(deadline: float) -> float:
    """
    The timeout for one service call before generation: what's left of the
    caller's budget, never more than RAG_SERVICE_TIMEOUT_S. Without it each
    call could take the full service timeout and together run a compare call
    past the harness's limit. Raises ServiceUnavailable once the budget is
    gone, rather than starting a call that can't finish.
    """
    left = deadline - time.monotonic()
    if left <= 0:
        raise clients.ServiceUnavailable(
            "pipeline", "time budget used up before generation"
        )
    return min(settings.RAG_SERVICE_TIMEOUT_S, left)


async def run(
    course_id: int,
    question_text: str,
    config: RagConfig,
    *,
    caller: Caller,
    deadline: float,
) -> RagResult:
    """
    Retrieve, apply the threshold and generate (§5.3). `deadline` is a
    `time.monotonic()` value covering everything, waiting at the generation
    gate included. Raises the errors above, or `clients.ServiceUnavailable`.
    Never writes to the database.
    """
    # The checks come first, in this order, so a bad request is an error and
    # never a silent `matched: false` (§5.3).
    profile = PROFILES.get(config.ingestion_profile)
    if profile is None:
        raise UnknownProfile(config.ingestion_profile)
    if not await clients.has_model(config.generation_model, timeout=_budget(deadline)):
        raise ModelNotAvailable(config.generation_model)
    question = question_text[: settings.QUESTION_MAX_CHARS]
    collection = await clients.get_collection(
        profile.collection_name(course_id), timeout=_budget(deadline)
    )
    if collection is None:
        raise ProfileNotIngested(profile.name)
    meta = collection.metadata or {}
    if meta.get("profile_hash") != profile.hash():
        raise ProfileStale(profile.name)
    sync_ids = await _current_sync_ids(course_id, profile.name)
    if not sync_ids:
        raise ProfileNotIngested(profile.name)
    # The model the vectors were made with, never one from code (§6.2).
    model = str(meta.get("embedding_model") or profile.embedding_model)

    started = time.monotonic()
    [vector] = await clients.embed(
        [profile.query_prefix + question], model, timeout=_budget(deadline)
    )
    embedding_ms = _ms(started)

    started = time.monotonic()
    where = (
        {"sync_id": sync_ids[0]}
        if len(sync_ids) == 1
        else {"sync_id": {"$in": sync_ids}}
    )
    hits = await clients.query_chunks(
        collection, vector, settings.RAG_TOP_K, where, timeout=_budget(deadline)
    )
    # A past answer that was un-accepted or retracted since the last
    # re-index must not be cited (§4.6).
    qa_posts = [
        int(h.metadata["accepted_post_id"])
        for h in hits
        if h.metadata.get("resource_type") == "historical_qa"
        and "accepted_post_id" in h.metadata
    ]
    accepted = await _still_accepted(qa_posts)
    retrieval_ms = _ms(started)

    log = logger.bind(course_id=course_id, profile=profile.name, caller=caller.lower())
    kept: list[RetrievedChunk] = []
    for h in hits:
        similarity = round(1.0 - h.distance, 4)
        stale = (
            h.metadata.get("resource_type") == "historical_qa"
            and int(h.metadata.get("accepted_post_id", -1)) not in accepted
        )
        above = similarity >= config.similarity_threshold
        log.info(
            "rag_hit",
            source=h.metadata.get("source_url"),
            similarity=similarity,
            above_threshold=above,
            stale_qa=stale or None,
        )
        if above and not stale:
            kept.append(
                RetrievedChunk(
                    resource_type=str(h.metadata.get("resource_type", "")),
                    source_url=str(h.metadata.get("source_url", "")),
                    similarity_score=similarity,
                    text=h.text,
                    metadata=h.metadata,
                )
            )
    if not kept:
        return RagResult(
            matched=False,
            chunks=[],
            answer=None,
            metrics=RagMetrics(embedding_ms, retrieval_ms, 0.0),
        )

    built = prompt.build(
        config.system_prompt,
        [prompt.PromptChunk(c.resource_type, c.text, dict(c.metadata)) for c in kept],
        question,
    )
    if len(built.used) < len(kept):
        log.warning("rag_prompt_chunks_dropped", dropped=len(kept) - len(built.used))
        kept = [kept[i] for i in built.used]

    queued = time.monotonic()
    generation_ms = 0.0
    async with generation_gate.acquire(caller, deadline) as held:
        # generation_time_ms is the generation itself; time spent waiting
        # for the gate (behind another answer) is logged separately.
        gate_wait_ms = _ms(queued)
        started = time.monotonic()
        if held:
            result = await clients.chat(
                config.generation_model,
                built.messages,
                options={
                    "num_ctx": settings.OLLAMA_NUM_CTX,
                    "num_predict": settings.OLLAMA_NUM_PREDICT,
                    "temperature": 0,
                    "seed": settings.OLLAMA_SEED,
                },
                deadline=deadline,
            )
            generation_ms = _ms(started)
        else:
            result = clients.ChatResult("", truncated=True)
    if gate_wait_ms >= 1000:
        log.info("rag_generation_gate_wait", wait_ms=gate_wait_ms)
    if result.truncated:
        log.warning("rag_generation_truncated", chars=len(result.text))
    return RagResult(
        matched=True,
        chunks=kept,
        answer=result.text,
        truncated=result.truncated,
        metrics=RagMetrics(embedding_ms, retrieval_ms, generation_ms),
    )

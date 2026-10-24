"""
Thin async clients for the three RAG services (docs/design-rag.md §5.1, §5.2).

This is the only module that talks to Ollama, Infinity or ChromaDB, and the
place to mock them in tests. Every call has a timeout, and any failure to
reach a service is raised as `ServiceUnavailable`, so callers treat "service
down" the same way everywhere: the live path posts nothing, ingestion records
`last_error`, and the compare endpoint returns 503.

Nothing here blocks the event loop: Infinity and Ollama go through
`httpx.AsyncClient`, and ChromaDB through its own `AsyncHttpClient`.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from ...config import settings

logger = structlog.get_logger()

# Tests swap this for an httpx.MockTransport.
_transport: httpx.AsyncBaseTransport | None = None

_MODELS_CACHE_S = 30.0
_models_cache: tuple[float, frozenset[str]] | None = None

_chroma_client: Any = None
_chroma_lock = asyncio.Lock()


class ServiceUnavailable(Exception):
    """A RAG service couldn't be reached or answered with an error."""

    def __init__(self, service: str, detail: str):
        self.service = service
        self.detail = detail
        super().__init__(f"{service} unavailable: {detail}")


def _client(base_url: str, timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=base_url, timeout=timeout, transport=_transport)


def _timeout(timeout: float | None) -> float:
    """A request's timeout: the caller's (at least 0.1 s), else the default."""
    return settings.RAG_SERVICE_TIMEOUT_S if timeout is None else max(timeout, 0.1)


# ── Infinity (embeddings) ────────────────────────────────────────────────────


async def embed(
    texts: list[str], model: str, *, timeout: float | None = None
) -> list[list[float]]:
    """
    Embed `texts` with `model`, in batches of `INFINITY_BATCH_SIZE` so a large
    ingestion can't grow Infinity's memory without limit. Returns one vector
    per text, in order. `timeout` (default RAG_SERVICE_TIMEOUT_S) applies to
    each request; the pipeline passes what's left of its budget.
    """
    vectors: list[list[float]] = []
    batch_size = settings.INFINITY_BATCH_SIZE
    async with _client(settings.INFINITY_URL, _timeout(timeout)) as c:
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            try:
                resp = await c.post(
                    "/embeddings", json={"model": model, "input": batch}
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise ServiceUnavailable("infinity", _describe(exc)) from exc
            try:
                data = sorted(resp.json()["data"], key=lambda d: d["index"])
                batch_vectors = [d["embedding"] for d in data]
            except (ValueError, KeyError, TypeError) as exc:
                raise ServiceUnavailable(
                    "infinity", f"malformed response: {_describe(exc)}"
                ) from exc
            # A short or long answer would silently shift every later vector
            # onto the wrong text.
            if len(batch_vectors) != len(batch):
                raise ServiceUnavailable(
                    "infinity",
                    f"returned {len(batch_vectors)} vectors for {len(batch)} texts",
                )
            vectors.extend(batch_vectors)
    return vectors


# ── Ollama (generation) ──────────────────────────────────────────────────────


def normalize_model_tag(tag: str) -> str:
    """`llama3.2` and `llama3.2:latest` name the same model."""
    return tag if ":" in tag else f"{tag}:latest"


async def list_models(*, timeout: float | None = None) -> frozenset[str]:
    """Pulled Ollama models (normalized tags), cached for ~30 s."""
    global _models_cache
    now = time.monotonic()
    if _models_cache and now - _models_cache[0] < _MODELS_CACHE_S:
        return _models_cache[1]
    async with _client(settings.OLLAMA_URL, _timeout(timeout)) as c:
        try:
            resp = await c.get("/api/tags")
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ServiceUnavailable("ollama", _describe(exc)) from exc
    try:
        models = frozenset(
            normalize_model_tag(m["name"]) for m in resp.json()["models"]
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise ServiceUnavailable(
            "ollama", f"malformed response: {_describe(exc)}"
        ) from exc
    _models_cache = (now, models)
    return models


async def has_model(tag: str, *, timeout: float | None = None) -> bool:
    return normalize_model_tag(tag) in await list_models(timeout=timeout)


@dataclass(frozen=True)
class ChatResult:
    text: str
    # True when the answer is cut off: the deadline passed, or it hit
    # `num_predict` (Ollama's done_reason "length"). The live path never
    # posts a truncated answer; compare returns it as is (§5.3).
    truncated: bool


async def chat(
    model: str,
    messages: list[dict[str, str]],
    *,
    options: dict[str, Any],
    deadline: float,
) -> ChatResult:
    """
    Stream a chat completion until it finishes or `deadline` (a
    `time.monotonic()` value) passes. The deadline is a total budget: it also
    covers waiting for Ollama to load the model and start answering. On
    timeout, returns the text received so far (possibly empty) with
    `truncated=True` instead of raising. An answer that stopped at the
    `num_predict` cap is `truncated` too, since it ends mid-sentence.
    """
    parts: list[str] = []
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return ChatResult("", truncated=True)
    body = {"model": model, "messages": messages, "stream": True, "options": options}
    # The overall budget is enforced by asyncio.timeout below; httpx's own
    # read timeout only has to be longer than it.
    async with _client(settings.OLLAMA_URL, remaining + 5) as c:
        try:
            async with asyncio.timeout(remaining):
                async with c.stream("POST", "/api/chat", json=body) as resp:
                    if resp.status_code >= 400:
                        await resp.aread()
                        raise ServiceUnavailable(
                            "ollama", f"HTTP {resp.status_code}: {resp.text[:200]}"
                        )
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                        except ValueError as exc:
                            raise ServiceUnavailable(
                                "ollama", f"malformed stream line: {line[:100]!r}"
                            ) from exc
                        if "error" in chunk:
                            raise ServiceUnavailable("ollama", str(chunk["error"]))
                        parts.append(chunk.get("message", {}).get("content", ""))
                        if chunk.get("done"):
                            capped = chunk.get("done_reason") == "length"
                            if capped:
                                logger.warning(
                                    "ollama_generation_hit_num_predict",
                                    model=model,
                                    chars=sum(map(len, parts)),
                                )
                            return ChatResult("".join(parts), truncated=capped)
        except TimeoutError:
            logger.warning(
                "ollama_generation_truncated", model=model, chars=sum(map(len, parts))
            )
            return ChatResult("".join(parts), truncated=True)
        except httpx.HTTPError as exc:
            raise ServiceUnavailable("ollama", _describe(exc)) from exc
    # The stream ended without a `done` chunk.
    raise ServiceUnavailable("ollama", "stream ended before the answer was done")


# ── ChromaDB (vector store) ──────────────────────────────────────────────────


async def chroma() -> Any:
    """The shared ChromaDB `AsyncHttpClient`, created on first use."""
    global _chroma_client
    if _chroma_client is not None:
        return _chroma_client
    async with _chroma_lock:
        if _chroma_client is None:
            import chromadb
            from chromadb.config import Settings as ChromaSettings

            url = httpx.URL(settings.CHROMA_URL)
            try:
                _chroma_client = await chromadb.AsyncHttpClient(
                    host=url.host,
                    port=url.port or 8000,
                    settings=ChromaSettings(anonymized_telemetry=False),
                )
            except Exception as exc:  # the client raises plain exceptions
                raise ServiceUnavailable("chromadb", _describe(exc)) from exc
    return _chroma_client


@asynccontextmanager
async def _chroma_timeout(timeout: float | None) -> AsyncIterator[None]:
    """
    The ChromaDB client has no request timeout of its own, so a hung server
    would hold a compare call past the harness's limit. Every call goes
    through this.
    """
    seconds = _timeout(timeout)
    try:
        async with asyncio.timeout(seconds):
            yield
    except TimeoutError:
        raise ServiceUnavailable(
            "chromadb", f"no answer within {seconds:.0f} s"
        ) from None


async def get_collection(name: str, *, timeout: float | None = None) -> Any | None:
    """The collection named `name`, or None if it doesn't exist."""
    client = await chroma()
    try:
        async with _chroma_timeout(timeout):
            return await client.get_collection(name)
    except ServiceUnavailable:
        raise
    except Exception as exc:
        if _is_not_found(exc):
            return None
        raise ServiceUnavailable("chromadb", _describe(exc)) from exc


async def get_or_create_collection(name: str, metadata: dict[str, Any]) -> Any:
    """
    The collection named `name`, created with cosine distance and `metadata`
    if it doesn't exist. An existing collection keeps its own metadata; the
    caller compares it (ingestion checks the stored profile hash, §6.2).
    """
    existing = await get_collection(name)
    if existing is not None:
        return existing
    client = await chroma()
    try:
        async with _chroma_timeout(None):
            return await client.create_collection(
                name,
                metadata=metadata,
                configuration={"hnsw": {"space": "cosine"}},
                # Vectors always come from Infinity; never let Chroma embed.
                embedding_function=None,
                get_or_create=True,  # another sync may have just created it
            )
    except ServiceUnavailable:
        raise
    except Exception as exc:
        raise ServiceUnavailable("chromadb", _describe(exc)) from exc


async def add_chunks(
    collection: Any,
    ids: list[str],
    embeddings: list[list[float]],
    documents: list[str],
    metadatas: list[dict[str, Any]],
) -> None:
    try:
        async with _chroma_timeout(None):
            await collection.add(
                ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas
            )
    except ServiceUnavailable:
        raise
    except Exception as exc:
        raise ServiceUnavailable("chromadb", _describe(exc)) from exc


async def get_chunk_metadata(
    collection: Any, where: dict[str, Any]
) -> list[dict[str, Any]]:
    """The metadata of every chunk matching `where` (no vectors or text)."""
    try:
        async with _chroma_timeout(None):
            result = await collection.get(where=where, include=["metadatas"])
    except ServiceUnavailable:
        raise
    except Exception as exc:
        raise ServiceUnavailable("chromadb", _describe(exc)) from exc
    return list(result.get("metadatas") or [])


@dataclass(frozen=True)
class Hit:
    """One query result: the stored text and metadata, and its cosine
    distance (collections use cosine space, so similarity = 1 - distance)."""

    text: str
    metadata: dict[str, Any]
    distance: float


async def query_chunks(
    collection: Any,
    embedding: list[float],
    n: int,
    where: dict[str, Any],
    *,
    timeout: float | None = None,
) -> list[Hit]:
    """The `n` nearest chunks matching `where`, nearest first."""
    try:
        async with _chroma_timeout(timeout):
            result = await collection.query(
                query_embeddings=[embedding],
                n_results=n,
                where=where,
                include=["documents", "metadatas", "distances"],
            )
    except ServiceUnavailable:
        raise
    except Exception as exc:
        raise ServiceUnavailable("chromadb", _describe(exc)) from exc
    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]
    return [
        Hit(text or "", dict(meta or {}), float(dist))
        for text, meta, dist in zip(documents, metadatas, distances, strict=True)
    ]


async def delete_chunks(collection: Any, where: dict[str, Any]) -> None:
    try:
        async with _chroma_timeout(None):
            await collection.delete(where=where)
    except ServiceUnavailable:
        raise
    except Exception as exc:
        raise ServiceUnavailable("chromadb", _describe(exc)) from exc


def _is_not_found(exc: Exception) -> bool:
    name = type(exc).__name__
    return name in ("NotFoundError", "InvalidCollectionException") or (
        isinstance(exc, ValueError) and "does not exist" in str(exc)
    )


# ── Health ───────────────────────────────────────────────────────────────────


async def health() -> dict[str, dict[str, Any]]:
    """
    Reachability of each service, for the staff `rag/health` endpoint and the
    T5 checks. Never raises: an unreachable service is reported, not thrown.
    """

    async def check_ollama() -> dict[str, Any]:
        global _models_cache
        _models_cache = None  # report the live state, not the cache
        return {"ok": True, "models": sorted(await list_models())}

    async def check_infinity() -> dict[str, Any]:
        async with _client(settings.INFINITY_URL, 5) as c:
            resp = await c.get("/models")
            resp.raise_for_status()
        return {"ok": True, "models": sorted(m["id"] for m in resp.json()["data"])}

    async def check_chroma() -> dict[str, Any]:
        client = await chroma()
        async with _chroma_timeout(5):
            await client.heartbeat()
        return {"ok": True}

    checks = {
        "ollama": check_ollama(),
        "infinity": check_infinity(),
        "chromadb": check_chroma(),
    }
    results = await asyncio.gather(*checks.values(), return_exceptions=True)
    report: dict[str, dict[str, Any]] = {}
    for name, result in zip(checks, results):
        if isinstance(result, BaseException):
            detail = (
                result.detail
                if isinstance(result, ServiceUnavailable)
                else _describe(result)
            )
            report[name] = {"ok": False, "error": detail}
        else:
            report[name] = result
    return report


def _describe(exc: BaseException) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    return f"{type(exc).__name__}: {exc}"[:300]

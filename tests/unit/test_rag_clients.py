"""
Unit tests for the RAG service clients (docs/design-rag.md §5.2, §5.3).

Ollama and Infinity are replaced with an httpx.MockTransport, so no service
needs to run. The live services are exercised by the integration tests.
"""

from __future__ import annotations

import asyncio
import json
import time

import httpx
import pytest


@pytest.fixture
def clients(monkeypatch):
    from app.services.rag import clients as mod

    monkeypatch.setattr(mod, "_models_cache", None)
    return mod


def _use(monkeypatch, mod, handler) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    async def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        result = handler(request)
        if asyncio.iscoroutine(result):
            result = await result
        return result

    monkeypatch.setattr(mod, "_transport", httpx.MockTransport(record))
    return seen


# ── embed ────────────────────────────────────────────────────────────────────


async def test_embed_batches_and_keeps_order(monkeypatch, clients):
    monkeypatch.setattr(clients.settings, "INFINITY_BATCH_SIZE", 2)

    def handler(request):
        texts = json.loads(request.content)["input"]
        # Return the batch out of order: the client must sort by index.
        data = [{"index": i, "embedding": [float(len(t))]} for i, t in enumerate(texts)]
        return httpx.Response(200, json={"data": list(reversed(data))})

    seen = _use(monkeypatch, clients, handler)
    vectors = await clients.embed(["a", "bb", "ccc", "dddd", "eeeee"], "m")

    assert vectors == [[1.0], [2.0], [3.0], [4.0], [5.0]]
    assert [len(json.loads(r.content)["input"]) for r in seen] == [2, 2, 1]


async def test_embed_error_is_service_unavailable(monkeypatch, clients):
    _use(monkeypatch, clients, lambda r: httpx.Response(500))

    with pytest.raises(clients.ServiceUnavailable) as err:
        await clients.embed(["a"], "m")

    assert err.value.service == "infinity"


async def test_embed_unreachable_is_service_unavailable(monkeypatch, clients):
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    _use(monkeypatch, clients, handler)

    with pytest.raises(clients.ServiceUnavailable):
        await clients.embed(["a"], "m")


# ── models ───────────────────────────────────────────────────────────────────


def test_normalize_model_tag(clients):
    assert clients.normalize_model_tag("llama3.2") == "llama3.2:latest"
    assert clients.normalize_model_tag("qwen2.5:1.5b") == "qwen2.5:1.5b"


async def test_has_model_normalizes_and_caches(monkeypatch, clients):
    tags = {"models": [{"name": "qwen2.5:1.5b"}, {"name": "llama3.2:latest"}]}
    seen = _use(monkeypatch, clients, lambda r: httpx.Response(200, json=tags))

    assert await clients.has_model("llama3.2")
    assert await clients.has_model("qwen2.5:1.5b")
    assert not await clients.has_model("qwen2.5:3b")
    assert len(seen) == 1  # cached after the first call


# ── chat ─────────────────────────────────────────────────────────────────────


def _ndjson(*chunks: dict) -> bytes:
    return b"".join(json.dumps(c).encode() + b"\n" for c in chunks)


async def test_chat_returns_full_answer(monkeypatch, clients):
    body = _ndjson(
        {"message": {"content": "3 slip "}, "done": False},
        {"message": {"content": "days"}, "done": False},
        {"message": {"content": ""}, "done": True},
    )
    seen = _use(monkeypatch, clients, lambda r: httpx.Response(200, content=body))

    result = await clients.chat(
        "qwen2.5:1.5b",
        [{"role": "user", "content": "?"}],
        options={"temperature": 0},
        deadline=time.monotonic() + 10,
    )

    assert result == clients.ChatResult("3 slip days", truncated=False)
    sent = json.loads(seen[0].content)
    assert sent["stream"] is True and sent["options"] == {"temperature": 0}


async def test_chat_deadline_returns_partial_text(monkeypatch, clients):
    class SlowStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield _ndjson({"message": {"content": "partial"}, "done": False})
            await asyncio.sleep(5)  # the model keeps going past the deadline
            yield _ndjson({"message": {"content": " more"}, "done": True})

    _use(monkeypatch, clients, lambda r: httpx.Response(200, stream=SlowStream()))

    started = time.monotonic()
    result = await clients.chat("m", [], options={}, deadline=time.monotonic() + 0.3)

    assert result == clients.ChatResult("partial", truncated=True)
    assert time.monotonic() - started < 2


async def test_chat_past_deadline_does_not_call_ollama(monkeypatch, clients):
    seen = _use(monkeypatch, clients, lambda r: httpx.Response(200))

    result = await clients.chat("m", [], options={}, deadline=time.monotonic() - 1)

    assert result == clients.ChatResult("", truncated=True)
    assert seen == []


async def test_chat_error_status_is_service_unavailable(monkeypatch, clients):
    _use(
        monkeypatch,
        clients,
        lambda r: httpx.Response(404, json={"error": "model not found"}),
    )

    with pytest.raises(clients.ServiceUnavailable) as err:
        await clients.chat("m", [], options={}, deadline=time.monotonic() + 5)

    assert "404" in err.value.detail


async def test_chat_stream_without_done_is_service_unavailable(monkeypatch, clients):
    body = _ndjson({"message": {"content": "cut"}, "done": False})
    _use(monkeypatch, clients, lambda r: httpx.Response(200, content=body))

    with pytest.raises(clients.ServiceUnavailable):
        await clients.chat("m", [], options={}, deadline=time.monotonic() + 5)


# ── health ───────────────────────────────────────────────────────────────────


async def test_health_reports_down_services_without_raising(monkeypatch, clients):
    def handler(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen2.5:1.5b"}]})
        raise httpx.ConnectError("refused", request=request)

    async def chroma_down():
        raise clients.ServiceUnavailable("chromadb", "refused")

    _use(monkeypatch, clients, handler)
    monkeypatch.setattr(clients, "chroma", chroma_down)

    report = await clients.health()

    assert report["ollama"] == {"ok": True, "models": ["qwen2.5:1.5b"]}
    assert report["infinity"]["ok"] is False
    assert report["chromadb"] == {"ok": False, "error": "refused"}

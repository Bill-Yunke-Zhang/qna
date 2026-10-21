"""
Ingestion profiles: the fixed list of chunking + embedding setups
(docs/design-rag.md §6.2).

A profile decides everything that is baked into stored vectors. Each course
gets one ChromaDB collection per profile (`course_{id}__{name}`). Query-time
settings (threshold, system prompt, generation model) are not here; they are
per request (`RagConfig`).

**Never change a profile under its own name.** Stored vectors would no longer
match its definition. Add a profile with a new name instead.
`tests/unit/test_profiles.py` pins every profile's `definition_hash()`, so a
change under the same name fails the merge request pipeline.

Structural splitting (web pages by heading, markdown by section, historical
Q&A pairs never split) is the same in every profile. A profile only picks the
fallback chunker used inside oversized sections and long passages; PDFs
always use it. All sizes are counted in word-pieces of one fixed tokenizer
(MiniLM's, `CHUNK_TOKENIZER_PATH`) in every profile, so profiles that differ
only in the embedding model get identical chunk boundaries.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

# Resource types that go through a fallback chunker. Historical Q&A pairs are
# atomic (never split), so they have none. Values match chunk metadata and
# eval/ground_truth.json (§3.1).
CHUNKED_RESOURCE_TYPES = ("syllabus", "schedule", "repo_markdown", "repo_pdf")


@dataclass(frozen=True)
class SlidingWindow:
    """Fixed windows of `chunk_size` word-pieces, `chunk_overlap` shared."""

    chunk_size: int
    chunk_overlap: int

    def __post_init__(self) -> None:
        if not 0 <= self.chunk_overlap < self.chunk_size:
            raise ValueError("need 0 <= chunk_overlap < chunk_size")


@dataclass(frozen=True)
class Semantic:
    """
    Split into units, then merge neighbours while consecutive units' embedding
    similarity stays at or above `breakpoint_similarity` (not the retrieval
    threshold). A merged span over `max_chunk_size` word-pieces isn't cut at
    the cap: the `oversized` sliding window, with its own overlap, is run
    over just that span (the spec's rule for semantic chunking).
    """

    unit: Literal["sentence", "paragraph"]
    breakpoint_similarity: float
    max_chunk_size: int
    oversized: SlidingWindow

    def __post_init__(self) -> None:
        if self.oversized.chunk_size > self.max_chunk_size:
            raise ValueError("oversized window must fit within max_chunk_size")


@dataclass(frozen=True)
class PerPage:
    """One chunk per PDF page; a page longer than the window uses `oversized`."""

    oversized: SlidingWindow


Chunker = SlidingWindow | Semantic | PerPage


@dataclass(frozen=True)
class Profile:
    name: str
    embedding_model: str
    # Hugging Face commit, also passed to Infinity (--revision) so a fresh
    # model cache downloads the weights the stored vectors were made with.
    embedding_revision: str
    query_prefix: str
    document_prefix: str
    chunkers: Mapping[str, Chunker]

    def __post_init__(self) -> None:
        if set(self.chunkers) != set(CHUNKED_RESOURCE_TYPES):
            raise ValueError(
                f"profile {self.name!r} needs a chunker for exactly "
                f"{CHUNKED_RESOURCE_TYPES}"
            )
        object.__setattr__(self, "chunkers", MappingProxyType(dict(self.chunkers)))

    def chunker_for(self, resource_type: str) -> Chunker:
        return self.chunkers[resource_type]

    def collection_name(self, course_id: int) -> str:
        return f"course_{course_id}__{self.name}"

    def hash(self) -> str:
        """
        Hash of the settings that shape stored vectors. Saved on the ChromaDB
        collection when it's created; ingestion refuses to write into a
        collection whose saved hash differs. Leaves out `query_prefix`, which
        only affects queries.
        """
        return _digest(
            {
                "embedding_model": self.embedding_model,
                "embedding_revision": self.embedding_revision,
                "document_prefix": self.document_prefix,
                "chunkers": self.chunkers,
            }
        )

    def definition_hash(self) -> str:
        """
        Hash of every field, `query_prefix` included: it doesn't change stored
        vectors, but it changes retrieval, so T6 numbers mustn't shift under an
        unchanged name. Pinned by `test_profile_hashes_pinned`.
        """
        return _digest(
            {
                "name": self.name,
                "query_prefix": self.query_prefix,
                "ingestion": self.hash(),
            }
        )


def _canonical(value: object) -> object:
    """JSON-ready form; chunkers carry their class name so kinds can't collide."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        fields = {
            f.name: _canonical(getattr(value, f.name))
            for f in dataclasses.fields(value)
        }
        return {"kind": type(value).__name__, **fields}
    if isinstance(value, Mapping):
        return {str(k): _canonical(v) for k, v in value.items()}
    return value


def _digest(value: object) -> str:
    text = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()[:16]


# ── The profiles ─────────────────────────────────────────────────────────────

_MINILM = "sentence-transformers/all-MiniLM-L6-v2"
_MINILM_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
_GTE_QWEN2 = "Alibaba-NLP/gte-Qwen2-1.5B-instruct"
_GTE_QWEN2_REVISION = "a9af15a6372d7d6b25e9fb07c2ccb9e1fe645644"
# From the model card: queries carry a one-sentence task instruction,
# documents get none.
_GTE_QWEN2_QUERY_PREFIX = (
    "Instruct: Given a web search query, retrieve relevant passages that answer "
    "the query\nQuery: "
)
_BGE_SMALL = "BAAI/bge-small-en-v1.5"
_BGE_SMALL_REVISION = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
# From the model card at that revision: the instruction goes on retrieval
# queries only, never on passages.
_BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

# Provisional starting size (§6.2): tuned locally before T6, then frozen.
# MiniLM truncates at 256 word-pieces; 200 leaves room for a document prefix.
_BASELINE_WINDOW = SlidingWindow(chunk_size=200, chunk_overlap=40)
_SEMANTIC_PROSE = Semantic(
    unit="sentence",
    breakpoint_similarity=0.2,
    max_chunk_size=200,
    oversized=_BASELINE_WINDOW,
)

_PROFILE_LIST = (
    # Baseline: one sliding window for every type.
    Profile(
        name="sliding-window",
        embedding_model=_MINILM,
        embedding_revision=_MINILM_REVISION,
        query_prefix="",
        document_prefix="",
        chunkers={t: _BASELINE_WINDOW for t in CHUNKED_RESOURCE_TYPES},
    ),
    # Axis 1: same model, a fallback chosen per resource type.
    Profile(
        name="type-tailored",
        embedding_model=_MINILM,
        embedding_revision=_MINILM_REVISION,
        query_prefix="",
        document_prefix="",
        chunkers={
            # Prose sections change topic mid-section; a fixed window cuts
            # across those changes. Breakpoint 0.2: MiniLM similarity of
            # adjacent sentences in the eval pages and repo markdown has a
            # median of 0.22-0.40, so 0.6 split nearly every sentence (median
            # chunk 21-26 word-pieces); 0.2 splits only at the clearest topic
            # changes (median 43-56). A span over the cap is windowed with
            # the baseline window, as the spec requires.
            "syllabus": _SEMANTIC_PROSE,
            "schedule": _SEMANTIC_PROSE,
            "repo_markdown": _SEMANTIC_PROSE,
            # A slide is a self-contained unit; the baseline window runs across
            # page boundaries and mixes slides.
            "repo_pdf": PerPage(oversized=_BASELINE_WINDOW),
        },
    ),
    # Axis 2: same chunking as the baseline, a different embedding model
    # (last-token pooling).
    Profile(
        name="embedding-alt",
        embedding_model=_GTE_QWEN2,
        embedding_revision=_GTE_QWEN2_REVISION,
        query_prefix=_GTE_QWEN2_QUERY_PREFIX,
        document_prefix="",
        chunkers={t: _BASELINE_WINDOW for t in CHUNKED_RESOURCE_TYPES},
    ),
    # Axis 2, a second data point: a small model with CLS pooling (MiniLM
    # mean-pools, gte-Qwen2 uses the last token), same chunking as the
    # baseline.
    Profile(
        name="embedding-cls",
        embedding_model=_BGE_SMALL,
        embedding_revision=_BGE_SMALL_REVISION,
        query_prefix=_BGE_QUERY_PREFIX,
        document_prefix="",
        chunkers={t: _BASELINE_WINDOW for t in CHUNKED_RESOURCE_TYPES},
    ),
)

PROFILES: Mapping[str, Profile] = MappingProxyType({p.name: p for p in _PROFILE_LIST})


def get_profile(name: str) -> Profile:
    try:
        return PROFILES[name]
    except KeyError:
        raise KeyError(f"unknown ingestion profile {name!r}") from None

"""
The shared RAG pipeline (docs/design-rag.md §5.3). One `run()` serves both the
compare endpoint and live answering, so the eval measures the code students
get. It never writes to the database.

This module holds the pipeline's contract: `RagConfig`, `RagResult` and the
errors `run()` raises, which the compare endpoint maps to status codes.
`run()` itself (retrieval with the similarity threshold, the tagged prompt and
generation through the shared gate) comes with retrieval and the prompt.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

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
    """
    raise NotImplementedError("the RAG pipeline isn't built yet")

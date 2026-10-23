from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# The compare contract (docs/design-rag.md §0), fixed by the spec and read by
# eval/compare_harness.py. Field names must match it exactly: the harness
# reads metrics with .get(name, 0), so a misspelled one would show up as 0.
# ---------------------------------------------------------------------------


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # The pipeline cuts the question to QUESTION_MAX_CHARS; this only keeps
    # an absurd body out.
    question: str = Field(..., min_length=1, max_length=20_000)
    ingestion_profile: str = Field(..., min_length=1, max_length=64)
    # A cosine similarity (1 - cosine distance, §5.3).
    similarity_threshold: float = Field(..., ge=-1.0, le=1.0, allow_inf_nan=False)
    # Used literally as the system message, and never dropped to fit num_ctx
    # (§5.3), so it's capped well under the context window.
    system_prompt: str = Field(..., max_length=8_000)
    generation_model: str = Field(..., min_length=1, max_length=128)


class CompareChunk(BaseModel):
    resource_type: str
    source_url: str
    similarity_score: float
    text: str


class CompareMetrics(BaseModel):
    embedding_time_ms: float
    retrieval_time_ms: float
    generation_time_ms: float
    cpu_percent: float


class CompareResponse(BaseModel):
    matched: bool
    # Only chunks that passed the threshold (what went into the prompt).
    retrieved_chunks: list[CompareChunk]
    answer: str | None  # null when matched is false
    metrics: CompareMetrics

"""
The configuration comparison endpoint (docs/design-rag.md §5.3, T6). The
course's harness calls it once per question and configuration, as the
`grader` admin, and aborts the whole run on any error status, so every
failure here is deliberate: never a silent `matched: false`.

It creates no rows. The pipeline only reads, and the one query here checks
that the course exists.
"""

from __future__ import annotations

import time
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.dependencies import CourseMember, require_course_staff
from ..common.exceptions import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    ServiceUnavailableError,
)
from ..database import get_db
from ..schemas.rag import CompareRequest, CompareResponse
from ..services import resource_service
from ..services.rag import clients, compare, pipeline

logger = structlog.get_logger()

router = APIRouter(prefix="/courses/{course_id}/rag", tags=["rag"])

Staff = Annotated[CourseMember, Depends(require_course_staff)]
Db = Annotated[AsyncSession, Depends(get_db)]


@router.post("/compare", response_model=CompareResponse)
async def compare_configuration(
    course_id: int, body: CompareRequest, _: Staff, db: Db
) -> dict:
    arrival = time.monotonic()
    await resource_service.require_course(db, course_id)
    config = pipeline.RagConfig(
        ingestion_profile=body.ingestion_profile,
        similarity_threshold=body.similarity_threshold,
        system_prompt=body.system_prompt,
        generation_model=body.generation_model,
    )
    cpu = compare.CpuWindow()
    with compare.tracking():
        try:
            result = await pipeline.run(
                course_id,
                body.question,
                config,
                caller="COMPARE",
                deadline=compare.deadline(arrival),
            )
        except pipeline.UnknownProfile:
            raise InvalidInputError(
                f"Unknown ingestion profile {body.ingestion_profile!r}"
            ) from None
        except pipeline.ModelNotAvailable:
            raise InvalidInputError(
                f"Generation model {body.generation_model!r} isn't pulled into Ollama"
            ) from None
        except pipeline.ProfileNotIngested:
            raise NotFoundError(
                f"Course {course_id} has no content ingested under "
                f"{body.ingestion_profile!r}"
            ) from None
        except pipeline.ProfileStale:
            raise ConflictError(
                f"The {body.ingestion_profile!r} collection was built with a "
                "different profile definition; re-sync it"
            ) from None
        except clients.ServiceUnavailable as exc:
            raise ServiceUnavailableError(
                f"{exc.service} is unavailable: {exc.detail}"
            ) from None

    if result.truncated:
        logger.warning(
            "compare_answer_truncated",
            course_id=course_id,
            profile=body.ingestion_profile,
            model=body.generation_model,
        )
    return {
        "matched": result.matched,
        "retrieved_chunks": [
            {
                "resource_type": c.resource_type,
                "source_url": c.source_url,
                "similarity_score": c.similarity_score,
                "text": c.text,
            }
            for c in result.chunks
        ],
        "answer": result.answer if result.matched else None,
        "metrics": {
            "embedding_time_ms": result.metrics.embedding_time_ms,
            "retrieval_time_ms": result.metrics.retrieval_time_ms,
            "generation_time_ms": result.metrics.generation_time_ms,
            "cpu_percent": cpu.percent(),
        },
    }

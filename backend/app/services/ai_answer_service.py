"""
AI answers in the thread model (docs/design-rag.md §4).

`create_ai_post` is the only code that writes an AI post. An AI post is an
ordinary `ANSWER` with `author_role='AI'`, no author user, and the citations
it was posted with, so the existing accept flow works on it unchanged, and
staff can retract it (`qa_service.retract_ai_post`, §4.7).

`answer_question`, the background task that runs the RAG pipeline after a
question is created and calls `create_ai_post` (§5.4), comes with the
pipeline.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import structlog
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.exceptions import ConflictError, InvalidInputError, NotFoundError
from ..models.qa import Post, Question
from ..schemas.qa import AICitations, Citation

logger = structlog.get_logger()


async def create_ai_post(
    db: AsyncSession,
    question_id: int,
    answer: str,
    citations: Sequence[Citation | dict[str, Any]],
) -> Post:
    """
    Add an AI answer to the thread (§4.3). Citations are validated here, the
    one write path, instead of by a CHECK in MySQL: 1–3 of them, ranked
    1..n best first, each with the location its type needs (§3.1). Refuses a
    closed thread like `create_post` does. Flushes; the caller commits.
    """
    question = await db.get(Question, question_id)
    if question is None:
        raise NotFoundError(f"Question {question_id} not found")
    if question.status == "CLOSED":
        raise ConflictError("This question's thread is closed to new posts")
    if not answer.strip():
        raise InvalidInputError("An AI answer can't be empty")
    try:
        checked = AICitations(
            citations=[
                c if isinstance(c, Citation) else Citation.model_validate(c)
                for c in citations
            ]
        )
    except ValidationError as exc:
        raise InvalidInputError(f"Invalid AI citations: {exc}") from None

    post = Post(
        question_id=question_id,
        author_user_id=None,
        author_role="AI",
        kind="ANSWER",
        body=answer,
        citations=[c.model_dump(exclude_none=True) for c in checked.citations],
    )
    db.add(post)
    await db.flush()
    logger.info(
        "ai_post_created",
        question_id=question_id,
        post_id=post.id,
        citations=len(checked.citations),
    )
    return post

"""
AI answers in the thread model (docs/design-rag.md §4).

`create_ai_post` is the only code that writes an AI post. An AI post is an
ordinary `ANSWER` with `author_role='AI'`, no author user, and the citations
it was posted with, so the existing accept flow works on it unchanged, and
staff can retract it (`qa_service.retract_ai_post`, §4.7).

`answer_question` is the background task `create_question` schedules
(§5.4): it runs the shared pipeline on the new question with the live
configuration from settings and, if a source matched, posts the answer with
its citations. Every failure, a timeout, a cut-off answer or a refusal posts
nothing, and the question waits for a person, as it does without AI.
"""

from __future__ import annotations

import re
import time
from collections.abc import Sequence
from typing import Any

import structlog
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..common.exceptions import ConflictError, InvalidInputError, NotFoundError
from ..config import settings
from ..database import AsyncSessionLocal
from ..models.qa import Post, Question
from ..schemas.qa import AICitations, Citation
from .rag import clients, compare, pipeline

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


# ── Live answering (§5.4) ────────────────────────────────────────────────────

# Live tasks between scheduling and the end of generation. Changed only
# without an await in between, so no lock is needed (one event loop).
_live_waiting = 0

# A course whose live configuration can't run (profile not ingested, model
# not pulled) would otherwise log on every question: once per hour instead.
_CONFIG_WARNING_INTERVAL_S = 3600.0
_last_config_warning: dict[tuple[int, str], float] = {}


async def answer_question(course_id: int, question_id: int) -> None:
    """
    Background task after a question is committed. Never raises: anything
    that goes wrong is logged and nothing is posted.
    """
    global _live_waiting
    log = logger.bind(course_id=course_id, question_id=question_id)
    if not settings.RAG_LIVE_ENABLED:
        return
    if _live_waiting >= settings.RAG_LIVE_MAX_WAITING:
        log.info("ai_answer_skipped", reason="backlog", waiting=_live_waiting)
        return
    _live_waiting += 1  # before the first await
    try:
        if compare.active_or_ended_within(settings.RAG_COMPARE_QUIET_S):
            # A harness run is in progress: don't compete with it (§5.3).
            log.info("ai_answer_skipped", reason="compare_traffic")
            return
        text = await _question_text(question_id)
        if text is None:
            return
        result = await pipeline.run(
            course_id,
            text,
            live_config(),
            caller="LIVE",
            deadline=time.monotonic() + settings.RAG_LIVE_DEADLINE_S,
        )
    except pipeline.PipelineError as exc:
        _warn_config_once(course_id, exc)
        return
    except clients.ServiceUnavailable as exc:
        log.warning("ai_answer_failed", service=exc.service, detail=exc.detail)
        return
    except Exception:
        log.exception("ai_answer_failed")
        return
    finally:
        _live_waiting -= 1

    if not result.matched:
        log.info("ai_answer_skipped", reason="no_match")
        return
    if result.truncated:
        log.warning("ai_answer_skipped", reason="truncated")
        return
    if not result.answer or is_refusal(result.answer):
        log.info("ai_answer_skipped", reason="refusal")
        return
    citations = citations_from(result.chunks)
    if not citations:
        log.warning("ai_answer_skipped", reason="no_citable_chunk")
        return
    try:
        await _post_if_still_open(question_id, result.answer, citations)
    except Exception:
        log.exception("ai_answer_post_failed")


def live_config() -> pipeline.RagConfig:
    return pipeline.RagConfig(
        ingestion_profile=settings.RAG_LIVE_PROFILE,
        similarity_threshold=settings.RAG_LIVE_THRESHOLD,
        system_prompt=settings.RAG_LIVE_SYSTEM_PROMPT,
        generation_model=settings.RAG_LIVE_MODEL,
    )


async def _question_text(question_id: int) -> str | None:
    """Title and body, as live answering embeds and prompts them (§5.3)."""
    async with AsyncSessionLocal() as db:
        question = await db.get(Question, question_id)
        if question is None:
            return None
        return f"{question.title}\n\n{question.body}"


async def _post_if_still_open(
    question_id: int, answer: str, citations: list[dict[str, Any]]
) -> None:
    """
    Re-check the thread in a new session (the request's is closed, and
    staff may have acted during generation), then post.
    """
    async with AsyncSessionLocal() as db:
        question = await db.scalar(
            select(Question)
            .options(selectinload(Question.posts))
            .where(Question.id == question_id)
        )
        reason = skip_reason(question)
        if reason:
            logger.info("ai_answer_skipped", question_id=question_id, reason=reason)
            return
        await create_ai_post(db, question_id, answer, citations)
        await db.commit()


def skip_reason(question: Question | None) -> str | None:
    """
    Why the thread no longer gets an AI answer, or None. A student's answer
    doesn't stop it (peers aren't authoritative); an accepted answer or any
    staff answer does, and so does an existing AI post, retracted included,
    so a retracted thread is never answered again (§4.7).
    """
    if question is None:
        return "deleted"
    if question.status != "OPEN":
        return "closed"
    posts = question.posts
    if any(p.author_role == "AI" for p in posts):
        return "has_ai_post"
    if any(p.is_accepted for p in posts):
        return "has_accepted_answer"
    if any(p.author_role == "STAFF" and p.kind == "ANSWER" for p in posts):
        return "has_staff_answer"
    return None


def citations_from(chunks: Sequence[pipeline.RetrievedChunk]) -> list[dict[str, Any]]:
    """
    The best 3 distinct sources the answer was given, best first (§3.3):
    deduplicated by citation_url, or by question_id for historical Q&A.
    Chunks without the location their type needs are left out.
    """
    citations: list[dict[str, Any]] = []
    seen: set[tuple[str, Any]] = set()
    for chunk in chunks:
        meta = chunk.metadata
        if chunk.resource_type == "historical_qa":
            key = ("question_id", meta.get("question_id"))
        else:
            key = ("citation_url", meta.get("citation_url"))
        if key[1] is None or key in seen:
            continue
        seen.add(key)
        citations.append(
            {
                "rank": len(citations) + 1,
                # Citation.label allows 500 characters; a longer one (a deep
                # heading path, a long thread title) would fail validation and
                # lose the whole answer.
                "label": _clip(meta.get("label") or chunk.source_url, 500),
                "resource_type": chunk.resource_type,
                "similarity_score": round(chunk.similarity_score, 4),
                key[0]: key[1],
            }
        )
        if len(citations) == 3:
            break
    return citations


# Answers that only say the context doesn't cover the question. Matched at
# the start and only when short, so "The syllabus doesn't cover X, but Y..."
# still posts (§5.3). Tune from the answers in eval/report.md.
_REFUSAL_START = re.compile(
    r"^\W*"
    # An apology or "unfortunately" in front ("Unfortunately, the provided
    # context does not…", "I am sorry, but I cannot…").
    r"(?:(?:unfortunately|sorry|i'm sorry|i am sorry)[,.]?\s+(?:but\s+)?)?"
    r"(?:"
    r"i (?:do not|don't|cannot|can't|am unable to|am not able to)"
    r"|i'm (?:sorry|not able|unable)|sorry,"
    r"|(?:based on|from|according to) the (?:provided |given )?(?:context|information|materials?)"
    r"(?: provided)?, (?:i (?:cannot|can't|don't|do not)|there (?:is|are) (?:no|not))"
    r"|(?:the|this) (?:provided |given |tagged )?(?:context|information|material)s?"
    # qwen2.5 puts the participle after the noun: "The context provided does
    # not contain…" (found in Bill's eval run, 0/4 caught before).
    r"(?: (?:provided|given|available))?"
    r" (?:does not|doesn't|do not|don't|is not|isn't|lacks?)"
    r"|there (?:is|isn't) (?:not |no )?(?:enough |sufficient )?information"
    r"|not enough information"
    r")",
    re.IGNORECASE,
)
# "Midterm 1 is not mentioned in the provided information." The subject comes
# first, so this can't be a prefix; it counts only as the answer's first and
# only clause (nothing ending in . ; : before it), so "3 slip days; rollover
# is not mentioned in the context" is a partial answer and still posts.
_NOT_IN_CONTEXT = re.compile(
    r"^\W*[^.;:!?\n]{1,80}?\b(?:is|are) not"
    r" (?:mentioned|covered|included|provided|found|specified|stated)"
    r" in the (?:provided |given |available )?(?:context|information|materials?)\b",
    re.IGNORECASE,
)
# "The syllabus does not provide information about the midterm." qwen2.5 names
# the source instead of "the context" (live board, 10/24). Same guard as
# above: nothing ending in , . ; : before it, and nothing after it but the
# rest of that one sentence, so "…, but the rubric says X" still posts.
_SOURCE_LACKS_INFO = re.compile(
    r"^\W*[^.,;:!?\n]{1,80}?\b(?:does not|doesn't|do not|don't)"
    r" (?:provide|contain|include|give|have|offer|mention|specify)"
    r" (?:any |specific |enough |detailed |further )?(?:information|details)\b"
    r"(?:(?!\b(?:but|however|although|though)\b)[^.;:!?\n])*[.!?]?\s*$",
    re.IGNORECASE,
)
_REFUSAL_MAX_WORDS = 40


def is_refusal(answer: str) -> bool:
    # Models often write curly apostrophes ("don’t"); the patterns use '.
    text = answer.strip().replace("’", "'").replace("‘", "'")
    return len(text.split()) < _REFUSAL_MAX_WORDS and (
        _REFUSAL_START.match(text) is not None
        or _NOT_IN_CONTEXT.match(text) is not None
        or _SOURCE_LACKS_INFO.match(text) is not None
    )


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _warn_config_once(course_id: int, exc: pipeline.PipelineError) -> None:
    key = (course_id, type(exc).__name__)
    now = time.monotonic()
    last = _last_config_warning.get(key)
    if last is not None and now - last < _CONFIG_WARNING_INTERVAL_S:
        return
    _last_config_warning[key] = now
    logger.warning(
        "ai_answers_off_for_course",
        course_id=course_id,
        reason=type(exc).__name__,
        detail=str(exc),
        profile=settings.RAG_LIVE_PROFILE,
        model=settings.RAG_LIVE_MODEL,
    )

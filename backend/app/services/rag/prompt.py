"""
The user message the generation model sees (docs/design-rag.md §5.5).

The system message is only the literal `system_prompt`; everything else goes
in one tagged user message:

    <context>
    <syllabus title="Syllabus › Grading">…</syllabus>
    <course_file title="Course repo › p2-buzzer/instructions.md › Setup" lines="12-30">…</course_file>
    <past_question title="Past question › …">
    <question>…</question>
    <accepted_answer>…</accepted_answer>
    </past_question>
    </context>
    <student_question>…</student_question>

No source ids or URLs: citations come from chunk metadata, so the model has
no reason to invent `[S1]` or links. Only our own tag names are escaped in
chunk text and the question (their `<` becomes `&lt;`); other text is left
alone, because a small model copies `&amp;` and `&lt;` into its answers.

`build` keeps the whole prompt inside Ollama's context window, which would
otherwise silently cut the prompt's start, guardrail included: each chunk is
cut to PROMPT_CHUNK_MAX_CHARS, and while the estimate is over budget the
lowest-ranked chunk is dropped. The system prompt and question never are.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ...config import settings
from .chunking import TokenCounter, count_tokens

TAG_NAMES = (
    "context",
    "syllabus",
    "schedule",
    "course_file",
    "past_question",
    "question",
    "accepted_answer",
    "student_question",
)
# `<tag`, `</tag`, `< / tag`, any case, followed by anything but a name char.
_OUR_TAGS = re.compile(
    r"<(\s*/?\s*(?:" + "|".join(TAG_NAMES) + r"))(?![\w-])", re.IGNORECASE
)

_TAG_FOR_TYPE = {
    "syllabus": "syllabus",
    "schedule": "schedule",
    "repo_markdown": "course_file",
    "repo_pdf": "course_file",
    "historical_qa": "past_question",
}

# The generation model tokenizes differently from the chunking tokenizer.
TOKEN_SAFETY_MARGIN = 1.3
# Chat-template tokens around the two messages.
_TEMPLATE_TOKENS = 32


@dataclass(frozen=True)
class PromptChunk:
    """What `build` needs of a retrieved chunk."""

    resource_type: str
    text: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class Prompt:
    messages: list[dict[str, str]]
    # Indexes of the chunks that made it into the prompt, best first.
    used: list[int]


def escape(text: str) -> str:
    """Neutralizes our tag names; leaves every other `<`, `&` and quote."""
    return _OUR_TAGS.sub(r"&lt;\1", text)


def _attr(value: str) -> str:
    return escape(value).replace('"', "&quot;")


def _cap(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _location_attrs(meta: dict[str, Any]) -> str:
    if "line_start" in meta:
        return (
            f' lines="{meta["line_start"]}-{meta.get("line_end", meta["line_start"])}"'
        )
    if "page_start" in meta:
        start, end = meta["page_start"], meta.get("page_end", meta["page_start"])
        return f' pages="{start}"' if start == end else f' pages="{start}-{end}"'
    return ""


def _chunk_block(chunk: PromptChunk) -> str:
    tag = _TAG_FOR_TYPE.get(chunk.resource_type, "course_file")
    title = _attr(str(chunk.metadata.get("label", "")))
    limit = settings.PROMPT_CHUNK_MAX_CHARS
    if tag == "past_question":
        split = int(chunk.metadata.get("answer_start", 0))
        question, answer = chunk.text[:split].strip(), chunk.text[split:].strip()
        return (
            f'<past_question title="{title}">\n'
            f"<question>{escape(_cap(question, limit // 2))}</question>\n"
            f"<accepted_answer>{escape(_cap(answer, limit // 2))}</accepted_answer>\n"
            "</past_question>"
        )
    body = escape(_cap(chunk.text.strip(), limit))
    return f'<{tag} title="{title}"{_location_attrs(chunk.metadata)}>{body}</{tag}>'


def _user_message(blocks: Sequence[str], question: str) -> str:
    context = "\n".join(blocks)
    return (
        f"<context>\n{context}\n</context>\n"
        f"<student_question>{escape(question)}</student_question>"
    )


def build(
    system_prompt: str,
    chunks: Sequence[PromptChunk],
    question: str,
    counter: TokenCounter | None = None,
) -> Prompt:
    """
    The two chat messages. `chunks` are in best-match order; `question` is
    already cut to QUESTION_MAX_CHARS. Drops chunks from the end until the
    estimated size fits OLLAMA_NUM_CTX minus OLLAMA_NUM_PREDICT; the best
    chunk is always kept.
    """
    budget = settings.OLLAMA_NUM_CTX - settings.OLLAMA_NUM_PREDICT
    blocks = [_chunk_block(c) for c in chunks]
    fixed = count_tokens(system_prompt, counter) + _TEMPLATE_TOKENS
    sizes = [count_tokens(b, counter) for b in blocks]
    base = count_tokens(_user_message([], question), counter)

    used = list(range(len(blocks)))
    while (
        len(used) > 1
        and (fixed + base + sum(sizes[i] for i in used)) * (TOKEN_SAFETY_MARGIN)
        > budget
    ):
        used.pop()
    return Prompt(
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": _user_message([blocks[i] for i in used], question),
            },
        ],
        used=used,
    )

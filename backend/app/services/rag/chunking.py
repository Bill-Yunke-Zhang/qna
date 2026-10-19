"""
Splitting documents into chunks (docs/design-rag.md §6.2, §7.3, §7.4).

Two layers:

1. **Structural splitting**, the same in every profile: a web page by
   heading (`web_sections`). Markdown by section and PDFs by page come with
   repo ingestion; they only need to produce `Section`s too.
2. **The profile's fallback chunker**, applied only to a section larger than
   its size limit: `SlidingWindow`, `Semantic` or `PerPage` (profiles.py).

Chunking runs in three steps, so a semantic chunker, which needs embeddings,
never calls Infinity from inside a worker thread (§7.3):

    plan  = plan_chunks(text, sections, chunker)      # sync, in a thread
    vecs  = await clients.embed(plan.units_to_embed, model)   # only if non-empty
    chunks = finish_chunks(plan, vecs)                # sync, in a thread

All sizes are word-pieces of one fixed tokenizer (MiniLM's), whatever the
profile's embedding model, so profiles that differ only in the model get the
same chunk boundaries. Windows start and end on whitespace, never mid-word,
because Text Fragments only match whole words. Every chunk keeps its
character offsets into the document, so its exact location (Text Fragment,
line range, page range) can be computed from them.
"""

from __future__ import annotations

import bisect
import functools
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote, urlsplit, urlunsplit

from tokenizers import Tokenizer

from ...config import settings
from .fetchers import WebDocument
from .profiles import Chunker, PerPage, Semantic, SlidingWindow

HEADING_SEPARATOR = " › "

# ── Token counting ───────────────────────────────────────────────────────────


class TokenCounter(Protocol):
    def token_starts(self, text: str) -> list[int]:
        """Character offset where each token of `text` starts, in order."""
        ...


class _HFTokenCounter:
    def __init__(self, path: str):
        self._tokenizer = Tokenizer.from_file(path)
        # MiniLM's tokenizer.json pads and truncates to 128 by default, which
        # would cap every count at 128 without an error.
        self._tokenizer.no_padding()
        self._tokenizer.no_truncation()

    def token_starts(self, text: str) -> list[int]:
        encoding = self._tokenizer.encode(text, add_special_tokens=False)
        return [start for start, _ in encoding.offsets]


@functools.cache
def default_counter() -> TokenCounter:
    return _HFTokenCounter(settings.CHUNK_TOKENIZER_PATH)


def count_tokens(text: str, counter: TokenCounter | None = None) -> int:
    return len((counter or default_counter()).token_starts(text))


# ── Data ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Section:
    """
    A structural piece of a document: `text[start:end]` of the document text.
    `heading_path` is the chain of headings above it, outermost first.
    """

    start: int
    end: int
    heading_path: tuple[str, ...] = ()


@dataclass(frozen=True)
class Chunk:
    start: int
    end: int
    heading_path: tuple[str, ...]
    token_count: int

    def text(self, document_text: str) -> str:
        return document_text[self.start : self.end]


@dataclass(frozen=True)
class _Word:
    start: int
    end: int
    tokens: int


_NON_SPACE = re.compile(r"\S+")


def _words(text: str, start: int, end: int, counter: TokenCounter) -> list[_Word]:
    """Whitespace-separated words of `text[start:end]` with token counts."""
    piece = text[start:end]
    token_starts = counter.token_starts(piece)
    words = []
    for m in _NON_SPACE.finditer(piece):
        tokens = bisect.bisect_left(token_starts, m.end()) - bisect.bisect_left(
            token_starts, m.start()
        )
        words.append(_Word(start + m.start(), start + m.end(), tokens))
    return words


# ── Structural splitting: web pages ──────────────────────────────────────────


def web_sections(doc: WebDocument) -> list[Section]:
    """
    One section per heading: the text after the heading's line up to the next
    heading of any level, with the path of headings above it. Text before the
    first heading is a section with an empty path. Headings with no text under
    them produce nothing.
    """
    sections = []
    path: list[tuple[int, str]] = []
    start = 0
    for heading in (*doc.headings, None):
        end = heading.start if heading else len(doc.text)
        section = _trimmed(doc.text, start, end, tuple(t for _, t in path))
        if section:
            sections.append(section)
        if heading:
            while path and path[-1][0] >= heading.level:
                path.pop()
            path.append((heading.level, heading.text))
            start = heading.end
    return sections


def _trimmed(
    text: str, start: int, end: int, heading_path: tuple[str, ...]
) -> Section | None:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return Section(start, end, heading_path) if start < end else None


# ── Fallback chunkers ────────────────────────────────────────────────────────


def sliding_windows(
    words: Sequence[_Word], chunk_size: int, chunk_overlap: int
) -> list[tuple[int, int, int]]:
    """
    Windows of whole words, each at most `chunk_size` tokens (a single word
    longer than that is a window by itself), the next starting so that about
    `chunk_overlap` tokens are shared. Returns `(first, last + 1, tokens)`
    word index ranges.
    """
    windows = []
    first, n = 0, len(words)
    while first < n:
        last, tokens = first, 0
        while last < n and (last == first or tokens + words[last].tokens <= chunk_size):
            tokens += words[last].tokens
            last += 1
        windows.append((first, last, tokens))
        if last == n:
            break
        # Step back from the end while the shared part fits in the overlap,
        # always moving forward by at least one word.
        nxt, shared = last, 0
        while nxt - 1 > first and shared + words[nxt - 1].tokens <= chunk_overlap:
            nxt -= 1
            shared += words[nxt].tokens
        first = nxt
    return windows


def _window_chunks(
    words: Sequence[_Word], window: SlidingWindow, heading_path: tuple[str, ...]
) -> list[Chunk]:
    return [
        Chunk(words[i].start, words[j - 1].end, heading_path, tokens)
        for i, j, tokens in sliding_windows(
            words, window.chunk_size, window.chunk_overlap
        )
    ]


# A sentence ends at . ! or ? followed by whitespace, or at a line break
# (every block element of a web page is its own line).
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")


def _sentence_units(
    text: str, section: Section, max_tokens: int, counter: TokenCounter
) -> list[list[_Word]]:
    """Sentences of a section as word lists; longer sentences are cut to size."""
    units = []
    pos = section.start
    bounds = [
        m.start() for m in _SENTENCE_END.finditer(text, section.start, section.end)
    ]
    for end in (*bounds, section.end):
        words = _words(text, pos, end, counter)
        pos = end
        if not words:
            continue
        if sum(w.tokens for w in words) <= max_tokens:
            units.append(words)
        else:
            units.extend(
                list(words[i:j]) for i, j, _ in sliding_windows(words, max_tokens, 0)
            )
    return units


@dataclass
class _SemanticSection:
    section: Section
    units: list[list[_Word]]


@dataclass
class ChunkPlan:
    """
    The result of step 1. `units_to_embed` is empty unless a section went to
    a semantic chunker; then step 2 embeds those texts (with the profile's
    document prefix) and step 3 merges them.
    """

    text: str
    chunker: Chunker
    items: list[Chunk | _SemanticSection]
    units_to_embed: list[str]


def plan_chunks(
    text: str,
    sections: Sequence[Section],
    chunker: Chunker,
    counter: TokenCounter | None = None,
) -> ChunkPlan:
    """
    Step 1. A section within the chunker's size limit is one chunk; a larger
    one goes to the fallback chunker. `PerPage` treats each section (one PDF
    page) the same way, with its `oversized` window as the fallback.
    """
    counter = counter or default_counter()
    if isinstance(chunker, Semantic):
        limit = chunker.max_chunk_size
    elif isinstance(chunker, PerPage):
        limit = chunker.oversized.chunk_size
    else:
        limit = chunker.chunk_size

    items: list[Chunk | _SemanticSection] = []
    to_embed: list[str] = []
    for section in sections:
        words = _words(text, section.start, section.end, counter)
        if not words:
            continue
        tokens = sum(w.tokens for w in words)
        if tokens <= limit:
            items.append(
                Chunk(words[0].start, words[-1].end, section.heading_path, tokens)
            )
        elif isinstance(chunker, Semantic):
            units = _sentence_units(text, section, chunker.max_chunk_size, counter)
            items.append(_SemanticSection(section, units))
            to_embed.extend(text[u[0].start : u[-1].end] for u in units)
        else:
            window = chunker.oversized if isinstance(chunker, PerPage) else chunker
            items.extend(_window_chunks(words, window, section.heading_path))
    return ChunkPlan(text, chunker, items, to_embed)


def finish_chunks(
    plan: ChunkPlan, unit_vectors: Sequence[Sequence[float]] = ()
) -> list[Chunk]:
    """
    Step 3. Semantic sections: neighbouring sentences are merged while each
    one's similarity to the one before stays at or above
    `breakpoint_similarity` and the chunk stays within `max_chunk_size`.
    """
    if len(unit_vectors) != len(plan.units_to_embed):
        raise ValueError(
            f"got {len(unit_vectors)} vectors for {len(plan.units_to_embed)} units"
        )
    chunks: list[Chunk] = []
    vectors = iter(unit_vectors)
    for item in plan.items:
        if isinstance(item, Chunk):
            chunks.append(item)
            continue
        assert isinstance(plan.chunker, Semantic)
        chunks.extend(_merge_semantic(item, vectors, plan.chunker))
    return chunks


def _merge_semantic(item: _SemanticSection, vectors, chunker: Semantic) -> list[Chunk]:
    chunks = []
    current: list[_Word] = []
    tokens = 0
    previous = None
    for unit in item.units:
        vector = next(vectors)
        unit_tokens = sum(w.tokens for w in unit)
        if current and (
            _cosine(previous, vector) < chunker.breakpoint_similarity
            or tokens + unit_tokens > chunker.max_chunk_size
        ):
            chunks.append(
                Chunk(
                    current[0].start, current[-1].end, item.section.heading_path, tokens
                )
            )
            current, tokens = [], 0
        current.extend(unit)
        tokens += unit_tokens
        previous = vector
    if current:
        chunks.append(
            Chunk(current[0].start, current[-1].end, item.section.heading_path, tokens)
        )
    return chunks


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


# ── Web citations (Text Fragments, §3.1) ─────────────────────────────────────

# First and last ~5 words; a chunk under ~10 words is matched whole.
FRAGMENT_WORDS = 5
FRAGMENT_PREFIX_WORDS = 3


def heading_path_label(heading_path: Sequence[str]) -> str:
    return HEADING_SEPARATOR.join(heading_path)


def page_source_url(page_url: str) -> str:
    """The page with no location: drops any `#fragment`."""
    return urlunsplit(urlsplit(page_url)._replace(fragment=""))


def _encode_fragment_term(term: str) -> str:
    # quote() leaves "-" alone, but it marks a prefix/suffix in the syntax;
    # "," and "&" are encoded by quote(safe="").
    return quote(term, safe="").replace("-", "%2D")


def _normalize(text: str) -> str:
    return " ".join(text.split()).lower()


def web_citation(page_url: str, doc: WebDocument, chunk: Chunk) -> dict[str, str]:
    """
    Location metadata for one web-page chunk: `source_url`, `citation_url`,
    `heading_path`, `fragment_start`, `fragment_end` and, when needed,
    `fragment_prefix`. Keys that don't apply are left out (ChromaDB metadata
    can't hold None).

    `textStart` and `textEnd` each have to match inside one block of the live
    page, so they're taken from the chunk's first and last line.
    """
    lines = chunk.text(doc.text).split("\n")
    first, last = lines[0].split(), lines[-1].split()
    if len(lines) == 1 and len(first) <= 2 * FRAGMENT_WORDS:
        start, end = " ".join(first), ""
    else:
        start = " ".join(first[:FRAGMENT_WORDS])
        end = " ".join(last[-FRAGMENT_WORDS:])

    # A fragment highlights the first match on the live page, which still has
    # the navbar, footer and so on. If the start words could match before the
    # chunk, anchor them to the words just before it (usually its heading).
    # Like the other terms, the prefix must sit inside one block: it comes
    # from the text before the chunk on its own line, else the line above.
    prefix = ""
    needle = _normalize(start)
    before = doc.text[: chunk.start]
    if needle in _normalize(doc.removed_text) or needle in _normalize(before):
        lines_before = before.rstrip().split("\n") if before.strip() else [""]
        prefix = " ".join(lines_before[-1].split()[-FRAGMENT_PREFIX_WORDS:])

    terms = [_encode_fragment_term(start)]
    if end:
        terms.append(_encode_fragment_term(end))
    if prefix:
        terms.insert(0, _encode_fragment_term(prefix) + "-")
    source_url = page_source_url(page_url)

    location = {
        "source_url": source_url,
        "citation_url": f"{source_url}#:~:text={','.join(terms)}",
        "fragment_start": start,
    }
    if end:
        location["fragment_end"] = end
    if prefix:
        location["fragment_prefix"] = prefix
    if chunk.heading_path:
        location["heading_path"] = heading_path_label(chunk.heading_path)
    return location

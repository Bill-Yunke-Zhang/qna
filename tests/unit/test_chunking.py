"""
Unit tests for chunking and web citations (docs/design-rag.md §3.1, §6.2,
§7.4).

Most tests count tokens with a fake counter (one token per word or
punctuation mark) so sizes are easy to reason about. The tests marked
`real_tokenizer` use MiniLM's tokenizer.json from CHUNK_TOKENIZER_PATH and
are skipped when it isn't there (the Docker image and CI have it).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import unquote

import pytest

from app.services.rag.chunking import (
    Chunk,
    Section,
    _words,
    count_tokens,
    finish_chunks,
    plan_chunks,
    sliding_windows,
    web_citation,
    web_sections,
)
from app.services.rag.fetchers import parse_html
from app.services.rag.profiles import PROFILES, PerPage, Semantic, SlidingWindow

REPO = Path(__file__).resolve().parents[2]
SAMPLE_WEB = REPO / "eval" / "sample_data" / "web"


class FakeCounter:
    _TOKEN = re.compile(r"\w+|[^\w\s]")

    def token_starts(self, text: str) -> list[int]:
        return [m.start() for m in self._TOKEN.finditer(text)]


FAKE = FakeCounter()


def numbered_words(n: int) -> str:
    return " ".join(f"w{i}" for i in range(n))


def assert_on_word_boundaries(text: str, chunk: Chunk) -> None:
    assert not text[chunk.start].isspace() and not text[chunk.end - 1].isspace()
    assert chunk.start == 0 or text[chunk.start - 1].isspace()
    assert chunk.end == len(text) or text[chunk.end].isspace()


# ── Structural splitting ─────────────────────────────────────────────────────

PAGE = """
<html><body>
<header><nav><a href="/">Home</a> <a href="/syllabus">Syllabus</a></nav></header>
<main>
<h1>Syllabus</h1>
<p>Welcome to the course.</p>
<h2>Grading</h2>
<h3>Late policy</h3>
<p>Late work loses 10% per day.</p>
<h3>Exams</h3>
<h2>Office hours</h2>
<ul><li>Monday 2pm</li><li>Thursday 4pm</li></ul>
</main>
<footer>Copyright 2026</footer>
</body></html>
"""


def test_web_sections_follow_heading_nesting():
    doc = parse_html(PAGE)
    sections = web_sections(doc)
    got = [(s.heading_path, doc.text[s.start : s.end]) for s in sections]
    assert got == [
        (("Syllabus",), "Welcome to the course."),
        (("Syllabus", "Grading", "Late policy"), "Late work loses 10% per day."),
        # "Grading" and "Exams" have no text of their own: no section.
        (("Syllabus", "Office hours"), "Monday 2pm\nThursday 4pm"),
    ]


def test_text_before_first_heading_is_a_section():
    doc = parse_html("<p>Intro words.</p><h2>Later</h2><p>Body.</p>")
    sections = web_sections(doc)
    assert sections[0] == Section(0, len("Intro words."), ())
    assert sections[1].heading_path == ("Later",)


# ── Sliding windows ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("size,overlap", [(10, 3), (7, 0), (5, 4)])
def test_sliding_windows_respect_size_and_cover_every_word(size, overlap):
    text = numbered_words(53)
    words = _words(text, 0, len(text), FAKE)
    windows = sliding_windows(words, size, overlap)

    assert windows[0][0] == 0 and windows[-1][1] == len(words)
    for (i, j, tokens), nxt in zip(windows, [*windows[1:], None]):
        assert tokens == sum(w.tokens for w in words[i:j]) <= size
        if nxt:
            shared = sum(w.tokens for w in words[nxt[0] : j])
            assert nxt[0] > i  # always moves forward
            assert shared <= overlap
            assert nxt[0] <= j  # no gap between windows


def test_a_word_longer_than_the_window_is_its_own_window():
    text = "a " + "-" * 30 + " b"  # the dashes count as 30 tokens
    words = _words(text, 0, len(text), FAKE)
    windows = sliding_windows(words, 5, 2)
    assert [(i, j) for i, j, _ in windows] == [(0, 1), (1, 2), (2, 3)]


def test_oversized_section_is_windowed_on_word_boundaries():
    text = "Heading\n" + numbered_words(40)
    section = Section(len("Heading\n"), len(text), ("Heading",))
    plan = plan_chunks(text, [section], SlidingWindow(10, 2), FAKE)
    chunks = finish_chunks(plan)

    assert plan.units_to_embed == []
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.token_count <= 10
        assert chunk.heading_path == ("Heading",)
        assert_on_word_boundaries(text, chunk)
    assert chunks[0].start == section.start and chunks[-1].end == section.end


def test_section_within_the_limit_is_one_chunk():
    text = numbered_words(10)
    plan = plan_chunks(text, [Section(0, len(text))], SlidingWindow(10, 2), FAKE)
    assert finish_chunks(plan) == [Chunk(0, len(text), (), 10)]


def test_per_page_uses_its_oversized_window():
    pages = numbered_words(4) + "\n" + numbered_words(30)
    sections = [
        Section(0, pages.index("\n")),
        Section(pages.index("\n") + 1, len(pages)),
    ]
    plan = plan_chunks(pages, sections, PerPage(SlidingWindow(10, 0)), FAKE)
    chunks = finish_chunks(plan)
    assert chunks[0] == Chunk(0, sections[0].end, (), 4)
    assert len(chunks) == 1 + 3


# ── Semantic merging ─────────────────────────────────────────────────────────

SEMANTIC_TEXT = (
    "Cats purr. Cats nap. Cats hunt mice. Taxes are due. Taxes are hard.\nRain falls."
)


def semantic_plan(max_chunk_size: int = 100):
    section = Section(0, len(SEMANTIC_TEXT))
    # max_chunk_size below the section's size forces the fallback.
    chunker = Semantic(
        "sentence", 0.6, max_chunk_size, SlidingWindow(max_chunk_size, 2)
    )
    return plan_chunks(SEMANTIC_TEXT, [section], chunker, FAKE)


def topic_vector(sentence: str) -> list[float]:
    return {"Cats": [1.0, 0.0, 0.0], "Taxes": [0.0, 1.0, 0.0]}.get(
        sentence.split()[0], [0.0, 0.0, 1.0]
    )


def test_semantic_splits_at_topic_changes():
    plan = semantic_plan(max_chunk_size=20)
    assert plan.units_to_embed == [
        "Cats purr.",
        "Cats nap.",
        "Cats hunt mice.",
        "Taxes are due.",
        "Taxes are hard.",
        "Rain falls.",
    ]
    vectors = [topic_vector(u) for u in plan.units_to_embed]
    chunks = finish_chunks(plan, vectors)
    assert [c.text(SEMANTIC_TEXT) for c in chunks] == [
        "Cats purr. Cats nap. Cats hunt mice.",
        "Taxes are due. Taxes are hard.",
        "Rain falls.",
    ]


def assert_windowed_with_overlap(text: str, chunks: list[Chunk], cap: int) -> None:
    assert len(chunks) > 1
    for chunk, nxt in zip(chunks, chunks[1:]):
        assert chunk.token_count <= cap
        assert_on_word_boundaries(text, chunk)
        assert nxt.start < chunk.end  # shared words, not a cut at the cap
    assert chunks[-1].token_count <= cap


def test_coherent_span_over_the_cap_is_windowed_with_overlap():
    plan = semantic_plan(max_chunk_size=6)
    same_topic = [[1.0, 0.0]] * len(plan.units_to_embed)
    chunks = finish_chunks(plan, same_topic)
    assert_windowed_with_overlap(SEMANTIC_TEXT, chunks, 6)
    assert chunks[0].start == 0 and chunks[-1].end == len(SEMANTIC_TEXT)


def test_long_sentence_is_one_unit_windowed_with_overlap():
    text = numbered_words(30) + "."
    chunker = Semantic("sentence", 0.6, 10, SlidingWindow(10, 3))
    plan = plan_chunks(text, [Section(0, len(text))], chunker, FAKE)
    assert plan.units_to_embed == [text]
    assert_windowed_with_overlap(text, finish_chunks(plan, [[1.0]]), 10)


def test_oversized_window_must_fit_the_cap():
    with pytest.raises(ValueError):
        Semantic("sentence", 0.2, 100, SlidingWindow(200, 40))


def test_finish_needs_one_vector_per_unit():
    with pytest.raises(ValueError):
        finish_chunks(semantic_plan(max_chunk_size=20), [[1.0]])


# ── Text Fragment citations ──────────────────────────────────────────────────


def citation_for(html: str, needle: str, page="https://cs.example.edu/syllabus.html"):
    doc = parse_html(html)
    start = doc.text.index(needle)
    chunk = Chunk(start, start + len(needle), ("Policies",), 0)
    return web_citation(page, doc, chunk)


def test_citation_uses_first_and_last_five_words():
    body = "one two three four five six seven eight nine ten eleven twelve"
    loc = citation_for(f"<main><h2>Policies</h2><p>{body}</p></main>", body)
    assert loc["fragment_start"] == "one two three four five"
    assert loc["fragment_end"] == "eight nine ten eleven twelve"
    assert loc["citation_url"] == (
        "https://cs.example.edu/syllabus.html#:~:text="
        "one%20two%20three%20four%20five,eight%20nine%20ten%20eleven%20twelve"
    )
    assert loc["source_url"] == "https://cs.example.edu/syllabus.html"
    assert loc["heading_path"] == "Policies"
    assert "fragment_prefix" not in loc


def test_short_chunk_matches_whole_text_only():
    loc = citation_for(
        "<main><h2>P</h2><p>Office hours on Monday</p></main>", "Office hours on Monday"
    )
    assert loc["fragment_start"] == "Office hours on Monday"
    assert "fragment_end" not in loc
    assert loc["citation_url"].endswith("#:~:text=Office%20hours%20on%20Monday")


def test_start_and_end_come_from_one_line_each():
    html = "<main><ul><li>Slip days: five per term</li><li>Late work: 10% off</li></ul></main>"
    loc = citation_for(html, "Slip days: five per term\nLate work: 10% off")
    assert loc["fragment_start"] == "Slip days: five per term"
    assert loc["fragment_end"] == "Late work: 10% off"


def test_fragment_syntax_characters_are_encoded():
    text = "Due dates - P1, P2 & P3 are listed below in the table"
    loc = citation_for(f"<main><p>{text}</p></main>", text)
    fragment = loc["citation_url"].split("#:~:text=", 1)[1]
    terms = fragment.split(",")
    assert len(terms) == 2  # only the separator comma is literal
    assert "-" not in fragment and "&" not in fragment
    assert unquote(terms[0]) == "Due dates - P1, P2"


def test_prefix_added_when_start_also_appears_in_the_navbar():
    html = (
        "<nav>Home | Office Hours | Syllabus</nav><main><h2>Getting Help</h2>"
        "<p>Office Hours</p></main>"
    )
    loc = citation_for(html, "Office Hours")
    assert loc["fragment_prefix"] == "Getting Help"
    assert loc["citation_url"].endswith("#:~:text=Getting%20Help-,Office%20Hours")


def test_prefix_added_when_start_appears_earlier_on_the_page():
    html = (
        "<main><h2>Week 1</h2><p>Read chapter one</p>"
        "<h2>Week 2</h2><p>Read chapter one</p></main>"
    )
    doc = parse_html(html)
    start = doc.text.rindex("Read chapter one")
    chunk = Chunk(start, len(doc.text), ("Week 2",), 0)
    loc = web_citation("https://x.edu/s.html", doc, chunk)
    assert loc["fragment_prefix"] == "Week 2"


def test_no_prefix_when_start_only_matches_the_chunk():
    html = (
        "<nav>Office</nav><main><h2>Help</h2><p>Office Hours are on Monday</p></main>"
    )
    assert "fragment_prefix" not in citation_for(html, "Office Hours are on Monday")


def test_existing_url_fragment_is_dropped():
    loc = citation_for(
        "<main><p>Some text</p></main>", "Some text", page="https://x.edu/s.html#top"
    )
    assert loc["source_url"] == "https://x.edu/s.html"
    assert loc["citation_url"].startswith("https://x.edu/s.html#:~:text=")


# ── Real tokenizer and sample pages ──────────────────────────────────────────

TOKENIZER = os.environ.get(
    "CHUNK_TOKENIZER_PATH", "/opt/tokenizers/minilm/tokenizer.json"
)
real_tokenizer = pytest.mark.skipif(
    not Path(TOKENIZER).is_file(), reason=f"no tokenizer at {TOKENIZER}"
)


@real_tokenizer
def test_real_tokenizer_counts_past_128_tokens():
    # tokenizer.json ships with truncation to 128; counts must not stop there.
    assert count_tokens(numbered_words(300)) > 300


@real_tokenizer
@pytest.mark.parametrize("page", ["syllabus", "schedule"])
@pytest.mark.parametrize("profile", ["sliding-window", "type-tailored"])
def test_sample_pages_chunk_within_size_and_cite_their_own_text(page, profile):
    doc = parse_html((SAMPLE_WEB / f"{page}.html").read_text(encoding="utf-8"))
    chunker = PROFILES[profile].chunker_for(page)
    plan = plan_chunks(doc.text, web_sections(doc), chunker)
    # Fake unit vectors alternating between two orthogonal topics, so semantic
    # sections split at every sentence; only sizes and locations are tested.
    vectors = [
        [float(i % 2), float(1 - i % 2)] for i in range(len(plan.units_to_embed))
    ]
    chunks = finish_chunks(plan, vectors)

    limit = getattr(chunker, "chunk_size", None) or chunker.max_chunk_size
    assert chunks
    url = f"https://git.example.edu/eval/sample_data/web/{page}.html"
    for chunk in chunks:
        assert chunk.token_count <= limit
        assert count_tokens(chunk.text(doc.text)) <= limit
        assert_on_word_boundaries(doc.text, chunk)
        loc = web_citation(url, doc, chunk)
        assert "eval/sample_data/web/" in loc["source_url"]
        assert loc["fragment_start"] in chunk.text(doc.text)
        assert chunk.text(doc.text).rstrip().endswith(loc.get("fragment_end", ""))

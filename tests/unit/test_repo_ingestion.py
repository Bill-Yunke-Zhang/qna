"""
Unit tests for repo files: markdown sections, PDF pages, their citations and
repo uploads (docs/design-rag.md §3.1, §6.2, §7.4).

Token counts use a fake one-token-per-word counter, as in test_chunking.py;
the eval repo is only parsed, not chunked, so no real tokenizer is needed.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path

import pytest

from app.services.rag import ingestion
from app.services.rag.chunking import (
    Chunk,
    Section,
    markdown_citation,
    markdown_sections,
    pdf_citation,
    plan_chunks,
    sections_for,
)
from app.services.rag.fetchers import FetchError, UploadedFile, UploadError, parse_pdf
from app.services.rag.profiles import PerPage, Semantic, SlidingWindow


class FakeCounter:
    """One token per word or punctuation mark, as in test_chunking.py."""

    _TOKEN = re.compile(r"\w+|[^\w\s]")

    def token_starts(self, text: str) -> list[int]:
        return [m.start() for m in self._TOKEN.finditer(text)]


FAKE = FakeCounter()


def numbered_words(n: int) -> str:
    return " ".join(f"w{i}" for i in range(n))


REPO = Path(__file__).resolve().parents[2]
SAMPLE_REPO = REPO / "eval" / "sample_data" / "repo"
SLIDES = SAMPLE_REPO / "lecture-10" / "slides.pdf"
BASE = "https://git.example.edu/course/-/blob/main/eval/sample_data/repo"


def section_texts(text: str) -> list[tuple[tuple[str, ...], str]]:
    return [(s.heading_path, text[s.start : s.end]) for s in markdown_sections(text)]


# ── Markdown sections ────────────────────────────────────────────────────────


def test_markdown_sections_follow_the_heading_tree():
    text = (
        "Intro line.\n"
        "# Project\n"
        "About it.\n"
        "## Setup\n"
        "Run it.\n"
        "### Details ###\n"
        "Fine print.\n"
        "## Grading\n"
        "Points.\n"
        "# Appendix\n"
        "Extra.\n"
    )
    assert section_texts(text) == [
        ((), "Intro line."),
        (("Project",), "About it."),
        (("Project", "Setup"), "Run it."),
        (("Project", "Setup", "Details"), "Fine print."),
        (("Project", "Grading"), "Points."),
        (("Appendix",), "Extra."),
    ]


def test_hashes_in_code_blocks_and_mid_line_are_not_headings():
    text = (
        "# Run\n"
        "```bash\n"
        "# install first\n"
        "make\n"
        "```\n"
        "#hashtag is not a heading, nor is this # one\n"
        "~~~\n"
        "## still code\n"
        "~~~\n"
        "## Next\n"
        "Done.\n"
    )
    sections = section_texts(text)
    assert [path for path, _ in sections] == [("Run",), ("Run", "Next")]
    assert "# install first" in sections[0][1] and "## still code" in sections[0][1]


def test_empty_sections_and_empty_headings_produce_nothing():
    text = "# Title\n\n## Empty\n\n## Filled\nText\n#\nAfter a bare #.\n"
    assert section_texts(text) == [
        (("Title", "Filled"), "Text"),
        ((), "After a bare #."),
    ]


# ── Markdown citations ───────────────────────────────────────────────────────


def test_markdown_citation_lines_come_from_the_chunk_itself():
    body = "\n".join(numbered_words(5) for _ in range(6))  # 6 lines of 5 words
    text = f"# Setup\n{body}\n"
    (section,) = markdown_sections(text)
    path_section = Section(
        section.start, section.end, ("a/b.md", *section.heading_path)
    )
    plan = plan_chunks(text, [path_section], SlidingWindow(10, 0), FAKE)
    chunks = [c for c in plan.items if isinstance(c, Chunk)]
    assert len(chunks) == 3

    locs = [markdown_citation(BASE, "a/b.md", text, c, "abc123") for c in chunks]
    assert [(loc["line_start"], loc["line_end"]) for loc in locs] == [
        (2, 3),
        (4, 5),
        (6, 7),
    ]
    first = locs[0]
    assert first["source_url"] == f"{BASE}/a/b.md"
    assert first["citation_url"] == f"{BASE}/a/b.md?plain=1#L2-L3"
    assert first["heading_path"] == "Setup"  # without the file path
    assert first["file_path"] == "a/b.md" and first["commit_sha"] == "abc123"


def test_markdown_citation_single_line_and_no_heading():
    text = "Just one line here."
    chunk = Chunk(0, len(text), ("notes.md",), 4)
    loc = markdown_citation(BASE, "notes.md", text, chunk)
    assert loc["citation_url"].endswith("notes.md?plain=1#L1")
    assert "heading_path" not in loc and "commit_sha" not in loc


def test_repo_paths_are_percent_encoded_in_urls():
    loc = markdown_citation(BASE + "/", "my docs/a#b.md", "x", Chunk(0, 1, (), 1))
    assert loc["source_url"] == f"{BASE}/my%20docs/a%23b.md"
    assert loc["file_path"] == "my docs/a#b.md"


# ── PDFs ─────────────────────────────────────────────────────────────────────


def test_parse_pdf_keeps_every_page_at_its_offset():
    pdf = parse_pdf("slides.pdf", SLIDES.read_bytes())
    assert len(pdf.page_starts) == 19
    assert pdf.text.startswith("Lecture 10")
    page_15 = pdf.text[pdf.page_starts[14] : pdf.page_starts[15]]
    assert "Deterministic" in page_15  # q10's slide


@pytest.mark.parametrize("data", [b"not a pdf at all", b"%PDF-1.7\n%broken"])
def test_parse_pdf_refuses_a_damaged_file(data):
    with pytest.raises(FetchError, match="could not read bad.pdf"):
        parse_pdf("bad.pdf", data)


def test_pdf_citation_links_the_raw_file_at_the_first_page():
    page_starts = (0, 10, 20)
    chunk = Chunk(12, 25, ("slides.pdf",), 3)  # pages 2-3
    loc = pdf_citation(BASE, "lecture-10/slides.pdf", page_starts, chunk, "abc")
    raw = BASE.replace("/-/blob/", "/-/raw/")
    assert loc["source_url"] == f"{BASE}/lecture-10/slides.pdf"
    assert loc["citation_url"] == f"{raw}/lecture-10/slides.pdf#page=2"
    assert (loc["page_start"], loc["page_end"]) == (2, 3)


def test_pdf_citation_keeps_a_base_that_is_not_a_gitlab_blob():
    loc = pdf_citation("https://x.edu/files", "s.pdf", (0,), Chunk(0, 3, (), 1))
    assert loc["citation_url"] == "https://x.edu/files/s.pdf#page=1"


def test_only_per_page_keeps_pdf_pages_apart():
    pages = [Section(0, 10, ("s.pdf",)), Section(12, 20, ("s.pdf",))]
    window, per_page = SlidingWindow(200, 40), PerPage(SlidingWindow(200, 40))
    semantic = Semantic("sentence", 0.2, 200, SlidingWindow(200, 40))
    assert sections_for(per_page, "repo_pdf", pages) == pages
    for chunker in (window, semantic):
        assert sections_for(chunker, "repo_pdf", pages) == [Section(0, 20, ("s.pdf",))]
    # Other types are never merged.
    assert sections_for(window, "repo_markdown", pages) == pages


# ── Repo documents and uploads ───────────────────────────────────────────────


def sample_repo_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for path in sorted(SAMPLE_REPO.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(SAMPLE_REPO).as_posix())
    return buf.getvalue()


def test_eval_repo_upload_matches_the_ground_truth_sources():
    docs = ingestion.parse_upload("REPO", BASE, "repo.zip", sample_repo_zip())
    by_key = {d.key: d for d in docs}
    assert sorted(by_key) == [
        "lecture-10/slides.pdf",
        "p1-side-scroller/instructions.md",
        "p1-side-scroller/rubric.md",
        "p2-buzzer/docs/realtime.md",
        "p2-buzzer/instructions.md",
        "p2-buzzer/rubric.md",
    ]
    assert by_key["lecture-10/slides.pdf"].resource_type == "repo_pdf"
    assert len(by_key["lecture-10/slides.pdf"].sections) == 19
    assert by_key["p2-buzzer/rubric.md"].resource_type == "repo_markdown"

    # The harness checks `expected_source in source_url` (§3.1).
    truth = json.loads((REPO / "eval" / "ground_truth.json").read_text())
    for q in truth["questions"]:
        if not q["resource_type"].startswith("repo_"):
            continue
        prefix = "eval/sample_data/repo/"
        doc = by_key[q["expected_source"].removeprefix(prefix)]
        assert doc.resource_type == q["resource_type"]
        section = doc.sections[0]
        chunk = Chunk(section.start, section.end, section.heading_path, 1)
        assert q["expected_source"] in doc.locate(chunk)["source_url"]


def test_markdown_document_puts_the_file_path_first_in_every_heading_path():
    file = UploadedFile("docs/a.md", b"# A\r\nOne.\r\n## B\r\nTwo.\r\n")
    doc = ingestion.markdown_document(file, BASE)
    assert "\r" not in doc.text
    assert [s.heading_path for s in doc.sections] == [
        ("docs/a.md", "A"),
        ("docs/a.md", "A", "B"),
    ]
    loc = doc.locate(Chunk(doc.sections[1].start, doc.sections[1].end, (), 1))
    assert loc["line_start"] == loc["line_end"] == 4


def test_repo_documents_skip_other_files_and_files_with_no_text():
    files = [
        UploadedFile("a.md", b"# Only a heading\n"),
        UploadedFile("b.md", b"Some text."),
        UploadedFile("page.html", b"<p>hi</p>"),
    ]
    assert [d.key for d in ingestion.repo_documents(files, BASE)] == ["b.md"]


def test_a_single_markdown_file_is_a_repo_upload():
    (doc,) = ingestion.parse_upload("REPO", BASE, "notes.md", b"# Notes\nText.\n")
    assert doc.key == "notes.md"


def test_a_repo_upload_with_a_damaged_pdf_is_refused():
    with pytest.raises(FetchError, match="could not read slides.pdf"):
        ingestion.parse_upload("REPO", BASE, "slides.pdf", b"%PDF-1.7 garbage")


def test_a_repo_upload_with_no_text_is_refused():
    with pytest.raises(UploadError, match="have no text"):
        ingestion.parse_upload("REPO", BASE, "empty.md", b"# Heading only\n")

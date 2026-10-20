"""
Unit tests for web fetching and HTML stripping (docs/design-rag.md §7.4, §8).

No network: DNS goes through a fake resolver and HTTP through an
httpx.MockTransport.
"""

from __future__ import annotations

import io
import json
import stat
import zipfile

import httpx
import pytest

from app.services.rag import fetchers
from app.services.rag.fetchers import (
    FetchError,
    UnsafeURL,
    UploadedFile,
    UploadError,
    check_has_content,
    check_url,
    fetch_web_page,
    parse_html,
    read_upload,
)

PUBLIC_IP = "93.184.215.14"
DNS = {
    "cs.example.edu": [PUBLIC_IP],
    "internal.example.edu": ["10.0.0.7"],
    "metadata.example.edu": ["169.254.169.254"],
    "mixed.example.edu": [PUBLIC_IP, "127.0.0.1"],
    "mapped.example.edu": ["::ffff:127.0.0.1"],
}


@pytest.fixture(autouse=True)
def fake_dns(monkeypatch):
    async def resolve(host: str, port: int) -> list[str]:
        if host in DNS:
            return DNS[host]
        try:  # IP literals resolve to themselves
            fetchers.ipaddress.ip_address(host)
            return [host]
        except ValueError:
            raise OSError("no such host") from None

    monkeypatch.setattr(fetchers, "_resolve", resolve)


@pytest.fixture
def serve(monkeypatch):
    """Install a handler(request) -> httpx.Response as the HTTP transport."""

    def install(handler):
        monkeypatch.setattr(fetchers, "_transport", httpx.MockTransport(handler))

    return install


# ── Address check ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "ftp://cs.example.edu/syllabus.html",
        "file:///etc/passwd",
        "https://",
        "http://127.0.0.1/",
        "http://localhost.invalid/",  # doesn't resolve
        "http://[::1]:8000/",
        "http://169.254.169.254/computeMetadata/v1/",
        "http://metadata.example.edu/",
        "http://internal.example.edu/",
        "http://mixed.example.edu/",
        "http://mapped.example.edu/",
        "http://100.64.0.1/",
        "http://224.0.0.1/",
        "https://user:pass@cs.example.edu/",
        "http://cs.example.edu:99999/",
    ],
)
async def test_unsafe_urls_are_refused(url):
    with pytest.raises(UnsafeURL):
        await check_url(url)


async def test_public_url_is_allowed():
    await check_url("https://cs.example.edu/syllabus.html")


# ── Fetch ────────────────────────────────────────────────────────────────────


def html_response(body: str, **headers) -> httpx.Response:
    return httpx.Response(
        200,
        headers={"content-type": "text/html; charset=utf-8", **headers},
        content=body.encode(),
    )


async def test_fetch_returns_decoded_html(serve):
    serve(lambda request: html_response("<p>Café</p>"))
    assert await fetch_web_page("https://cs.example.edu/s.html") == "<p>Café</p>"


async def test_redirects_are_followed_and_checked_each_hop(serve):
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "/new"})
        return html_response("<p>moved</p>")

    serve(handler)
    assert await fetch_web_page("https://cs.example.edu/old") == "<p>moved</p>"
    assert seen == ["https://cs.example.edu/old", "https://cs.example.edu/new"]


async def test_redirect_to_metadata_server_is_refused(serve):
    requested = []

    def handler(request):
        requested.append(request.url.host)
        return httpx.Response(302, headers={"location": "http://169.254.169.254/"})

    serve(handler)
    with pytest.raises(UnsafeURL):
        await fetch_web_page("https://cs.example.edu/s.html")
    assert requested == ["cs.example.edu"]  # never connected to the target


async def test_redirect_loop_stops(serve):
    serve(lambda request: httpx.Response(302, headers={"location": "/again"}))
    with pytest.raises(FetchError, match="redirects"):
        await fetch_web_page("https://cs.example.edu/s.html")


async def test_oversized_page_is_refused(serve, monkeypatch):
    monkeypatch.setattr(fetchers.settings, "WEB_FETCH_MAX_BYTES", 1000)
    serve(
        lambda request: httpx.Response(
            200, headers={"content-type": "text/html"}, content=b"x" * 1001
        )
    )
    with pytest.raises(FetchError, match="larger"):
        await fetch_web_page("https://cs.example.edu/s.html")


@pytest.mark.parametrize(
    "status,content_type,match",
    [
        (404, "text/html", "HTTP 404"),
        (200, "application/pdf", "expected an HTML page"),
    ],
)
async def test_errors_and_non_html_are_refused(serve, status, content_type, match):
    serve(
        lambda request: httpx.Response(
            status, headers={"content-type": content_type}, content=b"%PDF"
        )
    )
    with pytest.raises(FetchError, match=match):
        await fetch_web_page("https://cs.example.edu/s.html")


# ── HTML → text ──────────────────────────────────────────────────────────────


def test_parse_keeps_main_and_strips_chrome():
    doc = parse_html("""
        <html><head><title>T</title><style>p{}</style></head><body>
        <a href="#main">Skip to main content</a>
        <header><nav><ul><li>Schedule</li><li>Syllabus</li></ul></nav></header>
        <main>
          <h1>Syllabus</h1>
          <p>Grading is <b>results</b>-based.</p>
          <script>var x = "not text";</script>
          <div style="display: none"><div>Loading</div>Submitted</div>
          <p hidden>Secret</p>
          <ul><li>One&nbsp;item</li><li>Two</li></ul>
        </main>
        <footer>Copyright &copy; 2026</footer>
        </body></html>
    """)
    assert doc.text == "Syllabus\nGrading is results-based.\nOne item\nTwo"
    assert [(h.level, h.text) for h in doc.headings] == [(1, "Syllabus")]
    assert doc.text[doc.headings[0].start : doc.headings[0].end] == "Syllabus"
    assert "Skip to main content" in doc.removed_text
    assert "Schedule" in doc.removed_text and "Copyright © 2026" in doc.removed_text
    assert "not text" not in doc.removed_text  # scripts aren't visible text


def test_parse_without_main_keeps_everything_but_chrome():
    doc = parse_html(
        "<nav>Menu</nav><h2>Hours</h2><p>Mon <i>2pm</i></p><footer>F</footer>"
    )
    assert doc.text == "Hours\nMon 2pm"
    assert doc.removed_text == "Menu\nF"


def test_nested_inline_heading_text_is_joined():
    doc = parse_html(
        "<main><h3><strong>Tue</strong>: Lecture 2 &mdash; Git</h3><p>x</p></main>"
    )
    assert doc.headings[0].text == "Tue: Lecture 2 — Git"


# ── JavaScript-drawn schedule ────────────────────────────────────────────────


def schedule_page(data: dict | str) -> str:
    payload = data if isinstance(data, str) else json.dumps(data)
    return (
        '<main><h1>Course Schedule</h1><div id="weeks" class="schedule-weeks"></div>'
        "<noscript>This schedule needs JavaScript</noscript>"
        f'<script id="schedule-data" type="application/json">{payload}</script>'
        "</main>"
    )


def block(kind, date, title, body):
    return {"kind": kind, "date": date, "title": title, "body": body}


SCHEDULE = {
    "sections": [
        {"key": "003", "label": "Section 003 · Tue/Thu"},
        {"key": "006", "label": "Section 006 · Mon/Wed"},
    ],
    "banners": {"1": {"unit": "<strong>Unit 1</strong> &mdash; Basics"}},
    "weeks": [
        {
            "week": 1,
            "sec003": {
                "Tue": [block("fixed", "Sep 01", "P1 Released", "<p>Due Sep 15</p>")],
                "Thu": [
                    block(
                        "lecture",
                        "Sep 03",
                        "Lecture 1 &mdash; Intro",
                        '<a href="quiz-lec003.html">Quiz 1 results</a>',
                    )
                ],
            },
            "sec006": {
                "Tue": [block("fixed", "Sep 01", "P1 Released", "<p>Due Sep 15</p>")],
                "Wed": [
                    block(
                        "lecture",
                        "Sep 02",
                        "Lecture 1 &mdash; Intro",
                        '<a href="quiz-lec006.html">Quiz 1 results</a>',
                    ),
                    block("lecture", "Sep 02", "Lab", "<p>Section 006 only</p>"),
                ],
            },
        }
    ],
}


def test_embedded_schedule_is_drawn_once_per_entry_with_each_sections_date():
    doc = parse_html(schedule_page(SCHEDULE))
    assert [(h.level, h.text) for h in doc.headings] == [
        (1, "Course Schedule"),
        (2, "Week 1"),
        (3, "P1 Released (Tue Sep 01)"),
        # Same visible text; only the link targets differ.
        (3, "Lecture 1 — Intro (Section 003: Thu Sep 03; Section 006: Wed Sep 02)"),
        (3, "Lab (Section 006: Wed Sep 02)"),
    ]
    assert "Unit 1 — Basics" in doc.text
    assert "Due Sep 15" in doc.text and "Quiz 1 results" in doc.text
    assert "JavaScript" not in doc.text  # <noscript> is still dropped


def test_malformed_schedule_data_is_an_error():
    with pytest.raises(FetchError, match="unexpected format"):
        parse_html(schedule_page("{not json"))
    with pytest.raises(FetchError, match="unexpected format"):
        parse_html(schedule_page({"weeks": []}))  # no "sections"


def test_page_without_schedule_data_is_unchanged():
    html = "<main><h1>Syllabus</h1><p>Grading</p></main>"
    assert parse_html(html).text == "Syllabus\nGrading"


def test_page_with_almost_no_text_is_refused():
    doc = parse_html('<main><h1>Course Schedule</h1><div id="weeks"></div></main>')
    with pytest.raises(FetchError, match="JavaScript"):
        check_has_content(doc)
    check_has_content(parse_html("<main><p>" + "word " * 60 + "</p></main>"))


# ── Uploads ──────────────────────────────────────────────────────────────────


def zip_of(entries) -> bytes:
    """`entries`: name -> bytes, or a ZipInfo -> bytes for special entries."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_single_files_pass_through():
    (f,) = read_upload(r"C:\Users\me\syllabus.HTML", b"<p>hi</p>")
    assert f == UploadedFile("syllabus.HTML", b"<p>hi</p>")


@pytest.mark.parametrize("name", ["notes.txt", "page.docx", "noext", ""])
def test_other_file_types_are_refused(name):
    with pytest.raises(UploadError, match="is not one of"):
        read_upload(name, b"data")


def test_empty_file_is_refused():
    with pytest.raises(UploadError, match="empty"):
        read_upload("syllabus.html", b"  \n")


def test_upload_size_is_capped(monkeypatch):
    monkeypatch.setattr(fetchers.settings, "UPLOAD_MAX_BYTES", 10)
    with pytest.raises(UploadError, match="larger than"):
        read_upload("syllabus.html", b"x" * 11)


def test_zip_keeps_md_and_pdf_and_skips_the_rest():
    data = zip_of(
        {
            "README.md": b"# Read me",
            "./docs/guide.md": b"# Guide",
            "slides/week1.PDF": b"%PDF-1.4",
            "src/main.py": b"print()",
            ".DS_Store": b"\0",
            "__MACOSX/docs/._guide.md": b"junk",
            "docs/": b"",
        }
    )
    files = read_upload("repo.zip", data)
    assert [f.path for f in files] == ["README.md", "docs/guide.md", "slides/week1.PDF"]
    assert files[1].data == b"# Guide"


@pytest.mark.parametrize(
    "name", ["../secrets.md", "docs/../../x.md", "/etc/x.md", "C:/x.md", r"..\x.md"]
)
def test_zip_paths_outside_are_refused(name):
    with pytest.raises(UploadError, match="unsafe path"):
        read_upload("repo.zip", zip_of({name: b"# x"}))


def test_zip_symlinks_are_refused():
    link = zipfile.ZipInfo("docs/env.md")
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(UploadError, match="symbolic link"):
        read_upload("repo.zip", zip_of({link: b"/app/.env"}))


def test_zip_bomb_is_stopped_while_decompressing(monkeypatch):
    monkeypatch.setattr(fetchers.settings, "UPLOAD_MAX_ENTRY_BYTES", 1_000_000)
    data = zip_of({"bomb.md": b"0" * 5_000_000})
    assert len(data) < 50_000  # small on the wire
    with pytest.raises(UploadError, match="bomb.md is larger than"):
        read_upload("repo.zip", data)


def test_zip_lying_about_its_sizes_is_still_capped(monkeypatch):
    monkeypatch.setattr(fetchers.settings, "UPLOAD_MAX_ENTRY_BYTES", 1_000_000)
    data = bytearray(zip_of({"a.md": b"0" * 2_000_000}))
    # Rewrite the declared uncompressed size (central directory) to 10 bytes.
    cd = data.rfind(b"PK\x01\x02")
    data[cd + 24 : cd + 28] = (10).to_bytes(4, "little")
    with pytest.raises(UploadError):
        read_upload("repo.zip", bytes(data))


def test_zip_total_and_file_count_are_capped(monkeypatch):
    monkeypatch.setattr(fetchers.settings, "UPLOAD_MAX_UNCOMPRESSED_BYTES", 150)
    with pytest.raises(UploadError, match="add up to more than"):
        read_upload("repo.zip", zip_of({f"{i}.md": b"x" * 60 for i in range(3)}))

    monkeypatch.setattr(fetchers.settings, "UPLOAD_MAX_FILES", 2)
    with pytest.raises(UploadError, match="more than 2"):
        read_upload("repo.zip", zip_of({f"{i}.md": b"x" for i in range(3)}))


def test_bad_zips_are_refused():
    with pytest.raises(UploadError, match="not a valid zip"):
        read_upload("repo.zip", b"PK not really")
    with pytest.raises(UploadError, match="no .md or .pdf"):
        read_upload("repo.zip", zip_of({"main.py": b"print()"}))
    with pytest.raises(UploadError, match="more than once"):
        read_upload("repo.zip", zip_of({"a.md": b"1", "./a.md": b"2"}))

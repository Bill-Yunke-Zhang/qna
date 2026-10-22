"""
Getting course material into memory for ingestion (docs/design-rag.md §5.2,
§7.4, §8): web pages (syllabus, schedule), fetched and parsed into a
`WebDocument`; uploads, checked and unzipped in memory; and the course's
historical Q&A threads, read from MySQL. Repo clones come later.

**URL fetching is an SSRF surface.** The backend runs next to MySQL, Redis,
Ollama and the GCP metadata server (`169.254.169.254`, which hands out the
VM's credentials). So only `http(s)` is allowed, every address a host
resolves to must be public, and redirects are followed one hop at a time with
the same check on each. Responses are capped in size.
**Accepted risk (§8):** DNS rebinding between the check and the connection.

`parse_html` and `read_upload` are CPU-bound; callers run them with
`asyncio.to_thread` (§5.2).
"""

from __future__ import annotations

import asyncio
import html as html_lib
import io
import ipaddress
import json
import re
import socket
import stat
import zipfile
import zlib
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import settings
from ...models.qa import Post, Question

# Tests swap these for an httpx.MockTransport and a fake resolver.
_transport: httpx.AsyncBaseTransport | None = None


async def _resolve(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(
        host, port, type=socket.SOCK_STREAM
    )
    return [info[4][0] for info in infos]


class FetchError(Exception):
    """
    The source couldn't be fetched. The message is safe to store in
    `index_syncs.last_error` and show to staff.
    """


class UnsafeURL(FetchError):
    """The URL is refused before connecting (the request returns 422)."""


# ── Address check ────────────────────────────────────────────────────────────


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])  # drop an IPv6 zone id
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    # is_global excludes private, loopback, link-local (the metadata server),
    # shared (100.64/10) and reserved ranges; multicast is checked separately.
    return ip.is_global and not ip.is_multicast


async def check_url(url: str) -> None:
    """
    Refuse anything but an `http(s)` URL whose host resolves only to public
    addresses. Run when staff register a URL and again on every redirect hop.
    """
    try:
        parts = urlsplit(url)
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise UnsafeURL(f"invalid URL: {exc}") from None
    if parts.scheme not in ("http", "https"):
        raise UnsafeURL("only http and https URLs are allowed")
    if not parts.hostname:
        raise UnsafeURL("URL has no host")
    # Credentials would be stored in fetch_url and shown in the staff UI.
    if parts.username or parts.password:
        raise UnsafeURL("URL must not contain a username or password")
    try:
        addresses = await _resolve(parts.hostname, port)
    except OSError:
        raise UnsafeURL(f"could not resolve host {parts.hostname!r}") from None
    if not addresses:
        raise UnsafeURL(f"could not resolve host {parts.hostname!r}")
    # Every address, not just the first: the connection may use any of them.
    if not all(_is_public(a) for a in addresses):
        raise UnsafeURL(f"host {parts.hostname!r} is not a public address")


# ── Fetch ────────────────────────────────────────────────────────────────────

_HTML_TYPES = ("text/html", "application/xhtml+xml")


async def fetch_web_page(url: str) -> str:
    """
    GET `url` and return its HTML as text. Redirects are followed by hand, up
    to `WEB_FETCH_MAX_REDIRECTS`, each one checked like the original URL.
    """
    async with httpx.AsyncClient(
        follow_redirects=False,
        timeout=settings.WEB_FETCH_TIMEOUT_S,
        transport=_transport,
        # Proxy settings from the environment would make the connection go
        # somewhere other than the address that was checked.
        trust_env=False,
        headers={"User-Agent": "QnA-course-ingestion/1.0"},
    ) as client:
        for _ in range(settings.WEB_FETCH_MAX_REDIRECTS + 1):
            await check_url(url)
            try:
                async with client.stream("GET", url) as resp:
                    if resp.is_redirect:
                        location = resp.headers.get("location")
                        if not location:
                            raise FetchError(
                                f"HTTP {resp.status_code} redirect without a location"
                            )
                        url = urljoin(url, location)
                        continue
                    if resp.status_code >= 400:
                        raise FetchError(f"HTTP {resp.status_code} from {url}")
                    content_type = resp.headers.get("content-type", "")
                    mime = content_type.split(";", 1)[0].strip().lower()
                    if mime and mime not in _HTML_TYPES:
                        raise FetchError(f"expected an HTML page, got {mime!r}")
                    body = await _read_capped(resp)
                    return body.decode(resp.charset_encoding or "utf-8", "replace")
            except httpx.HTTPError as exc:
                raise FetchError(
                    f"could not fetch {url}: {type(exc).__name__}"
                ) from exc
    raise FetchError(f"more than {settings.WEB_FETCH_MAX_REDIRECTS} redirects")


async def _read_capped(resp: httpx.Response) -> bytes:
    limit = settings.WEB_FETCH_MAX_BYTES
    too_big = FetchError(f"page is larger than {limit // 1_000_000} MB")
    declared = resp.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise too_big
    body = bytearray()
    # Counted while streaming: content-length can be missing or wrong.
    async for part in resp.aiter_bytes():
        body += part
        if len(body) > limit:
            raise too_big
    return bytes(body)


# ── HTML → text ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Heading:
    level: int  # 1–6
    text: str
    start: int  # offsets of the heading's line in WebDocument.text
    end: int


@dataclass(frozen=True)
class WebDocument:
    """
    A page as plain text: one line per block element, whitespace collapsed
    within each line. Chunk offsets and Text Fragments refer to `text`.
    `removed_text` is the visible text that was stripped (navbar, header,
    footer, anything outside `<main>`). The live page still shows it, so a
    Text Fragment can accidentally match there (§3.1).
    """

    text: str
    headings: tuple[Heading, ...]
    removed_text: str


# Never part of the content. Chrome is visible on the live page (the real
# syllabus has a navbar and a copyright footer that would otherwise become
# chunks, §7.4); invisible tags aren't shown at all.
_CHROME_TAGS = frozenset({"header", "nav", "footer"})
_INVISIBLE_TAGS = frozenset({"script", "style", "head", "noscript", "template", "svg"})
_SKIP_TAGS = _CHROME_TAGS | _INVISIBLE_TAGS
_BLOCK_TAGS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "dd",
        "details",
        "div",
        "dl",
        "dt",
        "fieldset",
        "figcaption",
        "figure",
        "form",
        "hr",
        "li",
        "main",
        "ol",
        "p",
        "pre",
        "section",
        "summary",
        "table",
        "td",
        "th",
        "tr",
        "ul",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
    }
)
_HEADING_TAGS = {f"h{n}": n for n in range(1, 7)}
_VOID_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "track",
        "wbr",
    }
)
_WHITESPACE = re.compile(r"\s+")  # includes &nbsp; (U+00A0)
_DISPLAY_NONE = re.compile(r"display\s*:\s*none", re.IGNORECASE)


def _is_hidden(attrs: list[tuple[str, str | None]]) -> bool:
    """Hidden until a script shows it, e.g. the pages' "Loading…" and alert boxes."""
    return any(
        name == "hidden" or (name == "style" and value and _DISPLAY_NONE.search(value))
        for name, value in attrs
    )


class _Block:
    __slots__ = ("heading_level", "parts", "region")

    def __init__(self, region: str, heading_level: int | None = None):
        self.region = region  # "main" | "other" | "removed" | "invisible"
        self.heading_level = heading_level
        self.parts: list[str] = []

    def text(self) -> str:
        return _WHITESPACE.sub(" ", "".join(self.parts)).strip()


class _PageParser(HTMLParser):
    """Splits the page into blocks, each tagged with the region it came from."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[_Block] = []
        self.saw_main = False
        self._skip: dict[str, int] = {}
        # The outermost hidden element: its tag, and how many elements with
        # that tag are open inside it (so the right end tag closes it).
        self._hidden_tag: str | None = None
        self._hidden_depth = 0
        self._main_depth = 0
        self._heading: str | None = None
        self._new_block()

    def _skipping(self) -> bool:
        return self._hidden_tag is not None or any(self._skip.values())

    def _region(self) -> str:
        if self._hidden_tag is not None or any(
            self._skip.get(t) for t in _INVISIBLE_TAGS
        ):
            return "invisible"
        if self._skipping():
            return "removed"
        return "main" if self._main_depth else "other"

    def _new_block(self, heading_level: int | None = None) -> None:
        self.blocks.append(_Block(self._region(), heading_level))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in _VOID_TAGS:
            if tag == self._hidden_tag:
                self._hidden_depth += 1
            elif self._hidden_tag is None and _is_hidden(attrs):
                self._hidden_tag, self._hidden_depth = tag, 1
            if tag in _SKIP_TAGS:
                self._skip[tag] = self._skip.get(tag, 0) + 1
        if tag == "main" and not self._skipping():
            self.saw_main = True
            self._main_depth += 1
        if tag in _HEADING_TAGS and self._heading is None:
            self._heading = tag
            self._new_block(_HEADING_TAGS[tag])
        elif tag in _BLOCK_TAGS or tag in _SKIP_TAGS:
            self._new_block()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _BLOCK_TAGS:
            self._new_block()

    def handle_endtag(self, tag: str) -> None:
        if tag == self._heading:
            self._heading = None
            self._new_block()
            return
        if tag == self._hidden_tag:
            self._hidden_depth -= 1
            if not self._hidden_depth:
                self._hidden_tag = None
        if tag in _SKIP_TAGS and self._skip.get(tag):
            self._skip[tag] -= 1
        if tag == "main" and self._main_depth:
            self._main_depth -= 1
        if tag in _BLOCK_TAGS or tag in _SKIP_TAGS:
            self._new_block()

    def handle_data(self, data: str) -> None:
        block = self.blocks[-1]
        # A block opened before a region change (e.g. text right after </nav>)
        # belongs to the region the text is actually in.
        region = self._region()
        if block.region != region:
            if block.parts:
                self._new_block(block.heading_level)
            else:
                block.region = region
            block = self.blocks[-1]
        block.parts.append(data)


def parse_html(html: str) -> WebDocument:
    """
    Strip a page to its text, keeping heading positions. When the page has a
    `<main>` element, only its contents are kept; everything else visible
    goes to `removed_text`. A course schedule drawn by JavaScript is
    rendered here first (`_render_embedded_schedule`).
    """
    parser = _PageParser()
    parser.feed(_render_embedded_schedule(html))
    parser.close()
    keep = "main" if parser.saw_main else "other"

    lines: list[str] = []
    removed: list[str] = []
    headings: list[Heading] = []
    offset = 0
    for block in parser.blocks:
        text = block.text()
        if not text or block.region == "invisible":
            continue
        if block.region != keep:
            removed.append(text)
            continue
        if block.heading_level is not None:
            headings.append(
                Heading(block.heading_level, text, offset, offset + len(text))
            )
        lines.append(text)
        offset += len(text) + 1  # the "\n" joining lines
    return WebDocument(
        text="\n".join(lines),
        headings=tuple(headings),
        removed_text="\n".join(removed),
    )


# Fewer characters than this after stripping means the content wasn't in the
# HTML, most likely because the page draws it with JavaScript.
MIN_PAGE_TEXT_CHARS = 200


def check_has_content(doc: WebDocument) -> None:
    """Refuse a page that strips to almost nothing instead of indexing it."""
    if len(doc.text) < MIN_PAGE_TEXT_CHARS:
        raise FetchError(
            f"page has only {len(doc.text)} characters of text; its content may "
            "be drawn by JavaScript, which ingestion doesn't run. Upload a saved "
            "copy instead."
        )


# ── JavaScript-drawn course schedule ─────────────────────────────────────────
#
# The live schedule (aicoding.cs.wisc.edu/…/schedule.html) ships an empty
# `<div id="weeks">` and the whole schedule as JSON in
# `<script id="schedule-data" type="application/json">`, which js/schedule.js
# draws for one lecture section at a time. We draw it here in the same
# structure (an h2 per week, an h3 per entry, the entry's HTML body), for
# every section. Most entries are identical across sections (lectures differ
# only by day), so each is kept once with every section's date in its
# heading; duplicates would take two of the TOP_K retrieval slots.

_SCHEDULE_DATA = re.compile(
    r"<script\b[^>]*\bid=[\"']schedule-data[\"'][^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)
_WEEKS_DIV = re.compile(r"<div\b[^>]*\bid=[\"']weeks[\"'][^>]*>", re.IGNORECASE)
_DAY_ORDER = ("Mon", "Tue", "Wed", "Thu", "Fri")


def _render_embedded_schedule(html: str) -> str:
    match = _SCHEDULE_DATA.search(html)
    if not match:
        return html
    try:
        data = json.loads(match.group(1))
        rendered = _schedule_html(data)
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise FetchError(
            f"the page's schedule data has an unexpected format: {exc!r}"
        ) from None
    weeks = _WEEKS_DIV.search(html)
    if weeks:
        return html[: weeks.end()] + rendered + html[weeks.end() :]
    return html[: match.start()] + rendered + html[match.start() :]


def _schedule_html(data: dict) -> str:
    sections = [
        (s["key"], str(s.get("label") or f"Section {s['key']}").split("·")[0].strip())
        for s in data["sections"]
    ]
    banners = data.get("banners") or {}
    parts = []
    for week in data["weeks"]:
        number = week["week"]
        parts.append(f"<h2>Week {number}</h2>")
        banner = banners.get(str(number)) or {}
        for key in ("unit", "event"):
            if banner.get(key):
                parts.append(f"<p>{banner[key]}</p>")

        # Entries match on visible text: sections' copies of a lecture can
        # differ only in link targets (e.g. quiz-02-lec003 vs -lec006.html).
        # Visible text -> (title, first section's body HTML, dates), in order
        # of first appearance.
        entries: dict[tuple[str, str, str], tuple[str, str, list[tuple[str, str]]]] = {}
        for key, label in sections:
            days = week.get(f"sec{key}") or {}
            for day in _DAY_ORDER:
                for block in days.get(day) or []:
                    title, body = block["title"], block["body"]
                    visible = (block["kind"], _visible(title), _visible(body))
                    entry = entries.setdefault(visible, (title, body, []))
                    entry[2].append((label, f"{day} {block['date']}"))

        for title, body, dates in entries.values():
            if len(dates) == len(sections) and len({w for _, w in dates}) == 1:
                when = dates[0][1]  # the same day in every section
            else:
                when = "; ".join(f"{label}: {w}" for label, w in dates)
            parts.append(f"<h3>{title} ({html_lib.escape(when)})</h3>")
            parts.append(f"<div>{body}</div>")
    return "\n".join(parts)


_TAG = re.compile(r"<[^>]*>")


def _visible(fragment: str) -> str:
    """Rough visible text of an HTML fragment, for comparing entries."""
    return " ".join(html_lib.unescape(_TAG.sub(" ", fragment)).split())


# ── Uploads ──────────────────────────────────────────────────────────────────
#
# The upload fallback (§3.2, §7.2). Nothing is written to disk: a zip is read
# entry by entry in memory and the files are handed on as bytes. Every size is
# counted while decompressing, since a zip's declared sizes can lie.


class UploadError(FetchError):
    """The upload is refused (the request returns 422)."""


@dataclass(frozen=True)
class UploadedFile:
    path: str  # inside the zip, '/'-separated; the file name for a single file
    data: bytes


UPLOAD_FILE_TYPES = (".html", ".htm", ".md", ".pdf")
# What a zip can contribute: repo files. Anything else in it is skipped unread.
ZIP_MEMBER_TYPES = (".md", ".pdf")

_READ_PIECE = 64 * 1024
_DRIVE = re.compile(r"^[A-Za-z]:")


def read_upload(filename: str, data: bytes) -> list[UploadedFile]:
    """
    Check an uploaded file against the limits in §7.2 and return its files:
    the file itself, or a zip's `.md` and `.pdf` entries. Raises `UploadError`.
    CPU-bound for a zip; callers run it with `asyncio.to_thread`.
    """
    if len(data) > settings.UPLOAD_MAX_BYTES:
        raise UploadError(
            f"upload is larger than {settings.UPLOAD_MAX_BYTES // (1024 * 1024)} MB"
        )
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    lower = name.lower()
    if lower.endswith(".zip"):
        return _read_zip(data)
    if lower.endswith(UPLOAD_FILE_TYPES):
        if not data.strip():
            raise UploadError(f"{name} is empty")
        return [UploadedFile(name, data)]
    raise UploadError(
        f"{name or 'the upload'} is not one of "
        f"{', '.join(UPLOAD_FILE_TYPES + ('.zip',))}"
    )


def _read_zip(data: bytes) -> list[UploadedFile]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise UploadError("not a valid zip file") from None

    files: list[UploadedFile] = []
    seen: set[str] = set()
    total = 0
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            path = _zip_entry_path(info)
            if path.startswith("__MACOSX/") or not path.lower().endswith(
                ZIP_MEMBER_TYPES
            ):
                continue
            if path in seen:
                raise UploadError(f"the zip has {path} more than once")
            seen.add(path)
            if len(files) == settings.UPLOAD_MAX_FILES:
                raise UploadError(
                    f"the zip has more than {settings.UPLOAD_MAX_FILES} "
                    ".md and .pdf files"
                )
            body = _read_entry(archive, info, path, settings.UPLOAD_MAX_ENTRY_BYTES)
            total += len(body)
            if total > settings.UPLOAD_MAX_UNCOMPRESSED_BYTES:
                raise UploadError(
                    "the zip's files add up to more than "
                    f"{settings.UPLOAD_MAX_UNCOMPRESSED_BYTES // (1024 * 1024)} MB"
                )
            files.append(UploadedFile(path, body))
    if not files:
        raise UploadError("the zip has no .md or .pdf files")
    return files


def _zip_entry_path(info: zipfile.ZipInfo) -> str:
    """The entry's relative path; refuses anything that could point outside."""
    raw = info.filename.replace("\\", "/")
    parts = [p for p in raw.split("/") if p not in ("", ".")]
    if raw.startswith("/") or _DRIVE.match(raw) or ".." in parts or not parts:
        raise UploadError(f"zip entry {info.filename!r} has an unsafe path")
    # Unix mode bits sit in the high 16 bits of external_attr.
    if stat.S_ISLNK(info.external_attr >> 16):
        raise UploadError(f"zip entry {info.filename!r} is a symbolic link")
    return "/".join(parts)


def _read_entry(
    archive: zipfile.ZipFile, info: zipfile.ZipInfo, path: str, limit: int
) -> bytes:
    body = bytearray()
    try:
        with archive.open(info) as entry:
            while piece := entry.read(_READ_PIECE):
                body += piece
                if len(body) > limit:
                    raise UploadError(
                        f"{path} is larger than {limit // (1024 * 1024)} MB "
                        "uncompressed"
                    )
    except UploadError:
        raise
    # Encrypted entries (RuntimeError), unsupported compression
    # (NotImplementedError) and corrupt data (BadZipFile, zlib.error, EOFError).
    except (
        RuntimeError,
        NotImplementedError,
        zipfile.BadZipFile,
        zlib.error,
        EOFError,
    ):
        raise UploadError(f"could not read {path} from the zip") from None
    return bytes(body)


# ── PDFs ─────────────────────────────────────────────────────────────────────

# Slide decks and handouts are tens of pages; this only bounds the CPU a
# hostile file can take (its size is already capped by the upload limits).
PDF_MAX_PAGES = 500


@dataclass(frozen=True)
class PdfText:
    """A PDF's text, its pages joined by a blank line. Page i+1 starts at
    `page_starts[i]`."""

    text: str
    page_starts: tuple[int, ...]


def parse_pdf(path: str, data: bytes) -> PdfText:
    """
    Text per page (§7.4), for `repo_pdf` chunks with page numbers. Raises
    `FetchError` for a PDF that can't be read, is encrypted, or is too long.
    A page with no extractable text (a picture) is kept empty, so later page
    numbers stay right. CPU-bound; run it in a thread.
    """
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise FetchError(f"{path} is encrypted")
        if len(reader.pages) > PDF_MAX_PAGES:
            raise FetchError(f"{path} has more than {PDF_MAX_PAGES} pages")
        pages = [page.extract_text() or "" for page in reader.pages]
    except FetchError:
        raise
    # pypdf raises many kinds of errors on a damaged file.
    except Exception:
        raise FetchError(f"could not read {path} as a PDF") from None

    parts: list[str] = []
    starts: list[int] = []
    offset = 0
    for page in pages:
        page = page.replace("\r\n", "\n").replace("\x00", "")
        starts.append(offset)
        parts.append(page)
        offset += len(page) + 2
    return PdfText("\n\n".join(parts), tuple(starts))


# ── Historical Q&A ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class QAThread:
    question_id: int
    title: str
    question: str
    accepted_post_id: int
    answer: str


async def read_historical_qa(db: AsyncSession, course_id: int) -> list[QAThread]:
    """
    The course's threads whose accepted answer was written by a person
    (§4.6, §7.4). Accepted AI answers are left out, so AI text never
    re-enters the index; retraction only applies to AI posts, so it needs
    no check here.
    """
    rows = await db.execute(
        select(Question.id, Question.title, Question.body, Post.id, Post.body)
        .join(Post, Post.question_id == Question.id)
        .where(
            Question.course_id == course_id,
            Post.kind == "ANSWER",
            Post.is_accepted.is_(True),
            Post.author_role != "AI",
        )
        .order_by(Question.id)
    )
    return [
        QAThread(qid, title, body.strip(), post_id, answer.strip())
        for qid, title, body, post_id, answer in rows
    ]

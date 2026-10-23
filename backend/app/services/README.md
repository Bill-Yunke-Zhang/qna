# `backend/app/services/`

Business logic that the routers call. Each function takes an `AsyncSession`
(plus plain arguments or Pydantic input models) and works on the ORM classes
in [`../models/`](../models/). Services raise the `QnaError` subclasses from
[`../common/exceptions.py`](../common/exceptions.py) and know nothing about
HTTP requests or responses.

| File | What it owns | Called from |
|---|---|---|
| `qa_service.py` | Categories, questions, posts, accepting answers, retracting AI answers, closing and reopening threads, and the response serializers | `routers/qa.py` |
| `ai_answer_service.py` | `answer_question`, the live background task: runs the pipeline with the `RAG_LIVE_*` settings and posts a matched, non-refusal answer if the thread is still open with no AI, accepted or staff answer; skipped during compare traffic and past `RAG_LIVE_MAX_WAITING`; never raises. `create_ai_post`, the only code that writes an AI post (validates its citations) | `routers/qa.create_question` (background task) |
| `auth_service.py` | Password hashing, JWT creation and decoding, user lookup and creation, roster-based access sync | `routers/auth.py`, `routers/admin.py`, `common/dependencies.py`, `bootstrap.py` |
| `roster_service.py` | Student roster import (Canvas CSV or pre-mapped JSON rows) | `routers/admin.py` |
| `staff_service.py` | Staff CSV import | `routers/admin.py` |
| `bootstrap.py` | The first admin account and the `grader` account at startup | `main.py` lifespan |

## Transaction rule

Services **`flush()` but never `commit()`**. The router (or `get_db` when the
request ends) commits. A service can therefore be composed with other writes in
the same request, and any exception rolls everything back. `bootstrap.py` is
the only exception: it runs outside a request, so it opens its own session from
`AsyncSessionLocal` and commits.

## `qa_service.py`

**Loading a thread.** `_get_question` loads a question together with its
author, `closed_by`, categories, posts, post authors and `accepted_by`, using
`selectinload`. Async SQLAlchemy can't lazy-load, so serializing a relationship
that wasn't loaded here raises an error. It also sets
`populate_existing=True`. Each write function loads the question, changes it,
flushes, then loads it **again** to build the response. Without
`populate_existing`, the second load would return the cached `posts` list and
miss the new or changed post.

**Rules enforced here:**

- `create_question` checks that every `category_ids` entry belongs to this
  course (404 listing the unknown ids).
- `create_post` refuses a `CLOSED` thread (409). It stores the `author_role`
  the router passes in.
- `serialize_question_detail(question, viewer_role)`: students never get
  retracted AI posts; staff do, to show them collapsed (`docs/design-rag.md`
  §4.7). Every router call passes the caller's effective role.
- `retract_ai_post` only accepts AI posts (422 otherwise), un-accepts the post,
  and changes nothing if it's already retracted.
- `set_post_accepted` only accepts `ANSWER` posts (409 for `FOLLOWUP`, and
  for a retracted AI post).
  Accepting one **un-accepts any other post** in the same question, so at most
  one answer is accepted. It records `accepted_by_user_id` and `accepted_at`.
  Un-accepting clears them. When an accepted answer loses acceptance it also
  clears the course's historical Q&A `content_hash`, and returns `True` so the
  router runs `ingestion.drop_qa_thread` after committing
  (`docs/design-rag.md` §4.6).
- `close_question` and `reopen_question` set or clear `closed_at` and
  `closed_by_user_id`, and return 409 if the thread is already in the target
  state.
- `create_category` rejects a duplicate name in the same course (409).
  `update_category` doesn't check.

**Serializers.** `serialize_question_summary`, `serialize_question_detail` and
`serialize_post` turn ORM objects into the dicts that fill `QuestionSummary`,
`QuestionDetail` and `PostResponse`. Fields such as `post_count` and
`has_accepted_answer` are computed here. **A new field on one of those schemas
must be added to the serializer as well**, or it never reaches the client.
`display_name(user)` falls back from `display_name` to `username` to `netid`
to `"Unknown"`.

`list_questions` searches with SQL `LIKE '%q%'` on title and body. It loads
every matching question with all its posts and has no pagination.

## `auth_service.py`

- **Passwords:** bcrypt with 12 rounds through passlib.
- **Tokens:** RS256 JWTs signed with `JWT_PRIVATE_KEY` / `JWT_PUBLIC_KEY`
  (base64 PEM from `.env`). If the keys are missing or don't decode, it
  **generates an in-memory key pair** and logs a warning. Every token then
  becomes invalid when the backend restarts.

  | Type | Lifetime | Claims |
  |---|---|---|
  | `access` | 2 hours | `sub`, `role`, `token_type` |
  | `refresh` | 7 days | `sub`, `token_type` |
  | `temp` | 15 minutes | `sub`, `token_type` |

- **`get_or_create_user_by_netid`** is used by SSO and the dev netid login. It
  updates `last_login` and calls `_sync_roster_course_access`.
- **`_sync_roster_course_access`** gives the user `STUDENT` access to every
  course whose **active** roster lists their netid, unless they already have a
  grant there. It only adds access and never removes or downgrades it.
- **`authenticate_local`** checks a username and password. It returns `None`
  for an unknown user, an account without a password (SSO-only), or a wrong
  password, so the router gives the same 401 for all three.

## `roster_service.py`

Two entry points share the same upsert logic:

- `process_roster_csv` reads a **Canvas gradebook export**. It needs the
  `Student` (`"Last, First"`) and `SIS Login ID` (`NETID@WISC.EDU`) columns,
  case-insensitive, and skips the `Points Possible` row. The display name is
  the given name only, title-cased.
- `process_roster_rows` takes rows the Admin app has already mapped to
  `netid`, `full_name` and `email`.

Both upsert on `(course_id, netid)` and then **deactivate every active roster
row whose netid wasn't in this upload**, so each upload acts as the complete
current roster. They stop after 1000 rows and return
`imported`/`updated`/`deactivated` counts plus per-row `errors` instead of
failing the whole upload.

## `staff_service.py`

`process_staff_csv` reads `netid, full_name, email` (case-insensitive). For
each row it reuses the `User` with that netid or creates one. It fills in
`email` and `display_name` only where they are empty, then grants `STAFF`,
upgrading an existing `STUDENT` grant. Unlike the roster this takes effect
immediately, without a login. Duplicate netids in the file are reported and
skipped, and processing stops after 200 rows.

## `bootstrap.py`

Runs once from the `main.py` lifespan hook:

- **First admin:** if `ADMIN_USERNAME` and `ADMIN_PASSWORD` are set and no
  admin other than `grader` exists, it creates one. After that the variables
  have no effect.
- **`grader`:** if `GRADER_PASSWORD_HASH` (base64 of a bcrypt hash) is valid,
  it creates or updates an `ADMIN` user named `grader` with that hash **on
  every startup**. A malformed value is logged and ignored.
- On a fresh database it retries every 5 seconds until
  `alembic upgrade head` has created the tables, so the backend container
  waits instead of crashing.

AI posts don't need a system account: they have `author_role = 'AI'` and a
NULL `author_user_id` (see [`../models/README.md`](../models/README.md) and
`docs/design-rag.md` §4.1).

## Adding a service

RAG work (ingestion, retrieval, answer generation) lives in `rag/` (layout in
`docs/design-rag.md` §5.2). So far it has:

- `rag/profiles.py`: the fixed list of ingestion profiles (chunking +
  embedding model). Never change a profile under its own name; add a new one.
  `tests/unit/test_profiles.py` pins each profile's hash and fails the
  pipeline otherwise.
- `rag/clients.py`: the only code that talks to Ollama, Infinity and ChromaDB.
- `rag/fetchers.py`: fetches web pages (only public `http(s)` addresses,
  checked again on every redirect) and strips them to text with heading
  positions (`parse_html`); checks uploads and reads zips in memory, with
  sizes counted while decompressing (`read_upload`); and reads the threads
  eligible for historical Q&A (`read_historical_qa`).
- `rag/chunking.py`: splits a document into sections by structure (web pages
  by heading), runs the profile's fallback chunker on oversized sections, and
  builds Text Fragment citations. Chunking is three steps (`plan_chunks`,
  embed `units_to_embed` if any, `finish_chunks`) so semantic chunking never
  calls Infinity from a worker thread. Markdown and PDF only need to produce
  `Section`s to reuse the same chunkers.
- `rag/ingestion.py`: the background ingestion task and the in-process sync
  registry (`claim` / `release` / `is_syncing`). A request claims the source
  (`SyncInProgress` → 409) and schedules `ingest(...)` with a loader that
  returns `Document`s (text, sections, and how to locate a chunk). Each
  profile is chunked, embedded and inserted under a new `sync_id`, then
  switched to in `index_syncs`; old chunks are deleted after
  `CLEANUP_GRACE_S`. Unchanged content isn't re-embedded, and a failed
  profile keeps its previous version and records `last_error`.
  Loaders: `web_page_loader(resource)` for URL syllabus/schedule resources;
  `documents_loader(...)` for uploads, parsed in the request with
  `parse_upload` (so a bad file is a 422); `historical_qa_loader(course_id)`
  for the `historical_qa` source, one atomic chunk per thread.
  `drop_qa_thread` is the §4.6 un-accept cleanup.
- `rag/pipeline.py`: `run()`, the shared pipeline (§5.3), and its contract:
  `RagConfig`, `RagResult`, `RetrievedChunk` and the errors it raises
  (`UnknownProfile`, `ModelNotAvailable`, `ProfileNotIngested`,
  `ProfileStale`). The checks run first and in that order, so a bad request
  is an error, never a silent no-match. Then it embeds the question with the
  collection's own model and the profile's query prefix, queries the top
  `RAG_TOP_K` chunks of the current syncs, drops past answers that are no
  longer accepted (§4.6), keeps those at or above the threshold (cosine
  similarity = 1 − distance) and generates through `generation_gate`. The
  gate runs one generation at a time and serves waiting COMPARE callers
  before LIVE ones; waiting counts against the deadline. Every hit is
  logged (`rag_hit`) with its score. It never writes to the database.
- `rag/prompt.py`: the tagged user message (§5.5). One tag per resource
  type, best match first, no URLs or ids; only our own tag names are
  escaped. Chunks are cut to `PROMPT_CHUNK_MAX_CHARS`, and the lowest-ranked
  are dropped until the estimate (chunking tokenizer × 1.3) fits
  `OLLAMA_NUM_CTX − OLLAMA_NUM_PREDICT`.
- `rag/compare.py`: what the compare endpoint adds around `run()`: its time
  budget (`deadline`, `RAG_COMPARE_BUDGET_S`), VM-wide CPU use for the
  request (`CpuWindow`), and a record of compare traffic (`tracking`,
  `active_or_ended_within`) that live answering checks against
  `RAG_COMPARE_QUIET_S` to pause during a harness run.

Follow the
same rules: take an `AsyncSession`, flush without committing, raise
`QnaError` subclasses, and keep HTTP details in the router. Calls to Ollama,
Infinity or ChromaDB should go through the service layer too, so the router
and the compare endpoint can share them.

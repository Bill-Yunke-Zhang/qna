# `backend/app/routers/`

FastAPI `APIRouter`s, one per area of the API. `main.py` mounts all four under
the `/api` prefix. A router parses the request, applies an auth dependency
from [`../common/dependencies.py`](../common/dependencies.py), calls a service,
and returns a schema from [`../schemas/`](../schemas/). The Q&A rules
themselves live in [`../services/`](../services/).

| File | Prefix | Guard | Frontend |
|---|---|---|---|
| `health.py` | `/api/health` | none | Docker health checks |
| `auth.py` | `/api/auth` | none (it issues the tokens) | all three apps |
| `admin.py` | `/api/admin` | `require_admin` on every route | Admin app |
| `qa.py` | `/api/courses` | `get_current_user`, `require_course_member` or `require_course_staff` | Student and Staff apps |
| `rag.py` | `/api/courses/{course_id}/rag` | `require_course_staff` | `eval/compare_harness.py` |

## Transactions

`get_db` (in [`../database.py`](../database.py)) opens one session per
request, **commits when the handler returns normally, and rolls back if it
raises**. So a handler that only changes ORM objects (for example
`PUT /admin/courses/{id}` or `PATCH .../categories/{id}`) is still saved.

Handlers that return a response built from the database call
`await db.commit()` themselves before serializing. Follow that pattern in new
write endpoints so a database error surfaces as an error response instead of
after the handler has already returned.

Raise the `QnaError` subclasses from [`../common/exceptions.py`](../common/exceptions.py)
(`NotFoundError`, `ConflictError`, ...) for expected failures, not
`HTTPException`.

## `health.py`

`GET /api/health` returns `{"status": "ok"}`. It doesn't touch the database or
Redis.

## `auth.py`

| Endpoint | What it does |
|---|---|
| `POST /login` | `{username, password}` checks a local account and returns an access token in the body plus the refresh token as an HTTP-only cookie. `{netid}` is the **development-only** shortcut: it creates or finds the user and returns a temp token (401 outside development). Rate limited to 5 per 15 minutes. |
| `GET /oauth2-callback` | Campus SSO. The OAuth2 proxy in front of the backend sets `X-Auth-Request-User` and `X-Auth-Request-Email`. The endpoint returns a small HTML page that redirects to the app's `/login` with a temp token in the URL fragment. |
| `POST /exchange-temp` | Trades a temp token (from SSO or dev login) for an access token and refresh cookie. Rate limited to 10 per minute. |
| `POST /refresh` | Reads the `refresh_token` cookie and returns a new access token. It also rotates the refresh cookie. |
| `POST /logout` | Clears the refresh cookie. Access tokens are stateless and simply expire (2 hours). |

Points worth knowing:

- **The SSO headers are trusted only with the proxy secret.** The callback
  requires `X-Proxy-Shared-Secret` to match `OAUTH2_PROXY_SHARED_SECRET`
  (constant-time compare). If the setting is empty, the endpoint always fails.
  Without this check anyone who could reach the backend could forge
  `X-Auth-Request-User`.
- **`redirect_to` is allow-listed** to `/student/login`, `/staff/login` and
  `/admin/login`, so the callback can't be used as an open redirect.
- **The refresh cookie is scoped to `path=/api/auth`**, and is `secure`
  everywhere except development. Other routes never see it.
- A netid login (SSO or dev) runs `_sync_roster_course_access`, which is how a
  rostered student gets `STUDENT` access on first login.

## `admin.py`

Every route depends on `require_admin` (global `ADMIN`, which includes the
`grader` account). Most handlers query the models directly instead of going
through a service, because they are plain CRUD.

| Area | Endpoints | Notes |
|---|---|---|
| Courses | `GET/POST /courses`, `GET/PUT /courses/{id}` | No delete endpoint. |
| Student roster | `GET/POST /courses/{id}/roster`, `POST /courses/{id}/roster/import`, `PATCH /courses/{id}/roster/{roster_id}` | `POST .../roster` takes a Canvas gradebook CSV. `.../import` takes JSON rows already mapped by the Admin app's column wizard. Both go through `roster_service`, and both **deactivate rows missing from the upload**. |
| Staff | `GET/POST /courses/{id}/staff` | The CSV (`netid, full_name, email`) goes through `staff_service`, which creates accounts and grants `STAFF` right away. |
| Users | `GET/POST /users`, `GET/PUT/DELETE /users/{id}` | Local (username/password) accounts. New users are always created as `USER`. `PUT` can promote to `ADMIN`. Admins can't be deleted. |
| Course access | `POST /users/{id}/course-access`, `DELETE /users/{id}/course-access/{course_id}` | Grant (or change the role of) and revoke a `UserCourseAccess` row. |

CSV uploads are read with `read_upload_capped` (2 MB cap, 413 above it).

## `qa.py`

All routes are under `/api/courses`. Course-scoped routes take `course_id`
from the path and pass it to a course dependency. A non-member gets **404**,
not 403, so the response doesn't confirm that the course exists.

| Endpoint | Guard | Returns |
|---|---|---|
| `GET /courses/mine` | `get_current_user` | Courses the user can access, with their role. A global admin sees every course as `STAFF`. |
| `GET /{course_id}/categories` | member | `list[CategoryResponse]` |
| `POST /{course_id}/categories` | staff | `CategoryResponse` (409 on a duplicate name) |
| `PATCH`, `DELETE /{course_id}/categories/{category_id}` | staff | updated category / 204 |
| `GET /{course_id}/questions` | member | `list[QuestionSummary]`, newest first. Optional `category_id`, `status` (`OPEN`/`CLOSED`) and `q` (a `LIKE` search over title and body, at most 200 chars). |
| `POST /{course_id}/questions` | member | `QuestionDetail` |
| `GET /{course_id}/questions/{question_id}` | member | `QuestionDetail` |
| `POST /{course_id}/questions/{question_id}/posts` | member | `QuestionDetail`. 409 if the thread is closed. |
| `PATCH .../posts/{post_id}/accept` | staff | `QuestionDetail`. Body `{is_accepted}`. 409 for a `FOLLOWUP`. |
| `POST .../close`, `POST .../reopen` | staff | `QuestionDetail`. 409 if it is already in that state. |

**Every write that changes a thread returns the whole `QuestionDetail`**, so
the frontend re-renders from one response instead of re-fetching.

`create_post` passes `member.course_role` to the service as the post's
`author_role`. The client never sends it. Because of the `X-App-Surface`
clamp, staff posting from the Student app are recorded as `STUDENT`.

Renaming a category with `PATCH` doesn't check for duplicates the way `POST`
does, and the handler doesn't commit itself. A clash only fails at the
`(course_id, name)` unique constraint when `get_db` commits at the end of the
request, so the client doesn't get a clean 409.

## `rag.py`

`POST /{course_id}/rag/compare` runs one question through the RAG pipeline
with the configuration in the body and returns the fixed T6 contract
(`schemas/rag.py`). The course's harness calls it as the `grader` admin. It
creates no rows.

The harness aborts the whole run on any error status, so every failure is
explicit, never a quiet `matched: false`:

| Cause | Status |
|---|---|
| Unknown `ingestion_profile`, or `generation_model` not pulled | 422 |
| No such course, or nothing ingested under that profile | 404 |
| The collection was built with a different profile definition | 409 |
| Ollama, Infinity or ChromaDB unreachable | 503 |

A generation that runs out of the time budget (`RAG_COMPARE_BUDGET_S`) is
returned as a `200` with the partial answer, and logged.

## Adding a router

1. Create `APIRouter(prefix=..., tags=[...])` in a new file here.
2. Include it in `main.py` with `prefix="/api"`.
3. Guard it with a dependency from `common/dependencies.py`. Course-scoped
   staff features such as `POST /api/courses/{course_id}/rag/compare` and
   course-resource management should use `require_course_staff` and live
   under `/courses/{course_id}/...`, either in `qa.py` or in a new router with
   the same path shape.
4. Keep logic in a service so it can be tested without HTTP.

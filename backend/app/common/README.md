# `backend/app/common/`

Cross-cutting pieces that the routers and `main.py` share: authentication and
course-access dependencies, the error model, logging setup, rate limiting, and
a capped upload reader. Nothing here touches Q&A business rules. Those live in
[`../services/`](../services/).

| File | What it provides | Used by |
|---|---|---|
| `dependencies.py` | FastAPI dependencies for "who is calling" and "may they act in this course" | `routers/auth.py`, `routers/admin.py`, `routers/qa.py` |
| `exceptions.py` | `QnaError` hierarchy and the global exception handlers | `main.py`, routers, `services/qa_service.py` |
| `logging.py` | `configure_logging()` for structlog | `main.py` (called once at import) |
| `rate_limit.py` | The shared slowapi `limiter` | `main.py`, `routers/auth.py` |
| `uploads.py` | `read_upload_capped()` for CSV uploads | `routers/admin.py` (roster and staff CSVs) |

## `dependencies.py`: authentication and authorization

**Finding the token.** `_token_from_request` takes the JWT from the
`Authorization: Bearer` header first, then falls back to the `access_token` cookie.

**`get_current_user`** decodes the token through `services/auth_service.decode_token`.
It accepts `access` and `temp` tokens and rejects `refresh` tokens. It then
loads the `User`. A missing, invalid or expired token, or an unknown user,
raises `UnauthorizedError` (401).

**`require_admin`** requires the global role `ADMIN`. Otherwise it raises 403.
It guards every `/api/admin/*` route.

**`get_refresh_token`** reads the `refresh_token` cookie for `/api/auth/refresh`
and raises 401 if the cookie is missing. `/api/auth/exchange-temp` reuses
`_token_from_request` to read the temp token.

**Course-scoped access** is where per-course permissions are enforced:

- `require_course_member(course_id, ...)` returns a `CourseMember(user, course_role)`.
  - A global `ADMIN` is treated as `STAFF` in every course.
  - Anyone else needs a `UserCourseAccess` row for that `course_id`. Without one
    the call fails with **404 "Course {course_id} not found"**, not 403, so the response
    doesn't reveal that the course exists.
  - **The `X-App-Surface` header clamps the role.** When the header is
    `student` (the Student app always sends it), the effective role becomes
    `STUDENT` even for staff and admins. So staff using the Student app post
    and are permission-checked as students. The header can only lower a role,
    never raise it.
- `require_course_staff` stacks on top and requires the effective role to be `STAFF` (403 otherwise).

In `routers/qa.py`, reading categories and questions, asking questions and
posting replies use `require_course_member`. Managing categories, accepting
answers and closing or reopening questions use `require_course_staff`.

New staff-only course endpoints (for example `/rag/compare` or course-resource
management) should reuse `require_course_staff`. A global admin such as the
`grader` account passes as `STAFF`. A request that carries
`X-App-Surface: student` is clamped to `STUDENT` and rejected, so a caller that
sends no header (like the eval harness) is unaffected.

## `exceptions.py`: error model

`QnaError(code, message, status_code)` is the base class. Its subclasses:

| Class | HTTP | `error` code |
|---|---|---|
| `NotFoundError` | 404 | `NOT_FOUND` |
| `ForbiddenError` | 403 | `FORBIDDEN` |
| `UnauthorizedError` | 401 | `UNAUTHORIZED` |
| `ConflictError` | 409 | `CONFLICT` |
| `PayloadTooLargeError` | 413 | `PAYLOAD_TOO_LARGE` |

`register_exception_handlers(app)` installs three handlers, so every error
response has an `error` field the frontends can switch on:

- `QnaError` → `{"error": code, "message": message}` with the class's status, logged as a warning.
- `RequestValidationError` → 422 `{"error": "VALIDATION_ERROR", "detail": [...]}`.
  The errors pass through `jsonable_encoder` first. Without that, a validator
  that raises a plain `ValueError` (such as `LoginRequest`'s) would crash JSON
  serialization and turn the 422 into a 500.
- Any other `Exception` → 500 `{"error": "INTERNAL_ERROR", ...}`, logged with
  the traceback. Internal details are never sent to the client.

To signal an expected failure from a router or service, raise one of these
classes (or add a subclass) instead of `HTTPException`.

## `logging.py`

`configure_logging()` sets up structlog on top of the stdlib `logging` module,
writing to stdout. Every line gets the logger name, the level and an ISO
timestamp. Development uses `DEBUG` with a colored console renderer. Every
other environment uses `INFO` with one JSON object per line and quiets
`uvicorn.access` to `WARNING`. Modules log with `structlog.get_logger()` and
keyword fields, for example `logger.info("login_success", user_id=...)`.

## `rate_limit.py`

A single slowapi `Limiter` that `main.py` attaches to `app.state`. Routes opt
in with a decorator. Today only auth does: `/login` allows 5 per 15 minutes
and `/exchange-temp` allows 10 per minute.

The key is the client's remote address. **In development the key is a fresh
UUID per request, so limits never fire locally**, because all Docker traffic
shares one internal IP. Don't expect to reproduce a 429 on the dev stack.

## `uploads.py`

`read_upload_capped(file, max_bytes=2 MB)` reads an `UploadFile` in 64 KB
chunks and raises `PayloadTooLargeError` (413) as soon as the total passes the
cap. It exists because Starlette sets no body limit and `Content-Length` can't
be trusted. Use it instead of `await file.read()` for any new upload endpoint,
for example document ingestion. The 2 MB default was sized for CSVs and is
likely too small for a repository zip or a PDF. Pass a larger `max_bytes` for
those, and record the chosen limit in the design doc.

# `backend/app/schemas/`

Pydantic v2 models that define the JSON shapes going in and out of the HTTP API.
Routers use them as request bodies and `response_model`s. A few services also
build result objects from them. They contain no database access and no business
logic beyond field validation.

The SQLAlchemy tables live in [`../models/`](../models/). These schemas are the
public, wire-level view of that data, and they do not map one to one: some
response fields are computed in `services/qa_service.py` rather than read from
a column.

## Conventions

- **`*Create` / `*Update` / `*Patch` / `*Request` (input):** set
  `extra="forbid"`, so an unknown field returns a 422 instead of being silently
  dropped. `*Update` models make every field optional for partial updates.
- **`*Response` (output, built from an ORM object):** set `from_attributes=True`
  so a router can return a model instance directly.
- **Response models without `from_attributes`** (`QuestionSummary`,
  `QuestionDetail`, `PostResponse`, `AuthorSummary`, `MyCourseResponse`):
  validated from plain dicts that `qa_service.serialize_*` or the router builds
  by hand. Add any new field to the serializer too.
- **Enum-like strings in request bodies:** checked with a regex `pattern`, not
  a Python `Enum`. Roles are `USER|ADMIN` globally and `STUDENT|STAFF` per
  course. Post kinds are `ANSWER|FOLLOWUP`. Response models type these fields
  as plain `str` (`PostResponse.author_role`, `QuestionDetail.status`, ...).
  The real constraint is a MySQL `ENUM` column in `models/` (for example
  `Enum("STUDENT", "STAFF", name="post_author_role")` in `models/qa.py`), so
  adding a new value needs an **Alembic migration**, not just a schema edit.
- **Server-set fields:** `PostCreate` has no `author_role`. The router passes
  the caller's effective course role (`member.course_role`) into
  `qa_service.create_post`, which stores it on the post.
- Validation errors are turned into the `{"error": "VALIDATION_ERROR", "detail": [...]}`
  422 body by `common/exceptions.py`.

## Files

### `auth.py`: login and tokens (used by `routers/auth.py`)

| Model | Purpose |
|---|---|
| `LoginRequest` | Either `username` + `password`, or `netid` (dev-only fallback, rejected outside development). A `model_validator` requires one of the two. |
| `TokenResponse` | `{access_token, token_type: "bearer"}` returned by `/api/auth/login` and `/api/auth/exchange-temp`. The refresh token goes in an HTTP-only cookie, not in the body. |
| `TempTokenResponse` | Short-lived (15 min) temp token from dev netid login. The SSO callback issues the same kind of token. The client trades it for real tokens at `/api/auth/exchange-temp`. |
| `RefreshResponse` | New access token from `/api/auth/refresh`. |

### `admin.py`: admin app (used by `routers/admin.py`, `services/roster_service.py`, `services/staff_service.py`)

| Section | Models | Notes |
|---|---|---|
| Courses | `CourseCreate`, `CourseUpdate`, `CourseResponse` | name ≤ 255, semester ≤ 50 |
| Student roster | `RosterEntryResponse`, `RosterEntryPatch`, `RosterRowIn`, `RosterImportPayload`, `RosterUploadResult` | A roster row grants nothing by itself. `STUDENT` access is added when the student logs in (`auth_service._sync_roster_course_access`). Deactivating a row later does not revoke access that was already granted. Rows arrive either as a CSV upload or as JSON `rows` (`RosterImportPayload`, at least 1 row). The result reports `imported`/`updated`/`deactivated` counts plus per-row `errors`. |
| Staff import | `StaffUploadResult` | Unlike the roster, a staff CSV creates accounts right away and grants `STAFF` access to the course. |
| Users | `UserCreate`, `UserUpdate`, `UserResponse`, `UserWithAccessResponse` | Local accounts. Usernames must match `^[a-zA-Z0-9_-]+$` and are lowercased by a validator. Passwords are 8–72 chars (72 is bcrypt's input limit). `UserWithAccessResponse.course_access` is a loosely typed `list[dict]`. |
| Course access | `CourseAccessGrant` | `{course_id, role: STUDENT|STAFF}` for `POST /api/admin/users/{id}/course-access`. |

### `qa.py`: the Q&A board (used by `routers/qa.py`, `services/qa_service.py`)

| Section | Models | Notes |
|---|---|---|
| Categories | `CategoryCreate`, `CategoryUpdate`, `CategoryResponse` | Per-course tags managed by staff. |
| Questions | `QuestionCreate`, `QuestionSummary`, `QuestionDetail` | A new question needs a title, a body ≤ 10 000 chars and **at least one** `category_ids` entry. `QuestionSummary` is the list-view row: it adds the derived `post_count` and `has_accepted_answer`. `QuestionDetail` is the full thread: it includes every post plus `closed_by`/`closed_at`. |
| Posts | `PostCreate`, `PostResponse`, `PostAcceptPatch` | A post is either an `ANSWER` or a `FOLLOWUP` inside a question's thread. `author_role` records whether the author posted as `STUDENT` or `STAFF` (the effective course role at the time). `PostAcceptPatch {is_accepted}` toggles the accepted mark. |
| Authors | `AuthorSummary` | `{id, display_name}`, embedded wherever a user is shown. |
| Course picker | `MyCourseResponse` | `{id, name, semester, role}` for `GET /api/courses/mine`. A global admin sees every course as `STAFF`. |

Every write endpoint in `routers/qa.py` (new question, new post, accept,
close, reopen) returns the whole updated `QuestionDetail`, so the frontend can
re-render the thread from a single response.

## Adding to this directory

A future AI-answer feature would most likely add fields to `PostResponse` /
`QuestionDetail` (for example citations) or add a new model next to them. If
you do, update the matching serializer in `services/qa_service.py`, because
these response models are filled from dicts, not ORM objects.

Two constraints matter for an AI-generated post:

- **A new `author_role` value** (for example an AI role) needs an Alembic
  migration of the `post_author_role` ENUM. The frontends' `author_role` type
  must change too. See [`../../../frontend/student/README.md`](../../../frontend/student/README.md).
- **Every post needs an author user.** `Post.author_user_id` is non-nullable
  and a foreign key to `users.id`, and `AuthorSummary` requires `id` and
  `display_name`. An AI post therefore needs either a dedicated system account
  (`services/bootstrap.py` shows how the app already creates its `grader`
  account at startup) or a schema change that makes the author nullable. That
  is a design decision for `docs/design-rag.md`.

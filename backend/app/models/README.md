# `backend/app/models/`

SQLAlchemy 2.0 ORM classes (typed `Mapped[...]` style) for every MySQL table.
All of them subclass `Base` from [`../database.py`](../database.py). Nothing here
runs queries. Reads and writes happen in [`../services/`](../services/) and,
for the simple admin endpoints, directly in [`../routers/admin.py`](../routers/admin.py).
The JSON shapes the API returns are in [`../schemas/`](../schemas/).

| File | Tables | Classes |
|---|---|---|
| `user.py` | `users` | `User` |
| `course.py` | `courses`, `course_rosters`, `user_course_access` | `Course`, `CourseRoster`, `UserCourseAccess` |
| `qa.py` | `categories`, `questions`, `question_categories`, `posts` | `Category`, `Question`, `QuestionCategory`, `Post` |

## Relationships

```
User ──< UserCourseAccess >── Course ──< CourseRoster
 │                              │
 │                              ├──< Category ──< QuestionCategory >── Question
 │                              │                                         │
 ├──< Question (author) ────────┴──< Question ──< Post                    │
 └──< Post (author)                                                       │
```

- A **course** owns its roster rows, access grants, categories and questions.
  All of them use `cascade="all, delete-orphan"` and `ON DELETE CASCADE`, so
  deleting a course deletes everything in it.
- A **question** owns its posts and category links the same way. `posts` is
  always ordered by `created_at`, so a thread reads top to bottom.
- **Users are not cascaded.** `Question.author_user_id`, `Post.author_user_id`,
  `closed_by_user_id` and `accepted_by_user_id` reference `users.id` with no
  `ON DELETE` rule, and the two author columns are non-nullable. Deleting a user
  who has written a question or a post therefore fails at commit.
  (`DELETE /api/admin/users/{id}` only blocks admins up front.)

## `user.py`

`User` has a UUID string primary key (`String(36)`), generated in Python. One
table holds every kind of account:

| Kind | How it is created | Fields set |
|---|---|---|
| SSO / dev netid login | `auth_service.get_or_create_user_by_netid` | `netid`, `email` |
| Staff CSV import | `staff_service.process_staff_csv` | `netid`, `email`, `display_name` |
| Local account | `POST /api/admin/users` | `username`, `password_hash`, `display_name`, `email` |
| Bootstrapped admin / `grader` | `services/bootstrap.py` | `username`, `password_hash`, `role="ADMIN"` |

So almost every column is nullable. Code that shows a name uses
`qa_service.display_name()`, which falls back from `display_name` to `username`
to `netid` to `"Unknown"`.

`role` is the **global** role: `ADMIN` or `USER`. It is not the course role.
Students and staff are both `USER` globally.

## `course.py`

- **`Course`**: `name` and `semester`. Nothing else is course-level config
  today.
- **`CourseRoster`**: one row per student listed in an uploaded Canvas roster,
  unique on `(course_id, netid)`. A roster row **does not grant access by
  itself**. When that netid logs in, `auth_service._sync_roster_course_access`
  adds a `STUDENT` grant. `is_active=False` marks a student missing from the
  latest upload. It stops future grants but does not revoke one that exists.
- **`UserCourseAccess`**: the per-course permission row, with the composite
  primary key `(user_id, course_id)` and `role` = `STUDENT` or `STAFF`. This
  is what `common/dependencies.require_course_member` checks. A global `ADMIN`
  needs no row: it is treated as `STAFF` everywhere.

## `qa.py`

- **`Category`**: a staff-managed tag, unique on `(course_id, name)`.
- **`Question`**: the root of a thread. `status` is `OPEN` or `CLOSED`, and
  only staff change it. `closed_at` and `closed_by_user_id` are set on close
  and cleared on reopen. Indexed on `(course_id, status)` for the list view.
- **`QuestionCategory`**: the many-to-many link between questions and
  categories.
- **`Post`**: one reply in a thread. `kind` is either:
  - `ANSWER`: an attempt to resolve the question. Staff can mark it accepted
    no matter who wrote it, and at most one post per question is accepted
    (`qa_service.set_post_accepted` enforces that).
  - `FOLLOWUP`: ordinary discussion. It can never be accepted.

  `author_role` is a **snapshot** of the author's effective course role
  (`STUDENT` or `STAFF`) at the moment of posting, so a "staff answer" badge
  doesn't change later if their access changes. Staff posting from the Student
  app are stored as `STUDENT` (see `X-App-Surface` in
  [`../common/README.md`](../common/README.md)).

## Enum columns

Fixed sets of values are MySQL `ENUM` columns, not lookup tables:

| Column | Values | ENUM name |
|---|---|---|
| `users.role` | `ADMIN`, `USER` | `user_role` |
| `user_course_access.role` | `STUDENT`, `STAFF` | `course_role` |
| `questions.status` | `OPEN`, `CLOSED` | `question_status` |
| `posts.author_role` | `STUDENT`, `STAFF` | `post_author_role` |
| `posts.kind` | `ANSWER`, `FOLLOWUP` | `post_kind` |

Adding a value (for example `AI` to `post_author_role`) means editing the
`Enum(...)` here **and** writing an Alembic migration that alters the column.
The schemas, serializers and frontend types that treat these as strings need
updating too.

## Adding a model

1. Create the class here and subclass `Base`.
2. Export it from `__init__.py`, **and** add it to the import list at the top
   of [`../migrations/env.py`](../migrations/env.py). Autogenerate only sees
   tables whose classes have been imported, so a model missing from that list
   produces an empty migration.
3. Generate and review the migration:
   `alembic revision --autogenerate -m "..."`, then `alembic upgrade head`.
   Autogenerate doesn't reliably detect a changed `ENUM` value list, so write
   those changes by hand.
4. Add the matching Pydantic schemas in [`../schemas/`](../schemas/).

Today there is a single migration, `001_initial_schema.py`. The planned
course-resource tables for RAG ingestion (`docs/design-rag.md`) belong here,
and each should hang off `courses.id` with `ON DELETE CASCADE` like the
existing course-owned tables.

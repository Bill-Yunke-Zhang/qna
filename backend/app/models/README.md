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
| `resource.py` | `resources`, `index_syncs` | `Resource`, `IndexSync` |

## Relationships

```
User ──< UserCourseAccess >── Course ──< CourseRoster
 │                              │
 │                              ├──< Category ──< QuestionCategory >── Question
 │                              │                                         │
 ├──< Question (author) ────────┼──< Question ──< Post                    │
 └──< Post (author)             │                                         │
                                ├──< Resource ──< IndexSync               │
                                └──< IndexSync (historical_qa)            │
```

- A **course** owns its roster rows, access grants, categories, questions,
  resources and index syncs. All of them use `cascade="all, delete-orphan"` and
  `ON DELETE CASCADE`, so deleting a course deletes everything in it.
- A **question** owns its posts and category links the same way. `posts` is
  always ordered by `created_at`, so a thread reads top to bottom.
- **Users are not cascaded.** `Question.author_user_id`, `Post.author_user_id`,
  `closed_by_user_id` and `accepted_by_user_id` reference `users.id` with no
  `ON DELETE` rule. `Question.author_user_id` is non-nullable, and
  `Post.author_user_id` may only be NULL on AI posts (`ck_posts_ai_author`).
  Deleting a user who has written a question or a post therefore fails at
  commit. (`DELETE /api/admin/users/{id}` only blocks admins up front.)
  `retracted_by_user_id` and `Resource.created_by_user_id` are the exceptions:
  `ON DELETE SET NULL`, so deleting that staff user keeps the record.

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

  **AI posts** (`author_role = 'AI'`, `docs/design-rag.md` §4) are always
  `ANSWER`s, so the existing accept flow works on them unchanged. Three CHECK
  constraints, written by hand in `002_rag.py`, tie the RAG columns to them:
  - `ck_posts_ai_author`: `author_user_id` is NULL exactly when the post is AI.
    Code that reads `post.author` must handle `None`.
  - `ck_posts_citations_ai_only`: only AI posts have `citations`, the 1–3
    sources saved when the post was created. The column is
    `JSON(none_as_null=True)`, so Python `None` is stored as SQL `NULL`.
  - `ck_posts_retract_ai_only`: only AI posts can have `retracted_at`.

## `resource.py`

- **`Resource`**: course material staff register for ingestion: `type`
  `SYLLABUS`, `SCHEDULE` or `REPO`, from `origin` `URL` (`fetch_url` set) or
  `UPLOAD` (`link_base_url` set; no file is stored). `repo_branch` is only for
  repos. CHECK constraints enforce those three rules. Its `source_key` is
  `resource:{id}`.
- **`IndexSync`**: the result of the last ingestion of one source under one
  ingestion profile, unique on `(course_id, profile, source_key)`.
  `source_key` is a resource's, or `historical_qa` (`HISTORICAL_QA_SOURCE_KEY`)
  for the course's Q&A threads, which aren't a `Resource` row (`resource_id`
  NULL). Chunks live only in ChromaDB. Search sees only chunks whose `sync_id`
  is a row's `current_sync_id`, which is what makes a re-sync switch atomic.
  A NULL `content_hash` forces the next sync to re-embed.

## Enum columns

Fixed sets of values are MySQL `ENUM` columns, not lookup tables:

| Column | Values | ENUM name |
|---|---|---|
| `users.role` | `ADMIN`, `USER` | `user_role` |
| `user_course_access.role` | `STUDENT`, `STAFF` | `course_role` |
| `questions.status` | `OPEN`, `CLOSED` | `question_status` |
| `posts.author_role` | `STUDENT`, `STAFF`, `AI` | `post_author_role` |
| `posts.kind` | `ANSWER`, `FOLLOWUP` | `post_kind` |
| `resources.type` | `SYLLABUS`, `SCHEDULE`, `REPO` | `resource_type` |
| `resources.origin` | `URL`, `UPLOAD` | `resource_origin` |

Adding a value (as `002_rag.py` did with `AI`) means editing the
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

Migrations: `001_initial_schema.py`, then `002_rag.py` (AI posts, citations,
retraction, `resources`, `index_syncs`). CHECK constraints are never
autogenerated; write them by hand in the migration and mirror them in the
model's `__table_args__`. `002_rag`'s downgrade refuses while any AI post
exists, because `author_user_id` can't return to NOT NULL.

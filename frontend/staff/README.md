# `frontend/staff/`: Staff app

React 18 + TypeScript + Vite + Tailwind single-page app for course staff
(instructors and TAs). Staff answer questions, mark answers as verified,
close and reopen threads, and manage the course's categories.

The app is a **copy of [`../student/`](../student/) with staff features added**.
`lib/CourseContext.tsx`, `lib/types.ts`, `lib/utils.ts`, `components/ui/*`,
`QuestionsPage.tsx` and the login flow are the same as the student app,
apart from a few strings. Read the student README for those. This file only
covers what differs. There is no shared package, so a fix to a common file
has to be made in each app.

## Running

| | |
|---|---|
| Dev server | `npm run dev:staff` from the repo root → http://localhost:5174 |
| API in dev | Vite proxies `/api` to `http://localhost:8000` |
| Production | Built to `dist/` and served by nginx at **`/staff/`** |

## Differences from the student app

| Where | Staff app |
|---|---|
| `lib/api.ts` | Sends **`X-App-Surface: staff`**. This grants nothing by itself. The backend still uses the caller's real course role, and the header can only ever clamp a role down to `STUDENT`. A student who opens this app is still a student and gets 403 on staff-only actions. Also has `postForm`/`putForm` for multipart uploads (a `FormData` body sets its own `Content-Type`), and shows schema validation errors (422 `detail`) as their messages. |
| `App.tsx` | Header shows "Course Q&A — Staff" with nav links **Questions**, **Categories** and **Resources**, and adds the `/categories` and `/resources` routes. The header wraps on narrow screens. |
| `pages/QuestionDetailPage.tsx` | Adds staff controls (below). The reply form defaults to **Answer**, not Follow-up. |
| `pages/CategoriesPage.tsx` | New page (below). |
| `pages/ResourcesPage.tsx`, `lib/resources.ts` | New page (below) and its types, kept out of `types.ts` (which mirrors the student app). |
| `pages/AskQuestionPage.tsx` | Same form. The "no categories yet" hint points staff at the Categories page. |

## Routes

| Path | Page | Backend calls |
|---|---|---|
| `/login` | Same as the student app (title "Staff Login") | `POST /api/auth/login`, `/exchange-temp` |
| `/questions` | Same list and filters as the student app | `GET /courses/{id}/categories`, `GET /courses/{id}/questions` |
| `/questions/new` | Ask a question as staff | `POST /courses/{id}/questions` |
| `/questions/:questionId` | Thread with staff controls | `GET .../questions/{qid}`, `POST .../posts`, `PATCH .../posts/{pid}/accept`, `POST .../close`, `POST .../reopen` |
| `/categories` | List, create and delete the course's categories | `GET`/`POST /courses/{id}/categories`, `DELETE /courses/{id}/categories/{cid}` |
| `/resources` | Course material for RAG: add, re-sync, replace, delete, re-index Q&A | `GET`/`POST /courses/{id}/resources`, `POST …/resources/upload`, `POST …/resources/{rid}/sync`, `PUT …/resources/{rid}/upload`, `DELETE …/resources/{rid}`, `POST …/historical-qa/sync` |

### Staff controls on a thread (`QuestionDetailPage.tsx`)

- **Mark verified / Verified:** shown on every `ANSWER` post (not on
  follow-ups). It toggles `is_accepted` through
  `PATCH /courses/{id}/questions/{qid}/posts/{pid}/accept {is_accepted}`.
  Students see an accepted answer as "Verified by staff". The backend allows
  **at most one accepted answer per question**: accepting one clears any
  other, and accepting a follow-up returns 409. Accepting still works on a
  closed thread.
- **Close thread / Reopen:** `POST .../close` or `.../reopen`. A closed thread
  hides the reply form until it is reopened. Threads stay open until staff
  close them; nothing closes them automatically.
- Each action returns the updated `QuestionDetail`, which replaces the page
  state directly. A shared `busy` flag disables the buttons while a request is
  in flight.

### Categories (`CategoriesPage.tsx`)

Create a category (name and optional description) or delete one. The backend
also supports renaming (`PATCH /courses/{id}/categories/{cid}`), but this page
doesn't use it. A question needs at least one category, so a new course needs
at least one category before anyone can ask a question.

### Resources (`ResourcesPage.tsx`)

The staff side of RAG ingestion (`docs/design-rag.md` §7.5). Every action is
accepted with 202 and runs in the background on the server.

- **Add a resource** from a URL (syllabus or schedule page; a repository needs
  a branch) or by uploading a file. An upload asks "Where can people view
  this?", which becomes `link_base_url`: the file isn't stored, and AI
  citations link there (§3.2).
- **Profile picker** on every add, re-sync, replace and re-index. Adding
  defaults to the live profile. The others default to every profile the
  source is already ingested under, so its profiles stay on the same version.
- Each resource shows its **per-profile sync status** (`last_synced_at`,
  `chunk_count`, truncated chunks, `last_error`), a **Syncing** badge, and
  **Versions differ** when its profiles hold different versions.
- **Re-sync** is for URL resources. **Replace upload** is for uploads: it keeps
  the resource's id and sync rows, so searches never see a gap. **Delete**
  asks first, then removes the resource's chunks from every profile.
- **Past Q&A** re-indexes threads with a verified human answer.
- **Polling:** while any source is syncing, the page reloads every 5 s, for up
  to 15 minutes; after that it says "No result yet. Check back or re-sync."
  It uses the backend's `syncing` flag rather than comparing timestamps with
  the server's clock. A sync stays "Syncing" for about 30 s after its rows
  update, while the old chunks are cleaned up (`CLEANUP_GRACE_S`).
- Times come from the server as UTC without a zone; `formatTimestamp` adds
  the `Z` before showing them in local time.

## Things to know

- **The course picker lists every course from `GET /api/courses/mine`,
  including courses where the user is only a `STUDENT`.** The UI does not hide
  staff controls in those courses. The buttons appear, and clicking one returns
  403 from `require_course_staff`. A global admin sees every course as `STAFF`.
- Auth handling is the same as the student app: the token is kept in
  `localStorage`, there is no refresh, and logout only clears local state.
- **Theming (T8)** is the same in all three apps, each with its own copy:
  `src/index.css` defines semantic color tokens for the light and dark
  themes, and `tailwind.config.ts` replaces Tailwind's palette with them,
  so components can only use tokens (`bg-surface`, `text-ink-muted`,
  `bg-accent`, `text-danger-ink`, …). `lib/theme.ts` and
  `components/ThemeToggle.tsx` add the toggle. See [`docs/ui/`](../../docs/ui/)
  for the token list and screenshots.

## Where a RAG feature would plug in

- **AI answers are not pre-approved.** They are posted immediately, and
  staff accept one with the existing **Mark verified** button, the same path
  as any other answer. There is no separate approval flow to build here.
- **AI answers** show an **AI-generated** badge, the "Top sources given to
  the AI" block (`components/AiCitations.tsx`) and a **Retract** button
  (`PATCH …/retract`, `docs/design-rag.md` §4.7). A retracted answer is a
  collapsed "AI answer retracted by {name}" line that expands to the original.
- `QuestionsPage.tsx` shows an **AI answered** badge and a filter for AI
  answered threads with no verified answer, the ones staff still need to
  check (§4.4). The staff thread page doesn't poll.
- **Managing ingested course material** would be a new page next to
  `CategoriesPage.tsx`, with a nav link in `App.tsx`.

# `frontend/student/`: Student app

React 18 + TypeScript + Vite + Tailwind single-page app where students browse
a course's Q&A board, ask questions, and reply in threads. It is one of three
separate apps (see also [`../staff/`](../staff/) and [`../admin/`](../admin/)).
The three apps share no code. Each has its own copy of the shared files and its
own `package.json`.

## Running

| | |
|---|---|
| Dev server | `npm run dev:student` from the repo root, or `npm run dev` here → http://localhost:5173 |
| API in dev | Vite proxies `/api` to `http://localhost:8000` (`vite.config.ts`) |
| Production | `npm run build` → `dist/`, served by nginx at **`/student/`** (`base` is `/student/` only in production). `/` on nginx redirects to `/student/`. |

## Layout

```
src/
  main.tsx              React root (StrictMode)
  App.tsx               Router, auth guard, header with course picker + logout
  index.css             The semantic color tokens for the light and dark themes (T8), plus
                        global styles; tailwind.config.ts maps them to Tailwind colors
  lib/theme.ts          useTheme(): the current theme, saved choice or OS preference
  components/ThemeToggle.tsx  The sun/moon button in the header and on the login page
  lib/
    api.ts              fetch wrapper: adds Bearer token and X-App-Surface: student
    CourseContext.tsx   Which courses the user belongs to and which one is selected
    types.ts            TS mirrors of the backend's qa schemas
    utils.ts            cn() = clsx + tailwind-merge
  components/ui/        Small shadcn-style primitives: badge, button, card, input, textarea
  pages/
    LoginPage.tsx
    QuestionsPage.tsx
    AskQuestionPage.tsx
    QuestionDetailPage.tsx
```

## Routes (`App.tsx`)

| Path | Page | Backend calls |
|---|---|---|
| `/login` | `LoginPage`: username/password form, plus a **dev-only netid login** that stands in for campus SSO | `POST /api/auth/login`. Dev netid login gets a temp token, then calls `POST /api/auth/exchange-temp` |
| `/questions` | `QuestionsPage`: question list for the selected course, filterable by category, status (`OPEN`/`CLOSED`) and a text search `q` | `GET /courses/{id}/categories`, `GET /courses/{id}/questions?category_id&status&q` |
| `/questions/new` | `AskQuestionPage`: title, body, and at least one category | `POST /courses/{id}/questions`, then navigates to the new thread |
| `/questions/:questionId` | `QuestionDetailPage`: the thread. Shows every post with its kind (Answer / Follow-up) and a "Verified by staff" mark on accepted answers. Has a reply form with an Answer/Follow-up toggle (Follow-up is the default). | `GET /courses/{id}/questions/{qid}`, `POST .../posts` |
| `*` | Redirects to `/questions` | |

Every route except `/login` sits behind `RequireAuth`. It only checks that a
token exists in `localStorage`; it does not check whether the token is still
valid.

## Key behavior

- **Auth state:** the access token is stored in `localStorage.token` and sent
  as `Authorization: Bearer`. The app never calls `/api/auth/refresh`. When the
  token expires, requests fail with the backend's error message and the user
  has to log out and back in. Logout just clears the token. It does not call
  `/api/auth/logout`, so the refresh cookie stays.
- **`X-App-Surface: student`** is sent on every request. The backend
  (`backend/app/common/dependencies.py`) then treats the caller as `STUDENT` in
  the course even when they are staff or an admin. Anything done through this
  app is attributed to, and permission-checked as, a student.
- **Course selection:** `CourseContext` loads `GET /api/courses/mine` and keeps
  the selected course in `localStorage.course_id`, falling back to the first
  course. The picker in the header only appears when the user belongs to more
  than one course. Every page reads `courseId` from this context and builds
  course-scoped URLs from it. Call `refresh()` after login/logout, because the
  provider stays mounted across route changes.
- **Closed threads:** when `status` is `CLOSED`, the reply form is replaced by
  a notice. The backend enforces this too: a post to a closed thread returns
  409 (`qa_service.create_post`).
- **Errors:** `api.ts` throws `Error(message)` using the backend's `message`
  field. Pages show it inline.

## Where a RAG feature would plug in

AI answers (`docs/design-rag.md` §4.4–4.5) are wired in:
- `types.ts`: `author_role` includes `'AI'`, `author` can be `null`, and
  posts carry `citations`. An AI post shows an **AI-generated** badge (badge
  variant `ai`) and no author name.
- `components/AiCitations.tsx` shows "Top sources given to the AI" under an
  AI answer. Document sources open their `citation_url` (only `http(s)`
  links are rendered as links); past questions link to this app's
  `/questions/{id}`. The staff app has its own copy.
- `AskQuestionPage.tsx` navigates with `{ justAsked: true }`, and only then
  does `QuestionDetailPage.tsx` poll every 5 s, up to 36 times, until an AI
  post appears. The page clears that history state as soon as it reads it,
  so a reload or Back doesn't poll again. Opening a thread from the list
  doesn't poll.
- Students never receive retracted AI answers, so there's nothing to hide here.

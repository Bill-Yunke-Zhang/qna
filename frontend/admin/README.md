# `frontend/admin/`: Admin app

React 18 + TypeScript + Vite + Tailwind single-page app for global
administrators (`User.role == "ADMIN"`). Admins manage courses, course rosters
and staff lists, local user accounts, and per-course access grants. Every call
goes to `/api/admin/*`, which the backend guards with `require_admin`. This
app does not touch the Q&A board itself.

It started from the same template as [`../student/`](../student/) and
[`../staff/`](../staff/) (same `components/ui/*`, `lib/utils.ts`, Tailwind
setup), but its structure is different: there is no `CourseContext`, no
`types.ts`, and no `X-App-Surface` header.

## Running

| | |
|---|---|
| Dev server | `npm run dev:admin` from the repo root → http://localhost:5175 |
| API in dev | Vite proxies `/api` to `http://localhost:8000` |
| Production | Built to `dist/` and served by nginx at **`/admin/`** |

## Layout

```
src/
  App.tsx               Router, RequireAdmin guard, sidebar (Courses, Users, Logout)
  lib/api.ts            fetch wrapper (Bearer token) + postForm() for multipart CSV uploads
  lib/utils.ts          cn()
  index.css             Tailwind directives and global styles (with tailwind.config.ts at the app root,
                        where a theme/colour-token layer would go)
  components/ui/        badge, button, card, input, textarea
  pages/
    LoginPage.tsx       username/password only (no dev netid login)
    CoursesPage.tsx
    RosterPage.tsx
    UsersPage.tsx
    UserDetailPage.tsx
```

Response types are declared inline at the top of each page, not in a shared
`types.ts`. They mirror `backend/app/schemas/admin.py`.

## Routes

| Path | Page | Backend calls |
|---|---|---|
| `/login` | Username/password login | `POST /api/auth/login` |
| `/courses` | List, create and edit courses (name, semester) | `GET`/`POST /admin/courses`, `PUT /admin/courses/{id}` |
| `/courses/:courseId/roster` | The course's student roster and staff list (below) | `GET /admin/courses/{id}/roster`, `POST .../roster` (CSV), `PATCH .../roster/{rid}`, `GET .../staff`, `POST .../staff` (CSV) |
| `/users` | List users and create a local account (username, display name, optional email, password) | `GET`/`POST /admin/users` |
| `/users/:userId` | One user's details and course access. Grant `STUDENT` or `STAFF` access to a course, or revoke it. | `GET /admin/users/{id}`, `GET /admin/courses`, `POST /admin/users/{id}/course-access`, `DELETE /admin/users/{id}/course-access/{cid}` |
| `*` | Redirects to `/courses` | |

### Roster page

The page has two separate upload flows that behave differently on the backend:

- **Upload Canvas Gradebook CSV → student roster.** The backend
  (`services/roster_service.py`) reads the `Student` and `SIS Login ID`
  columns, skips Canvas's "Points Possible" row, and upserts `CourseRoster`
  rows. The result shows imported, updated and deactivated counts plus per-row
  errors. **This does not create accounts or grant access by itself.** A
  student gets `STUDENT` access the next time they log in. Each roster row has
  an active/inactive toggle (`PATCH {is_active}`). Deactivating a row does not
  revoke access the student already has; use the user page to revoke it.
- **Upload Staff CSV → staff list.** `services/staff_service.py` creates
  missing accounts **right away** and grants `STAFF` on this course. The
  result shows accounts created, access granted, already-staff counts and
  errors.

Uploads use `api.postForm()`, which leaves out `Content-Type` so the browser
sets the multipart boundary. The backend caps each file at 2 MB
(`common/uploads.py`).

## Things to know

- **`RequireAdmin` only checks that a token exists.** It does not check the
  role. A non-admin who logs in here sees the layout, and every data call
  returns 403 "Admin access required".
- The backend has endpoints this UI doesn't use: `POST /admin/courses/{id}/roster/import`
  (JSON rows), `PUT`/`DELETE /admin/users/{id}` (edit/delete a user, change the
  global role) and `GET /admin/courses/{id}`. To use them, call the API directly,
  for example through the Swagger UI at `/api/docs` (development only).
- Auth handling is the same as the other apps: the token is kept in
  `localStorage`, there is no refresh, and logout only clears local state.

# QnA

A Piazza-style course question-and-answer board. Students ask questions, course staff (and other students) answer them, and every question is the root of a discussion thread that stays open — accepting new answers and follow-ups — until course staff explicitly close it.

- Course-scoped: every question, category, and thread belongs to one course; access is granted per user, per course
- Students post questions and answers; staff can additionally manage categories, mark any answer verified, and close/reopen threads
- Keyword search and category filtering over the question board
- Local accounts and campus-SSO-style login (via an OAuth2 proxy in front of this service), same pattern as this course's other projects

There is currently **no AI component** — building a RAG-based auto-responder on top of this board is the assignment.

## Prerequisites

| Tool | Minimum version | Purpose |
|---|---|---|
| Docker Engine / Docker Desktop | 25 / 4.x | Running the full stack |
| Node.js | 20 | Frontend development servers |
| Python | 3.12 | Integration tests (optional if using Docker only) |

---

## First-time setup

### 1. Copy and configure environment

```bash
cp .env.template .env
```

Open `.env` and set:

| Variable | What to do |
|---|---|
| `MYSQL_ROOT_PASSWORD` | Choose a strong password |
| `MYSQL_PASSWORD` | Choose a strong password (used by the app) |
| `DATABASE_URL` | Update `change_me_app` to match `MYSQL_PASSWORD` |
| `ADMIN_USERNAME` | Username for the first admin account |
| `ADMIN_PASSWORD` | Password for the first admin account |
| `GRADER_PASSWORD_HASH` | Leave as it is in `.env.template`. Startup creates an admin user named `grader` from it; only course staff know its password, and they use it to grade your deployed application |
| `JWT_PRIVATE_KEY` | See step 2 (optional in dev — see note below) |
| `JWT_PUBLIC_KEY` | See step 2 (optional in dev — see note below) |

### 2. Create the Python virtual environment

Run the included setup script once after cloning. It creates `.venv`, installs all dependencies, and patches the activate script so your `.env` variables load automatically whenever the environment is activated:

```bash
bash scripts/setup_venv.sh
```

Then activate the environment (do this at the start of every terminal session):

```bash
source .venv/bin/activate        # macOS / Linux
```

> **Windows:** The setup script targets bash. On Windows, create the venv manually (`python3.12 -m venv .venv`), install dependencies (`pip install -r backend/requirements.txt -r tests/integration/requirements.txt`), and load `.env` variables in your shell before running any scripts.

### 3. Generate JWT signing keys (optional in development)

The backend signs tokens with RS256. If `JWT_PRIVATE_KEY`/`JWT_PUBLIC_KEY` are left blank, the backend auto-generates an ephemeral key pair at startup and logs a warning — convenient for local dev, but every restart invalidates existing tokens. Run the included helper once you want logins to survive a restart:

```bash
# With the virtual environment active (cryptography is already installed):
python backend/scripts/generate_keys.py
```

Paste the two `JWT_*` lines into `.env`.

### 4. Install frontend dependencies

```bash
npm install            # installs concurrently (root dev tool)
npm run install:all    # installs dependencies in all three frontend apps
```

> **Note:** Running `npm run build` is only needed if you want the pre-built apps to be served by Nginx at `http://localhost:8080`. If you plan to use the Vite dev servers (the typical workflow), you can skip the build step entirely.

### 5. Start the Docker stack

```bash
docker compose up
```

On first run, Docker builds the backend image and pulls MySQL, Redis, and Nginx. MySQL takes ~30 seconds to become healthy before the backend starts.

> **First run note:** On initial startup, MySQL takes 30–45 seconds to initialize the database user, and the backend will **wait — logging `admin_bootstrap_waiting_for_schema` every few seconds — until you run the migrations in the next step**, because its startup needs the database schema, which doesn't exist yet. Both behaviors are normal.

### 6. Run database migrations

```bash
docker compose run --rm backend alembic upgrade head
```

This creates all tables. Within a few seconds the waiting backend picks up the new schema, finishes starting, and bootstraps the admin account from `ADMIN_USERNAME`/`ADMIN_PASSWORD` — no manual step needed.

### 7. (Optional) Seed demo content

```bash
python scripts/seed_demo.py
```

Creates a demo course with staff-managed categories and a batch of realistic, entirely synthetic historical question threads — see [Load the demo content](#load-the-demo-content) below.

---

## Accessing the application

| Interface | URL | Notes |
|---|---|---|
| Student app | http://localhost:8080/student/ | Ask questions, browse/search the board |
| Staff app | http://localhost:8080/staff/ | Answer questions, manage categories, close/reopen threads |
| Admin app | http://localhost:8080/admin/ | Course/roster/user access management |
| API (direct) | http://localhost:8000 | Bypasses Nginx |
| Interactive API docs | http://localhost:8000/api/docs | Swagger UI (dev only) |
| Health check | http://localhost:8000/api/health | Service status |

Log in to the Admin app with the `ADMIN_USERNAME` / `ADMIN_PASSWORD` you set in `.env`. From there, create a course, grant yourself (or a test account) `STAFF` access, and upload a roster so students can be granted `STUDENT` access.

The Student and Staff apps authenticate the same way this course's other projects do: in production, a campus-SSO OAuth2 proxy sits in front of this service and sets `X-Auth-Request-User`/`X-Auth-Request-Email` headers, which `/api/auth/oauth2-callback` turns into an account automatically. In development (`APP_ENV=development`, the Docker Compose default), the login pages also expose a **netid dev-login** shortcut that calls the same account-creation path directly — no SSO proxy required locally.

**Security note:** those `X-Auth-Request-*` headers are otherwise trivial for anyone with network access to this service to set themselves and impersonate any user — so `/api/auth/oauth2-callback` refuses every request until `OAUTH2_PROXY_SHARED_SECRET` is set in `.env` *and* the request carries a matching `X-Proxy-Shared-Secret` header. In development that's fine to leave unset — use the dev netid login instead. Only set it once a real OAuth2 proxy is deployed in front of this service, configured to send the same secret and to strip any client-supplied copy of it before forwarding.

---

## Development workflow

### Starting a session

**1. Activate the Python virtual environment** in any terminal where you will run Python tools (tests, migrations, scripts):

```bash
source .venv/bin/activate
```

Not needed for the Docker stack itself — the backend runs inside its own container.

**2. Start the Docker stack** (backend, MySQL, Redis, Nginx):

```bash
docker compose up
```

The backend mounts `./backend` and runs with `--reload`, so any Python change takes effect immediately.

**3. Start all frontend dev servers** in a single terminal from the repo root:

```bash
npm run dev
```

```
[student] VITE ready  →  http://localhost:5173
[staff]   VITE ready  →  http://localhost:5174
[admin]   VITE ready  →  http://localhost:5175
```

Check the terminal output for the exact URLs — Vite picks the next available port if the default is in use. Press `Ctrl+C` once to stop all three.

To start a single app instead:

```bash
npm run dev:student
npm run dev:staff
npm run dev:admin
```

The Vite dev servers proxy `/api` traffic to the Docker backend, so the full stack works at these ports during development.

### During a session

- **Backend changes** — saved automatically; uvicorn reloads the process within a second.
- **Frontend changes** — saved automatically; the browser hot-reloads via the Vite dev server.
- **Database model changes** — generate and apply a migration:

```bash
docker compose exec backend alembic revision --autogenerate -m "describe change"
docker compose exec backend alembic upgrade head
```

### Ending a session

```bash
docker compose down
```

If you made frontend changes and want `localhost:8080` to reflect them, run a final build before stopping:

```bash
npm run build
```

### Other migration commands

```bash
docker compose exec backend alembic upgrade head
docker compose exec backend alembic downgrade -1
```

---

## Testing

### Integration test suite

Tests run against the live Docker stack (start it first). Activate the environment, then run:

```bash
python -m pytest tests/integration/ -q
```

### Unit tests

Runs against the FastAPI app directly with a mocked database — no Docker stack required:

```bash
cd tests/unit && pytest -v
```

---

## Common operations

### Load the demo content

```bash
python scripts/seed_demo.py
```

Creates two courses so there's something to exercise the multi-course picker with:

- **AI-Assisted Software Development** — categories mirroring a real course support board (Environment Setup, Git & CI/CD, Docker & Containers, Claude Code / AI Tools, Databases, Project Logistics) and 8 synthetic question threads.
- **General Chemistry I** — an unrelated course with its own categories (Stoichiometry & Calculations, Lab Safety & Procedure, Acids & Bases, Thermodynamics, Homework & Grading, Exams & Review) and 8 synthetic question threads.

Both span open/closed and accepted/unaccepted states, so there's realistic history to browse — and, later, to ingest.

### Import a course roster (students)

Roster uploads expect a Canvas gradebook export CSV. Upload via the Admin UI (Courses → Roster & Staff → Upload CSV), or via the API:

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"change_me_admin"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -X POST "http://localhost:8000/api/admin/courses/{course_id}/roster" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@sample_rosters/sample_roster_from_gradebook.csv"
```

Uploading a roster only creates `CourseRoster` entries (for gradebook-style tracking) — it does **not** immediately create accounts or grant access. Instead, `STUDENT` access is granted automatically the next time a listed (and active) netid logs in, whether via the dev netid fallback or the real campus-SSO flow. This is deliberate: a course roster is typically hundreds of students who haven't logged in yet, so eagerly creating that many accounts up front would be wasted work — and it means re-uploading an updated roster (deactivating dropped students, adding late adds) never needs a separate access-sync step.

If you need to grant or revoke access for one specific person outside the roster flow, that's still available via the Admin UI (Users → select a user → Grant Course Access) or the API.

### Import course staff

Staff uploads use a simpler CSV — `netid,full_name,email` — since course staff are a handful of people curated by hand, not a gradebook export. Upload via the Admin UI (Courses → Roster & Staff → Upload Staff CSV), or via the API:

```bash
curl -X POST "http://localhost:8000/api/admin/courses/{course_id}/staff" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@sample_rosters/sample_staff.csv"
```

Unlike the student roster, this takes effect **immediately**: an account is created for any netid that doesn't already have one, and `STAFF` access to that course is granted right away — no login-first step, since staff need access from day one, not eventually. Re-uploading the same file is safe (idempotent): existing accounts and grants are left alone, just reported back as already-staff.

### View structured logs

```bash
docker compose logs -f backend
```

### Reset the database (destructive)

```bash
docker compose down -v               # removes the MySQL volume
docker compose up --build
docker compose run --rm backend alembic upgrade head
```

---

## Project structure

```
qna/
├── backend/
│   ├── app/
│   │   ├── routers/        HTTP endpoints  (auth, admin, qa, health)
│   │   ├── services/       Business logic  (auth, roster, qa/threads)
│   │   ├── models/         SQLAlchemy ORM models
│   │   ├── schemas/        Pydantic request/response schemas
│   │   ├── common/         Dependencies, exceptions, rate limiting, logging
│   │   └── migrations/     Alembic schema migrations
│   ├── scripts/
│   │   └── generate_keys.py   RS256 key-pair generator
│   └── requirements.txt
├── frontend/
│   ├── student/             React app — ask, browse, search  (typically port 5173 in dev)
│   ├── staff/                React app — answer, verify, manage categories, close threads  (typically port 5174 in dev)
│   └── admin/                 React app — course/roster/user management   (typically port 5175 in dev)
├── nginx/
│   └── nginx.dev.conf      Reverse-proxy config
├── mysql-init/             SQL scripts run by MySQL on first startup
├── scripts/
│   └── seed_demo.py         Seeds a demo course with synthetic Q&A history
├── tests/
│   ├── integration/        Pytest suite against the live stack
│   └── unit/                Pytest suite against the app directly (mocked DB)
├── sample_rosters/          Example Canvas gradebook CSV (roster) and staff CSV
├── eval/                    RAG configuration comparison kit (ground truth, sample data, harness — see eval/README.md)
├── ai_log/                  Claude Code session logs (auto-generated, committed by hook)
├── docker-compose.yml
├── .env.template            Copy to .env and fill in before first run
└── .claude/                 Claude Code hook configuration
```

---

## Architecture overview

```
Browser (HTTP)
      │
      ▼
   Nginx :8080
   ├── /api/*      → FastAPI backend :8000
   ├── /student/   → Student React app (static)
   ├── /staff/     → Staff React app    (static)
   └── /admin/     → Admin React app   (static)
                          │
                     FastAPI :8000
                     ├── SQLAlchemy → MySQL :3306
                     └── redis-py   → Redis :6379
```

Everything is plain request/response REST — there is no WebSocket layer, since a question board has no real-time gameplay state to synchronize. Redis is reserved for caching and rate-limiting (a natural place to build the abuse-control mechanism the RAG feature will need).

## Domain model

- **Course** — the scope everything else lives inside. **CourseRoster** tracks gradebook-imported student entries; **UserCourseAccess** is the actual login grant (`STUDENT` or `STAFF`) per user, per course — populated by roster sync at login (students), staff CSV upload (immediate), or a one-off manual admin grant.
- **Category** — a staff-managed tag; a question can carry more than one.
- **Question** — the root of a discussion thread. `status` is `OPEN` or `CLOSED`; closing is an explicit staff action, and a closed thread accepts no further posts until reopened.
- **Post** — every entry in a question's thread (`kind: ANSWER | FOLLOWUP`), from a student or staff member. `author_role` snapshots the poster's course role *at post time*, so a "Course Staff" badge never retroactively changes if someone's access is later revoked. Staff can mark any `ANSWER` post — regardless of who wrote it — `is_accepted`; at most one accepted post per question.

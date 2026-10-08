#!/usr/bin/env python3
"""
Seed two demo courses into a running QnA backend with realistic, entirely
synthetic historical Q&A — no real student data (see the project's FERPA
note in course_design.md; this script only ever invents content).

Creates, per course:
  - The course itself
  - A handful of staff-managed categories mirroring a real course support board
  - A batch of historical question threads across those categories, each
    with an answer; some are marked accepted, and a couple are closed —
    so the RAG feature you build later has real thread history to ingest
    and real "closed thread" / "accepted answer" states to reason about.

Two courses (rather than one) exist specifically so there's something to
exercise the multi-course picker with — a "software dev" course support
board (Docker, Git, Claude Code, …) and an unrelated "intro chemistry"
course, so the two knowledge bases stay obviously distinct.

Everything is posted under the bootstrap admin account (global ADMIN acts
as course staff automatically), so don't read too much into the fact that
the "student" question and the "staff" answer share one author — it's a
simplification for seed data, not a statement about how the app works.

Usage:
    python scripts/seed_demo.py

Optional environment variables (defaults shown):
    BASE_URL        http://localhost:8000
    ADMIN_USERNAME  admin
    ADMIN_PASSWORD  change_me_admin
"""

import os
import sys

import httpx

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change_me_admin")

G = "\033[92m✓\033[0m"
AR = "\033[94m→\033[0m"

# ---------------------------------------------------------------------------
# Course 1 — AI-Assisted Software Development (support board content)
# ---------------------------------------------------------------------------

SWDEV_CATEGORIES = [
    ("Environment Setup", "Docker, .env, JWT keys, and other first-run issues."),
    ("Git & CI/CD", "Branching, merge requests, and the pipeline."),
    ("Docker & Containers", "docker compose, service health, and the network."),
    ("Claude Code / AI Tools", "CLAUDE.md, hooks, AI session logging."),
    ("Databases", "MySQL, Alembic migrations, and schema changes."),
    ("Project Logistics", "Team workflow, accounts, and submission questions."),
]

# Each entry: (title, body, category_names, answer_body, accepted, closed)
SWDEV_QUESTIONS = [
    (
        "docker compose up hangs forever on a fresh clone — is that normal?",
        "I ran `docker compose up` right after cloning and the backend just keeps "
        "logging `admin_bootstrap_waiting_for_schema` every few seconds. Did I break something?",
        ["Docker & Containers", "Environment Setup"],
        "That's expected on a brand-new database — the schema doesn't exist until you run "
        "migrations. Open a second terminal and run "
        "`docker compose run --rm backend alembic upgrade head`. The waiting backend picks up "
        "the new schema within a few seconds and finishes starting on its own.",
        True,
        True,
    ),
    (
        "Do we need to squash commits before opening a merge request?",
        "Our team has a bunch of small WIP commits on our feature branch. Should we squash "
        "them before opening the MR, or is that not required?",
        ["Git & CI/CD", "Project Logistics"],
        "Not required — the rubric asks for atomic commits with clear messages, not a single "
        "squashed commit. If your WIP commits are genuinely small logical steps with clear "
        "messages, leave them. If they're just 'wip', 'wip2', 'fix typo', clean those up before "
        "opening the MR so the history stays readable.",
        False,
        False,
    ),
    (
        "What's the actual difference between CLAUDE.md and .claude/settings.json?",
        "I keep mixing these up. Both seem to configure Claude Code — what's each one actually for?",
        ["Claude Code / AI Tools"],
        "CLAUDE.md is prose — it's auto-loaded at session start and is where you put codebase "
        "overview, conventions, and behavioral rules for Claude to read. .claude/settings.json is "
        "structured config — permissions (allow/deny specific tools or commands), hooks, and "
        "environment variables. There's no 'rules' field in settings.json; behavioral rules always "
        "belong in CLAUDE.md prose, not JSON.",
        True,
        False,
    ),
    (
        "My ai_log/ folder isn't getting new commits — did I break the logging hook?",
        "I've had several Claude Code sessions today but ai_log/ still only has last week's files. "
        "How do I check whether the hook is actually running?",
        ["Claude Code / AI Tools"],
        "First check `.claude/settings.json` is committed and present in your working copy — if you "
        "gitignored it or it's missing after a rebase, the hooks won't fire. Then have a short Claude "
        "Code session and watch for a new file in ai_log/ right after it ends; the Stop hook writes and "
        "commits it automatically. If nothing appears, run "
        "`python3 .claude/hooks/log_ai.py debug <transcript_path>` to see what it's parsing.",
        True,
        True,
    ),
    (
        "alembic upgrade head fails with 'table already exists' — how do I reset?",
        "I ran migrations twice by accident I think. Now `alembic upgrade head` fails because a table "
        "already exists. What's the safe way to reset in dev?",
        ["Databases"],
        "In development it's safe to nuke the volume and start clean: "
        "`docker compose down -v` (removes the MySQL volume), then `docker compose up --build`, then "
        "`docker compose run --rm backend alembic upgrade head` again. Don't do this against anything "
        "with data you care about — `-v` is destructive.",
        True,
        False,
    ),
    (
        "Can our team use a monorepo-style branch strategy instead of one branch per feature?",
        "We're a team of 4 and it feels like a lot of overhead to open a separate branch and MR for "
        "every tiny change. Can we work on a shared 'dev' branch instead and open fewer, bigger MRs?",
        ["Project Logistics", "Git & CI/CD"],
        "The rubric specifically credits independent features/fixes living on their own descriptively "
        "named branches — that's part of what's graded, not just a suggestion. A shared long-lived "
        "'dev' branch with infrequent giant MRs will read as weak version-control practice even if the "
        "code itself is fine. Keep branches scoped to one logical change each.",
        False,
        False,
    ),
    (
        "Backend crashes on startup with 'JWT_PRIVATE_KEY not configured'",
        "I copied .env.template to .env but didn't touch the JWT lines. Now the backend won't start. "
        "Do I have to generate real keys before I can even run the stack?",
        ["Environment Setup"],
        "You don't — leaving JWT_PRIVATE_KEY/JWT_PUBLIC_KEY blank is fine for local dev; the backend "
        "auto-generates an ephemeral key pair in memory and logs a warning instead of failing. The "
        "tradeoff is that tokens are invalidated on every restart. Run "
        "`python backend/scripts/generate_keys.py` and paste the two lines into .env once you want "
        "logins to survive a restart.",
        True,
        False,
    ),
    (
        "Is it OK for two team members to be logged into the same local test account?",
        "We've been sharing one admin login while we're both testing the app locally. Is that going to "
        "cause problems for the AI-usage or contribution grading?",
        ["Project Logistics"],
        "It won't corrupt any data, but it will make your commit-email-based contribution and AI-usage "
        "tracking less accurate for both of you — that's identified by git commit email, not by which "
        "account you were logged into in the browser. Sharing a browser session for manual testing is "
        "fine; just make sure your actual commits and Claude Code sessions each use your own identity.",
        True,
        False,
    ),
]

# ---------------------------------------------------------------------------
# Course 2 — General Chemistry I (intro college chemistry course board)
# ---------------------------------------------------------------------------

CHEM_CATEGORIES = [
    (
        "Stoichiometry & Calculations",
        "Balancing equations, mole conversions, molarity, dilutions.",
    ),
    (
        "Lab Safety & Procedure",
        "Safety rules, waste disposal, lab report requirements, makeup labs.",
    ),
    ("Acids & Bases", "pH, titration, indicators, buffers."),
    ("Thermodynamics", "Enthalpy, calorimetry, heat of reaction."),
    ("Homework & Grading", "Grading policy, late work, curves, extra credit."),
    ("Exams & Review", "Exam format, allowed materials, review sessions."),
]

CHEM_QUESTIONS = [
    (
        "How do I balance the combustion equation for C4H10?",
        "I keep ending up with fractional coefficients for O2 when I try to balance "
        "C4H10 + O2 -> CO2 + H2O. Am I doing something wrong?",
        ["Stoichiometry & Calculations"],
        "Fractional coefficients aren't wrong mid-process — balance C and H first (you'll get "
        "13/2 O2), then multiply every coefficient in the whole equation by 2 to clear the "
        "fraction: 2 C4H10 + 13 O2 -> 8 CO2 + 10 H2O. Final answers should always be in "
        "whole-number, lowest-ratio form.",
        True,
        False,
    ),
    (
        "Do we need to show significant figures on every calculation in lab reports?",
        "Some of our intermediate calculation steps have long decimals. Do those need to be "
        "rounded to sig figs too, or just the final answer?",
        ["Lab Safety & Procedure", "Homework & Grading"],
        "Round only the final reported answer — carry extra digits through intermediate steps "
        "so rounding error doesn't compound, then apply sig fig rules once at the end. Reports "
        "that round at every step and reports that never round at all both lose points under "
        "the rubric; it's specifically the final answer's sig figs that are graded.",
        True,
        True,
    ),
    (
        "What's the difference between molarity and molality, and which do we use for freezing point depression?",
        "The textbook uses both and I can't keep them straight. For the freezing point "
        "depression problems on the homework, which one goes in the formula?",
        ["Stoichiometry & Calculations"],
        "Molarity is moles solute per liter of *solution*; molality is moles solute per "
        "kilogram of *solvent*. Freezing point depression (ΔTf = i·Kf·m) uses molality (m) "
        "specifically because molality doesn't change with temperature — the volume a solution "
        "occupies does, but the mass of solvent doesn't.",
        True,
        False,
    ),
    (
        "My titration didn't reach the theoretical endpoint color — did I mess up entirely?",
        "My phenolphthalein turned a very faint pink well before the volume I calculated as the "
        "theoretical endpoint. Is my whole run unusable?",
        ["Acids & Bases"],
        "Not necessarily — phenolphthalein changes color over a pH range (roughly 8.2–10), so a "
        "faint pink is the *start* of the color change, not necessarily an error. Report the "
        "volume where you first saw a color change that persisted for 30 seconds with swirling. "
        "If your calculated concentration is within ~5% of the known value, the run is fine.",
        True,
        False,
    ),
    (
        "Is a calculator with programmable memory allowed on the midterm?",
        "I have a TI-83 that has some formulas saved in memory from a previous class. Can I use "
        "it as-is on the midterm, or do I need to clear it first?",
        ["Exams & Review"],
        "Clear the memory first, or bring a different calculator. The syllabus only permits "
        "basic scientific calculators for exams — no graphing, no programmable/stored-formula "
        "memory. A TI-83 with saved programs counts as programmable even if you don't plan to "
        "use the saved formulas.",
        True,
        True,
    ),
    (
        "Can we get extra credit for attending the review session?",
        "A few of us are wondering if showing up to the optional review session before the exam "
        "counts for any extra credit, or if it's purely optional with no grade benefit.",
        ["Homework & Grading"],
        "There's no formal extra-credit points for attending — it's there because students who "
        "come tend to do better on the exam, not because attendance itself is graded. We don't "
        "track attendance at review sessions.",
        False,
        False,
    ),
    (
        "Why does the calorimetry lab ask us to use styrofoam cups instead of the metal calorimeter?",
        "The stockroom has real bomb calorimeters. Why are we using styrofoam coffee cups for "
        "our enthalpy of reaction lab instead?",
        ["Thermodynamics", "Lab Safety & Procedure"],
        "Styrofoam is a much better insulator with much lower heat capacity than metal, so it "
        "introduces far less error into a simple constant-pressure calorimetry measurement — "
        "and it's cheap enough that everyone gets their own instead of sharing one instrument. "
        "Bomb calorimeters are for constant-volume combustion measurements, which is a different "
        "lab later in the semester.",
        True,
        False,
    ),
    (
        "I missed the acid-base lab due to illness — how do I make it up?",
        "I was out sick during this week's titration lab. What's the process for making it up?",
        ["Lab Safety & Procedure", "Homework & Grading"],
        "Email your TA with your section and the date you missed, and they'll add you to the "
        "makeup lab section that runs during the last week of the module (see the syllabus "
        "calendar). You'll need a note from student health services or a signed absence form for "
        "it to count as excused.",
        True,
        True,
    ),
]

# ---------------------------------------------------------------------------
# Courses to seed
# ---------------------------------------------------------------------------

COURSES = [
    {
        "name": "AI-Assisted Software Development",
        "semester": "Fall 2026",
        "categories": SWDEV_CATEGORIES,
        "questions": SWDEV_QUESTIONS,
    },
    {
        "name": "General Chemistry I",
        "semester": "Fall 2026",
        "categories": CHEM_CATEGORIES,
        "questions": CHEM_QUESTIONS,
    },
]


def login(client: httpx.Client) -> str:
    resp = client.post(
        f"{BASE_URL}/api/auth/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
    )
    resp.raise_for_status()
    token = resp.json()["access_token"]
    print(f"  {G} Logged in as {ADMIN_USERNAME!r}")
    return token


def create_course(client: httpx.Client, name: str, semester: str) -> int:
    resp = client.post(
        f"{BASE_URL}/api/admin/courses",
        json={"name": name, "semester": semester},
    )
    resp.raise_for_status()
    course = resp.json()
    print(f"  {G} Created course '{course['name']}' (id={course['id']})")
    return course["id"]


def create_categories(
    client: httpx.Client, course_id: int, categories: list[tuple[str, str]]
) -> dict[str, int]:
    ids: dict[str, int] = {}
    for name, description in categories:
        resp = client.post(
            f"{BASE_URL}/api/courses/{course_id}/categories",
            json={"name": name, "description": description},
        )
        resp.raise_for_status()
        category = resp.json()
        ids[name] = category["id"]
        print(f"  {G} Category '{name}' (id={category['id']})")
    return ids


def create_questions(
    client: httpx.Client,
    course_id: int,
    category_ids: dict[str, int],
    questions: list[tuple[str, str, list[str], str, bool, bool]],
) -> None:
    for title, body, category_names, answer_body, accepted, closed in questions:
        resp = client.post(
            f"{BASE_URL}/api/courses/{course_id}/questions",
            json={
                "title": title,
                "body": body,
                "category_ids": [category_ids[name] for name in category_names],
            },
        )
        resp.raise_for_status()
        question = resp.json()
        question_id = question["id"]

        resp = client.post(
            f"{BASE_URL}/api/courses/{course_id}/questions/{question_id}/posts",
            json={"kind": "ANSWER", "body": answer_body},
        )
        resp.raise_for_status()
        posts = resp.json()["posts"]
        post_id = posts[-1]["id"]

        if accepted:
            resp = client.patch(
                f"{BASE_URL}/api/courses/{course_id}/questions/{question_id}/posts/{post_id}/accept",
                json={"is_accepted": True},
            )
            resp.raise_for_status()

        if closed:
            resp = client.post(
                f"{BASE_URL}/api/courses/{course_id}/questions/{question_id}/close"
            )
            resp.raise_for_status()

        flags = []
        if accepted:
            flags.append("accepted")
        if closed:
            flags.append("closed")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        title_preview = title[:60] + ("…" if len(title) > 60 else "")
        print(f"  {G} Q{question_id:03d}{flag_str}  {title_preview}")


def seed_course(client: httpx.Client, course: dict) -> int:
    course_id = create_course(client, course["name"], course["semester"])

    print(f"\n{AR} Creating {len(course['categories'])} categories …\n")
    category_ids = create_categories(client, course_id, course["categories"])

    print(f"\n{AR} Creating {len(course['questions'])} question threads …\n")
    create_questions(client, course_id, category_ids, course["questions"])

    return course_id


def main() -> None:
    print(f"\n{AR} QnA — demo seed  ({BASE_URL})\n")

    course_ids = []
    with httpx.Client(timeout=15) as client:
        token = login(client)
        client.headers["Authorization"] = f"Bearer {token}"

        for i, course in enumerate(COURSES):
            if i > 0:
                print()
            print(f"{AR} Seeding '{course['name']}' ({course['semester']}) …")
            course_ids.append(seed_course(client, course))

    course_list = "\n".join(
        f"    - {c['name']} ({c['semester']}): course_id={cid}"
        for c, cid in zip(COURSES, course_ids)
    )
    print(
        f"\n{AR} Done!  To explore the demo:\n"
        f"\n"
        f"    1. Open the Student app  →  http://localhost:8080/student/\n"
        f"       (or http://localhost:5173 if the Vite dev server is running)\n"
        f"    2. Use the dev netid login (any netid — e.g. 'demo') to sign in\n"
        f"       — but you'll need course access granted first via the Admin app\n"
        f"    3. Or open the Admin app  →  http://localhost:8080/admin/\n"
        f"       and log in with your admin credentials to grant yourself access\n"
        f"\n"
        f"{course_list}\n"
    )


if __name__ == "__main__":
    try:
        main()
    except httpx.HTTPStatusError as exc:
        print(
            f"\n✗  HTTP {exc.response.status_code}: {exc.response.text}",
            file=sys.stderr,
        )
        sys.exit(1)
    except httpx.ConnectError:
        print(
            f"\n✗  Could not connect to {BASE_URL}.\n"
            f"   Is the Docker stack running?  (docker compose up)",
            file=sys.stderr,
        )
        sys.exit(1)

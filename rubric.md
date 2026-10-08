# Project 3: QnA — Rubric

**Changelog:** 2026-10-07 — New R0 (Team Schedule, 3 points), funded by 1 point each from
R5, R6 and R7; total remains 100. R7 covers five comparison axes (generation model added); R11
wording corrected to match the five sections T10 lists. 2026-08-25 — R11 (Individual Markdown Document) reduced from 8 to 6 points;
R13 (TA Code Review) increased from 8 to 10 points, so the TA Code Review weight matches
P1/P2/P4. Total remains 100.

This is the grading contract for Project 3. The project is worth **100 points**, graded by the course's automated grading pipeline together with course staff review. After grading, a report is posted to your repository; it is **provisional until your TA code review (R13)**, which is also where any automated-grading errors are corrected.

Each item below names the [instructions.md](instructions.md) task(s) it assesses.

**How automated items are judged.** Each item graded by an AI reviewer is checked against the criteria listed below, and only those criteria. Three independent reviews look for shortfalls, and a shortfall lowers your score only when at least two of them report it, each citing specific evidence from your repository (a file and line, a commit, or a test result). Minor issues cost little; a missing or non-working required deliverable costs more. Your report lists every shortfall that counted and the evidence for it, so you can check it and raise a specific correction at your TA code review.

## R0 — Team Schedule (3 points)

**Assesses:** the Team Schedule section at the top of [instructions.md](instructions.md)
**Criteria:** five checks, each worth an equal share of the points.
- `docs/schedule.md` was on `main` by the schedule due time (Wednesday, October 14 at 11:59 PM). If it was not, this item scores 0; slip days do not apply.
- The Team section lists every team member's NetID.
- The Timeline table has the Milestone, Tasks, Owner and Target date columns, and every row has an owner who is a team member and a `YYYY-MM-DD` target date.
- The timeline covers every task from T3 to T10, and every member owns at least one row.
- The Check-ins section lists at least two dated check-ins.

Only timing and form are graded. Whether you kept to the schedule is not graded, and updating the document later never changes this score.

**What graders examine:** the version of `docs/schedule.md` that was on `main` at the schedule due time, checked by a script.

## R1 — Version Control Usage (5 points)

**Assesses:** T1
**Criteria:**
- Independent features and fixes were developed on their own descriptively-named branches.
- Commits are atomic with clear, consistently-formatted messages, under a consistent per-member identity.
- All work reached `main` through merge requests; history was never rewritten.

**What graders examine:** the repository's branch history, commit messages and author identities, and merge request records.

## R2 — CI/CD Compliance (4 points)

**Assesses:** T2
**Criteria:**
- Every merged MR passed the full pipeline.
- Every MR was approved by someone who did not author it: your teammate, or, if your teammate has not reviewed it within 48 hours of your review request, a TA or instructor.
- Each member reviews their teammate's MRs promptly. An MR that needed a staff approval because you did not review it costs you, not the author, 1 point (up to 2). An MR left 48 hours with no teammate review costs each teammate who did not review it; the author of an MR is never charged.
- The pipeline itself was not altered or bypassed to make checks pass.

**What graders examine:** pipeline and approval records on each merge request, including who was asked to review and when.

## R3 — AI Logging Verification (4 points)

**Assesses:** T0
**Criteria:**
- Each member completed the logging verification before their own code work began (a session log no later than 24 hours after their first code commit).
- Each member's AI-assisted work is logged as it happens: at least half of the days on which you
  commit code have a session log from that day or the day before or after.

This item is scored separately for each member.

**What graders examine:** the `ai_log/` directory and its history.

## R4 — RAG Architecture Design (Elephant/Goldfish) (8 points)

**Assesses:** T3
**Criteria:**
- Bottom-up directory READMEs are present for all assigned directories and were committed before design work began.
- `docs/design-rag.md` was committed before any implementation code, and substantively addresses the citation data model, how an AI answer fits the existing thread model, the service architecture, and the ingestion-time/query-time configuration split.
- The document shows genuine, substantive revision after the Goldfish test, not cosmetic edits.
- The document is self-contained — specific enough to guide implementation without requiring the original Elephant conversation for context.

**What graders examine:** the committed READMEs, `docs/design-rag.md` and its revision history, and how closely the actual implementation follows it.

## R5 — Resource Ingestion (12 points)

**Assesses:** T4
**Criteria:**
- All four resource types (syllabus, schedule, course repositories, historical Q&A) can be registered and ingested by staff.
- URL-based ingestion is the primary path for syllabus/schedule/repositories, with file upload genuinely available as a fallback.
- Repository ingestion authenticates with an access token handled as a runtime secret, never hardcoded or stored as a CI/CD variable.
- Re-sync and ingestion-profile mechanisms work as specified: re-ingestion doesn't require deleting and re-adding a resource, and a new profile label produces a separate, coexisting copy of the ingested content.
- Chunking is genuinely type-appropriate across all four resource types.
- Every ingested chunk carries enough metadata to build a precise citation at answer time.

**What graders examine:** the running application's staff ingestion UI, the ingested content it produces, and the relevant code.

## R6 — Local RAG Pipeline (11 points)

**Assesses:** T5
**Criteria:**
- Ollama, Infinity, and ChromaDB run as part of the Docker Compose stack and are genuinely wired into the pipeline.
- A new question is embedded and matched via similarity search; below the chosen threshold, it is correctly left unanswered rather than forced.
- Retrieved context is assembled into a consistent, structured prompt with a system-level guardrail restricting the model to the provided context.
- A matched question receives an AI-generated answer posted as a new, clearly labeled post with a working citation link to its grounding source.
- Staff can accept an AI-generated answer through the existing acceptance mechanism, without the answer being gated behind pre-approval.

**What graders examine:** the running application's end-to-end behavior on both matched and unmatched questions, and the relevant code.

## R7 — RAG Configuration Comparison (12 points)

**Assesses:** T6
**Criteria:**
- `POST /api/courses/{course_id}/rag/compare` implements the specified contract exactly, including its dry-run guarantee.
- The pipeline is genuinely configurable along all five required axes (chunking, embedding model, similarity threshold, system prompt, generation model), each driven by an ingestion profile or request field as specified, not hardcoded.
- All five axes are evaluated as valid one-factor-at-a-time comparisons against a single, consistently-held baseline.
- `eval/report.json` and `eval/report.md` are committed and reproduce cleanly against the team's own running application. The re-run needs your deployment to be up when the grading run happens (see R10).
- The individual write-up's claims about which configuration performed better are consistent with the committed report.

**What graders examine:** the endpoint's live behavior, a fresh re-run of the provided harness against the running application compared to the committed report, and the write-up in each member's individual document.

## R8 — Integration Testing (8 points)

**Assesses:** T7
**Criteria:**
- The new capabilities from T4–T6 are covered by integration tests run against the live Docker stack.
- Tests assert on behavior, including error and access-control cases — not merely that endpoints respond.
- Pre-existing tests are intact and passing, neither deleted nor weakened.

**What graders examine:** the test suite and its results against the live stack.

## R9 — Light/Dark Theming (8 points)

**Assesses:** T8
**Criteria:**
- A semantic token layer is adopted consistently; hardcoded palette colors are gone outside the token definitions.
- Light and dark themes are complete across all three apps, including the new T4–T6 surfaces, with a working toggle that defaults to the OS preference and persists.
- Both themes meet the stated accessibility bar.
- The design is cohesive — consistent spacing, typography, and hierarchy; it looks deliberate, not just recolored.

**What graders examine:** the running application in both themes and the before/after screenshots in `docs/ui/`.

## R10 — Deployment (5 points)

**Assesses:** T9
**Criteria:**
- The application is reachable at the public URL recorded in `DEPLOYMENT_URL.txt` at the time of the grading run. Each run tests the live deployment when it runs, so a deployment that is down on the night of the due date (or of the late day you use) earns no credit for this check in that run.
- The course grader account (`grader`, created from `GRADER_PASSWORD_HASH`) can sign in to the deployed application.
- Deployment is automated through a `build`/`deploy` stage in `.gitlab-ci.yml`, not a manual step the team runs by hand, and that stage only runs on the `production` branch (not on every push).
- A `production` branch exists and its history is merge-only — every commit reachable there arrived via a merge request from `main`, never a direct push. Grading checks this from git history directly, not by trusting the GitLab UI setting alone, so keep the "Merge Commit" merge method for `main` → `production` merge requests (a squash merge changes the commit SHAs and will read as a direct push).
- No deployment credential is committed to the repository. A pipeline that needs one keeps it in a masked, protected GitLab CI/CD variable; the deployment guide's keyless sign-in needs none.

**What graders examine:** the live application at `DEPLOYMENT_URL.txt`'s URL, the `production` branch's commit history, and the pipeline's deploy-stage configuration.

## R11 — Individual Markdown Document (6 points)

**Assesses:** T10
**Criteria:**
- All five required sections are present and substantive.
- The document demonstrates genuine understanding of the codebase, the design process, and the RAG configuration findings, in the author's own words.
- The AI-usage account is honest and specific, with session logs referenced.

This item is scored separately for each member. A missing or placeholder document scores 0 for its author only.

**What graders examine:** each member's `docs/<netid>.md` and the logs it references.

## R12 — Equal Team Contribution (4 points)

**Assesses:** all tasks
**Criteria:**
- Contributions are roughly equal across the team, measured by lines changed and files touched (excluding `ai_log/` and lockfiles).
- A member at or above 30% of the team's work earns full points. Below that, points drop in proportion. Below 5%, the member earns 0.

This item is scored separately for each member. Commit under your own `<netid>@wisc.edu` identity so your work is credited to you.

**What graders examine:** commit history, authorship, and MR participation. Members with significantly less work lose points proportionally.

## R13 — TA Code Review (10 points)

**Assesses:** T11, and understanding of the entire submission
**Criteria:**
- Every member attends and participates.
- Each member can explain and justify **any** part of the submitted work — design decisions, how it was verified, where the AI helped and where it was wrong.
- Automated-grading concerns are raised with specific items and evidence.

**What graders examine:** your live discussion with the TA. This item is assessed by a person, on the spot.

## How team scores become individual scores

R3, R11, R12, R13 and half of R2 are scored for each member separately. The other items are team items, and every member who contributed a fair share (at least 30% of the work) receives the team score on them. A member below that share receives a reduced share of the team items, scaled by a contribution factor between 0 and 1. The automated report shows a provisional factor; your TA confirms or adjusts it at the code review, based on commits, merge requests, reviews, session logs and your discussion. If your teammate stops responding, tell your TA as early as possible, and request a TA review on any MR your teammate has not reviewed within 48 hours.

## Point Summary

| Item | Points |
|------|--------|
| R0 — Team Schedule | 3 |
| R1 — Version Control Usage | 5 |
| R2 — CI/CD Compliance | 4 |
| R3 — AI Logging Verification | 4 |
| R4 — RAG Architecture Design (Elephant/Goldfish) | 8 |
| R5 — Resource Ingestion | 12 |
| R6 — Local RAG Pipeline | 11 |
| R7 — RAG Configuration Comparison | 12 |
| R8 — Integration Testing | 8 |
| R9 — Light/Dark Theming | 8 |
| R10 — Deployment | 5 |
| R11 — Individual Markdown Document | 6 |
| R12 — Equal Team Contribution | 4 |
| R13 — TA Code Review | 10 |
| **Total** | **100** |

## Grading Notes

- **AI usage quality:** session logs are reviewed. Points are never deducted for using AI heavily — they are deducted for not using it *thoughtfully*. Copy-pasting output without understanding it, or never iterating on responses, are examples of poor usage.
- **R7 verification:** the comparison harness you were given (`eval/compare_harness.py`) is re-run, unmodified, against your team's own running application, and the fresh output is compared to what you committed. A write-up whose claims don't hold up against that re-run is a discrepancy to be prepared to explain at your TA code review, not a silent point loss you can't contest.
- **Provisional grades:** the automated grade report posted to your repository is provisional until the TA code review. Raising a specific, evidenced grading error at the review is the standard regrade path.
- **Formative feedback:** graders comment on git hygiene, testing strategy, RAG design reasoning, and AI usage. This feedback is formative — improvement across projects matters.

# Project 2: Buzzer — Rubric

This is the grading contract for Project 2. The project is worth **100 points**, graded by the course's automated grading pipeline together with course staff review. After grading, a report is posted to your repository; it is **provisional until your TA code review (R12)**, which is also where any automated-grading errors are corrected.

Each item below names the [instructions.md](instructions.md) task(s) it assesses.

## R1 — Version Control Usage (6 points)

**Assesses:** T1
**Criteria:**
- Independent features and fixes were developed on their own descriptively-named branches.
- Commits are atomic with clear, consistently-formatted messages.
- All work reached `main` through merge requests; history was never rewritten.

**What graders examine:** the repository's branch history, commit messages, and merge request records.

## R2 — CI/CD Compliance (4 points)

**Assesses:** T2
**Criteria:**
- Every merged MR passed the full pipeline.
- Every MR was approved by a teammate who did not author the code.
- The pipeline itself was not altered or bypassed to make checks pass.

**What graders examine:** pipeline and approval records on each merge request.

## R3 — AI Logging Verification (4 points)

**Assesses:** T0
**Criteria:**
- Every team member completed the logging verification before other work began.
- Session logs continue to appear throughout the project's development, for every member.

**What graders examine:** the `ai_log/` directory and its history.

## R4 — UI Restructuring (15 points)

**Assesses:** T4 (process: T3)
**Criteria:**
- Bottom-up directory READMEs are present for all assigned directories and were committed before design work.
- The design document was committed before implementation began and shows evidence of revision after the Goldfish test.
- All five host capabilities are functional in the host interface.
- Game–course attachment is enforced: a game is only reachable by hosts and players of its course.
- The admin interface is admin-first while retaining full access to host and player functionality.
- The changes work within the existing role and permission system rather than around it.

**What graders examine:** the committed READMEs and design document, the running application, and the relevant code changes.

## R5 — Integration Testing (10 points)

**Assesses:** T5
**Criteria:**
- The new capabilities from T4, T7, and T8 are covered by integration tests.
- Tests assert on behavior, including error and access-control cases — not merely that endpoints respond.
- Pre-existing tests are intact and passing.

**What graders examine:** the test suite and its results against the live stack.

## R6 — Quiz/Game JSON Files (4 points)

**Assesses:** T6
**Criteria:**
- Required number of games per member, meeting every coverage requirement in T6 (types, grading modes, classroom/party split, new question types).
- Every file imports cleanly; content is complete and appropriate to its audience.

**What graders examine:** the files in `sample_games/` and import behavior.

## R7 — New Question Types (13 points)

**Assesses:** T7
**Criteria:**
- Both question types are fully functional end-to-end: authorable by admins and hosts, playable by players, scored correctly, and exportable/importable.
- One type genuinely uses HTML Canvas as the player's interaction surface.
- Each type's scoring approach is deliberate and correctly implemented.
- The types integrate cleanly with the existing architecture rather than bypassing it.

**What graders examine:** the running application, the relevant code changes, and the accompanying tests and sample games.

## R8 — Image Support (11 points)

**Assesses:** T8
**Criteria:**
- Images are stored in the database, uploadable and manageable through the interface.
- Images function in question prompts, as question options, and on canvas-type questions.
- The feature holds up under realistic use (sensible handling of invalid input and repeated use).

**What graders examine:** the running application, the relevant code changes, and the accompanying tests.

## R9 — UI Look-and-Feel & Theming (9 points)

**Assesses:** T9
**Criteria:**
- A semantic token layer is adopted consistently; hardcoded palette colors are gone outside the token definitions.
- Light and dark themes are complete across all three apps, with a working toggle that defaults to the OS preference and persists.
- Both themes meet the stated accessibility bar.
- The design is cohesive — consistent spacing, typography, and hierarchy; it looks deliberate, not just recolored — including the new T7/T8 surfaces.

**What graders examine:** the running application in both themes and the before/after screenshots in `docs/ui/`.

## R10 — Individual Markdown Document (10 points)

**Assesses:** T10
**Criteria:**
- All four required sections are present and substantive.
- The document demonstrates genuine understanding of the codebase and data flow in the author's own words.
- The AI-usage account is honest and specific, with session logs referenced.

**What graders examine:** each member's `docs/<netid>.md` and the logs it references.

## R11 — Equal Team Contribution (4 points)

**Assesses:** all tasks
**Criteria:**
- Contributions are roughly equal across the team.

**What graders examine:** commit history, authorship, and MR participation. Members with significantly less work lose points proportionally.

## R12 — TA Code Review (10 points)

**Assesses:** T11, and understanding of the entire submission
**Criteria:**
- Every member attends and participates.
- Each member can explain and justify **any** part of the submitted work — design decisions, how it was verified, where the AI helped and where it was wrong.
- Automated-grading concerns are raised with specific items and evidence.

**What graders examine:** your live discussion with the TA. This item is assessed by a person, on the spot.

## Point Summary

| Item | Points |
|------|--------|
| R1 — Version Control Usage | 6 |
| R2 — CI/CD Compliance | 4 |
| R3 — AI Logging Verification | 4 |
| R4 — UI Restructuring | 15 |
| R5 — Integration Testing | 10 |
| R6 — Quiz/Game JSON Files | 4 |
| R7 — New Question Types | 13 |
| R8 — Image Support | 11 |
| R9 — UI Look-and-Feel & Theming | 9 |
| R10 — Individual Markdown Document | 10 |
| R11 — Equal Team Contribution | 4 |
| R12 — TA Code Review | 10 |
| **Total** | **100** |

## Grading Notes

- **AI usage quality:** session logs are reviewed. Points are never deducted for using AI heavily — they are deducted for not using it *thoughtfully*. Copy-pasting output without understanding it, or never iterating on responses, are examples of poor usage.
- **Provisional grades:** the automated grade report posted to your repository is provisional until the TA code review. Raising a specific, evidenced grading error at the review is the standard regrade path.
- **Formative feedback:** graders comment on git hygiene, testing strategy, and AI usage. This feedback is formative — improvement across projects matters.

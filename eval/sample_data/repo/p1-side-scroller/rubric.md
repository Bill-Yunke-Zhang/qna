# Project 1: Side-Scroller — Rubric

This is the grading contract for Project 1. The project is worth **100 points**, graded by the course's automated grading pipeline together with course staff review. After grading, a report is posted to your repository; it is **provisional until your TA code review (R10)**, which is also where any automated-grading errors are corrected.

Each item below names the [instructions.md](instructions.md) task(s) it assesses.

## R1 — Version Control Usage (10 points)

**Assesses:** T1
**Criteria:**
- Independent features and fixes were developed on their own descriptively-named branches.
- Commits are atomic with clear, consistently-formatted messages.
- All work reached `main` through merge requests; history was never rewritten.

**What graders examine:** the repository's branch history, commit messages, and merge request records.

## R2 — CI/CD Compliance (4 points)

**Assesses:** T2
**Criteria:**
- Every merged MR passed the full pipeline (the intentionally-red starting state is resolved by merging the T4 fix first).
- Every MR was approved by a teammate who did not author the code.
- The pipeline itself was not altered or bypassed to make checks pass.

**What graders examine:** pipeline and approval records on each merge request.

## R3 — AI Logging Verification (4 points)

**Assesses:** T0
**Criteria:**
- Every team member completed the logging verification before other work began.
- Session logs continue to appear throughout the project's development, for every member.

**What graders examine:** the `ai_log/` directory and its history.

## R4 — Parallax Bug Fix (14 points)

**Assesses:** T4 (process: T3)
**Criteria:**
- Parallax scrolling behaves correctly in the running game.
- The root cause was identified and fixed — not worked around.
- The change is localized and does not break unrelated functionality.
- The provided parallax tests pass unmodified.

**What graders examine:** the running game, the fix's code changes, and test results.

## R5 — New Features (20 points)

**Assesses:** T5
**Criteria:**
- Each member's feature is a genuine addition, not a constant tweak.
- Features integrate with the existing architecture rather than around it.
- Features work correctly in the running game.

**What graders examine:** the running game and each feature's code changes.

## R6 — Unit Testing (13 points)

**Assesses:** T6
**Criteria:**
- New tests cover the bug fix and every new feature.
- Tests assert on behavior, not just that code runs.
- Pre-existing tests are intact and passing.

**What graders examine:** the test suite and its results.

## R7 — Assets (10 points)

**Assesses:** T7
**Criteria:**
- All required asset categories are replaced or created and function in the running game.
- The maps are substantially reworked and a new map is added.
- The visual and audio style is cohesive — the assets feel like one game.

**What graders examine:** the running game and the asset files.

## R8 — Individual Markdown Document (8 points)

**Assesses:** T8 (and T3)
**Criteria:**
- All three required sections are present and substantive.
- The document demonstrates genuine understanding of the codebase and frame data-flow in the author's own words.
- The AI-usage account is honest and specific, with session logs referenced.

**What graders examine:** each member's `docs/<login>.md` and the logs it references.

## R9 — Equal Team Contribution (4 points)

**Assesses:** all tasks
**Criteria:**
- Contributions are roughly equal across the team.

**What graders examine:** commit history, authorship, and MR participation. Members with significantly less work lose points proportionally.

## R10 — Player Instructions Modal (3 points)

**Assesses:** T9
**Criteria:**
- The existing settings/menu modal (`m` key) includes player-facing text explaining how to play.
- That text covers every key needed to play the base game: left/right movement, jump, the menu toggle, and the fullscreen toggle.
- The instructions are visible in the running game, not just present in the source.

**What graders examine:** an automated check of the game's source for instructional text covering the required keys.

## R11 — TA Code Review (10 points)

**Assesses:** T10, and understanding of the entire submission
**Criteria:**
- Every member attends and participates.
- Each member can explain and justify **any** part of the submitted work — design decisions, how it was verified, where the AI helped and where it was wrong.
- Automated-grading concerns are raised with specific items and evidence.

**What graders examine:** your live discussion with the TA. This item is assessed by a person, on the spot.

## Point Summary

| Item | Points |
|------|--------|
| R1 — Version Control Usage | 10 |
| R2 — CI/CD Compliance | 4 |
| R3 — AI Logging Verification | 4 |
| R4 — Parallax Bug Fix | 14 |
| R5 — New Features | 20 |
| R6 — Unit Testing | 13 |
| R7 — Assets | 10 |
| R8 — Individual Markdown Document | 8 |
| R9 — Equal Team Contribution | 4 |
| R10 — Player Instructions Modal | 3 |
| R11 — TA Code Review | 10 |
| **Total** | **100** |

## Grading Notes

- **AI usage quality:** session logs are reviewed. Points are never deducted for using AI heavily — they are deducted for not using it *thoughtfully*. Copy-pasting output without understanding it, or never iterating on responses, are examples of poor usage.
- **Provisional grades:** the automated grade report posted to your repository is provisional until the TA code review. Raising a specific, evidenced grading error at the review is the standard regrade path.
- **Formative feedback:** graders comment on git hygiene, testing strategy, asset quality, and AI usage. This feedback is formative — improvement across projects matters.

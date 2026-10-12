# Project Schedule

## Team

| Name | NetID |
|---|---|
| Yuthika Goel | ygoel3 |
| Bill Zhang | yyzhang |

## Timeline

| Milestone | Tasks | Owner | Target date |
|---|---|---|---|
| READMEs for `backend/app/routers/`, `services/`, `models/` written and verified | T3 | ygoel3 | 2026-10-16 |
| READMEs for `backend/app/schemas/`, `common/` and `frontend/student/`, `staff/`, `admin/` written and verified | T3 | yyzhang | 2026-10-16 |
| Elephant session and first draft of `docs/design-rag.md` (citation model, AI post in thread model, services, config split) | T3 | both | 2026-10-19 |
| Goldfish test run and `docs/design-rag.md` revised and merged before any implementation | T3 | both | 2026-10-20 |
| Ollama, Infinity and ChromaDB added to Docker Compose and reachable from the backend | T5 | yyzhang | 2026-10-22 |
| Resource model, migrations and ingestion profiles (separate ChromaDB collection per profile) | T4 | ygoel3 | 2026-10-23 |
| Syllabus and schedule URL ingestion with HTML stripping, structural chunking and Text Fragment citations | T4 | ygoel3 | 2026-10-25 |
| Repository shallow clone with runtime-secret GitLab token; markdown (line range) and PDF (page) chunking | T4 | yyzhang | 2026-10-25 |
| Historical Q&A ingestion, file/zip upload fallback and re-sync | T4 | ygoel3, yyzhang | 2026-10-26 |
| Staff resource-management UI (register, upload, re-sync, profile selection) | T4 | yyzhang | 2026-10-26 |
| Semantic-color token layer and theme toggle (OS default, persisted) in all three apps | T8 | yyzhang | 2026-10-24 |
| Retrieval with similarity threshold and tagged prompt with baseline guardrail | T5 | yyzhang | 2026-10-28 |
| `AI` author role, AI answer posted with citation link and accepted via the existing mechanism | T5 | ygoel3 | 2026-10-28 |
| First end-to-end deploy to GCP VM: protected `production` branch, CI deploy stage, `DEPLOYMENT_URL.txt` | T9 | ygoel3 | 2026-10-28 |
| `POST /api/courses/{course_id}/rag/compare` dry-run endpoint matching the contract | T6 | ygoel3 | 2026-10-30 |
| Light and dark themes complete on all pages, including new RAG surfaces; WCAG AA contrast and focus states checked | T8 | ygoel3, yyzhang | 2026-10-31 |
| Integration tests for ingestion, profiles and access control | T7 | yyzhang | 2026-10-31 |
| Integration tests for RAG pipeline, AI answer posting and compare endpoint | T7 | ygoel3 | 2026-10-31 |
| Ingest `eval/sample_data/` under all profiles on the deployment; models pulled on the VM; `eval/configs.json` written | T6, T9 | yyzhang | 2026-11-01 |
| Harness run against the deployment; `eval/report.json` and `eval/report.md` committed | T6 | both | 2026-11-02 |
| Before/after theme screenshots committed to `docs/ui/` | T8 | yyzhang | 2026-11-02 |
| Individual document `docs/ygoel3.md` | T10 | ygoel3 | 2026-11-03 |
| Individual document `docs/yyzhang.md` | T10 | yyzhang | 2026-11-03 |
| Final deploy of `main` to `production`; deployment verified up and grader login checked | T9 | both | 2026-11-03 |

## Check-ins

| Date | What we will review |
|---|---|
| 2026-10-18 | READMEs merged; design doc draft ready for the Goldfish test |
| 2026-10-25 | Ingestion and Compose services progress; move dates that have slipped |
| 2026-10-29 | Pipeline end to end and first deploy working; plan the evaluation runs |
| 2026-11-02 | Report results, test coverage and what is left before the deadline |

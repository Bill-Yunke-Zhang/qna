# Project 3: QnA — Instructions

## Overview

This is a team-based project (teams of 2 students). Your team will use AI tools to add a Retrieval-Augmented Generation (RAG) feature to QnA, an existing Piazza-style course Q&A board, practicing professional software development workflows: version control, CI/CD pipelines, and AI-assisted development.

The starter app already works — students ask questions, staff and peers answer them, threads stay open until staff close them — but it has **no AI component at all**. Over the project your team will build one from scratch: an auto-responder that ingests real course resources (schedule, syllabus, course repositories, and the board's own Q&A history), retrieves relevant context for a new question, and — only when it's actually confident there's a good match — posts an AI-generated answer with a citation linking straight back to the source that grounded it. You'll also build a mechanism for comparing different RAG configurations against each other, so your design decisions are backed by evidence instead of guesses.

How your work is graded is defined in [rubric.md](rubric.md). Read it alongside this document: the tasks below say *what to do*; the rubric says *how it's assessed*.

## Do This First: Team Schedule (due Wednesday, October 14)

Before your team writes any code, agree on a schedule and commit it as `docs/schedule.md`. It says what will be done, who is responsible for each part, and by what date.

- **Due:** **Wednesday, October 14 at 11:59 PM**, one week after this project is released. By then the document must be on `main`, merged through an approved merge request like any other change (T1, T2). Open that merge request early, because a teammate has to approve it.
- **No late credit:** slip days do not apply to the schedule. If it is not on `main` by the due time, R0 scores 0.
- **What is graded:** only that the document is there on time and has the form below (R0 in [rubric.md](rubric.md)). Whether you keep to the schedule is not graded. Plans change, so update the document when yours does. The version on `main` at the due time is the one that is graded, and later edits never change that score.

`docs/schedule.md` has three sections, with these headings and these table columns:

```markdown
# Project Schedule

## Team

| Name | NetID |
|---|---|
| Ada Lovelace | alovelace |
| Alan Turing | aturing |

## Timeline

| Milestone | Tasks | Owner | Target date |
|---|---|---|---|
| Directory READMEs written and verified | T3 | alovelace, aturing | 2026-01-16 |
| `docs/design-rag.md` passes the Goldfish test | T3 | both | 2026-01-20 |
| Syllabus and schedule ingestion with citations | T4 | alovelace | 2026-01-24 |
| Ollama, Infinity and ChromaDB running in Compose | T5 | aturing | 2026-01-24 |
| ... | ... | ... | ... |

## Check-ins

| Date | What we will review |
|---|---|
| 2026-01-23 | Progress against the timeline; move dates that have slipped |
| 2026-01-30 | Progress against the timeline; what is left before the deadline |
```

The names, milestones and dates above are only an example. What each section must contain:

1. **Team** lists every team member's name and NetID.
2. **Timeline** is a table with the four columns shown: Milestone, Tasks, Owner, Target date.
   - **Milestone:** one row per milestone. A milestone is a piece of work small enough that you can tell when it is finished.
   - **Tasks:** the task number or numbers the milestone belongs to. Every task from T3 to T10 must appear in at least one row. A task can be split over several rows, and one row can name several tasks.
   - **Owner:** the NetID of the member responsible for getting the milestone done; others can still help. For shared work, list several NetIDs or write `both`. Every member must own at least one row.
   - **Target date:** the date you plan to finish the milestone, written `YYYY-MM-DD`.
3. **Check-ins** lists at least two dates on which the team will compare its progress with the timeline and update this document.

## Getting Started

> **Claim your GCP credit this week — don't wait for T9.** Deployment (T9) is the last task listed, but Part 1 of `deployment_instructions.md` (claiming and redeeming your free \$50 Google Cloud credit) takes a few minutes and depends on Google's own turnaround, which you don't control. The link for requesting your coupon is in Part 1; you will not get it by email. Redeem it in the first week: you cannot create your VM until the \$50 credit is in your account, and if something goes wrong with your coupon it can take days to sort out with Google. Do it now, in parallel with everything below, regardless of where your team is in the rest of the project. Skim the whole of `deployment_instructions.md` while you're at it, so the VM/branch-protection/CI-CD work later isn't a surprise.

1. Follow the **First-time setup** section of [README.md](README.md) — environment, JWT keys, Docker stack, migrations, frontend dev servers.
2. Run `python scripts/seed_demo.py` and explore both seeded courses (an AI-assisted software development course and a general chemistry course) as a student, as staff, and as admin, so you've seen the existing system work end to end before changing it.
3. **Unlike some of your earlier projects, there is no planted bug here and the CI pipeline starts green.** The codebase you're extending is fully functional; the challenge is entirely in designing and building a new AI feature well, not in fixing something broken.

## Required Reading

> **["Elephants, Goldfish and the New Golden Age of Software Engineering"](https://drensin.medium.com/elephants-goldfish-and-the-new-golden-age-of-software-engineering-c33641a48874)** — *Dave Rensin*
>
> The most dangerous mistake developers make with AI is skipping design and going straight to code. This article introduces two complementary AI session strategies — the **Elephant** (a long-running session that accumulates deep context) and the **Goldfish** (a fresh session with no memory, used to stress-test your design) — and argues that writing a detailed design document *before* touching any code is now the most important skill in software engineering. Task T3 requires you to follow this workflow.

Lectures 10–14 (and their pre-class readings — the RAG paper, Ollama and Infinity docs, ChromaDB docs) are your primary technical background for this project. This document doesn't repeat that reading list; if a term below is unfamiliar, it was covered there.

## Tasks

### T0 — Verify AI Session Logging

Before starting any development work, every team member must verify that Claude Code session logging is working in this repository:

1. Open a Claude Code session in the project directory.
2. Have a brief interaction (e.g., ask it to explain a file or how a system works).
3. Confirm a new log file was created and committed in `ai_log/` — the logging hook does this automatically.
4. Push your branch and confirm the log file appears on the remote.

Complete this before any other task. Your AI usage throughout the project is part of your grade, and unlogged sessions cannot be credited.

### T1 — Team Git Workflow

**Goal:** all work is tracked in Git using professional team practice, for the entire project.

| Requirement | Description |
|----------|-------------|
| Identity | Both team members commit under one consistent identity: set `git config user.email <your-netid>@wisc.edu` in this repository before your first commit. Work is attributed to you by commit email — commits under stray personal emails may not be credited. |
| Branching | Each independent feature or fix lives on its own branch. Branch names are descriptive (e.g., `feature/repo-ingestion`, `fix/citation-line-anchor`). |
| Commits | Commits are atomic (one logical change per commit) with clear, descriptive messages in a consistent format (e.g., imperative mood: "Add markdown line-range citation links"). |
| Merges | Branches are merged back to `main` via merge requests — never direct pushes. |
| No force pushes | History on `main` is never rewritten. |

### T2 — Keep the CI Pipeline Green

**Goal:** every merge request passes the existing CI/CD pipeline before merging. Do not bypass or modify the pipeline to make it pass artificially.

The pipeline (defined in `.gitlab-ci.yml`) runs on every merge request:

| Check | Command | Requirement |
|-------|---------|-------------|
| Python style | `ruff check backend/ scripts/` | No style or lint errors. Run `ruff format backend/ scripts/` locally to auto-fix before pushing. |
| Frontend types | `tsc --noEmit` (all three apps) | No TypeScript type errors. |
| Secret detection | GitLab built-in scan | No secrets or credentials committed — this matters more than usual this project, since you'll be handling a GitLab access token (T4) and API keys for the services you add (T5). |

**Merge request approval:** every MR must be reviewed and approved by your teammate. Authors may not approve their own MR.

Creating an MR does not ask anyone to review it. A **review request** is a separate step, and it is the MR author's job:

1. When you create an MR, add your teammate in the MR's **Reviewers** field (on the creation form, or in the right sidebar of an existing MR). GitLab notifies them and records the time of the request.
2. Your teammate then has 48 hours from that request to review the MR: approve it, or comment with the changes they want.
3. If your teammate has not reviewed it within those 48 hours, add a TA by name in the same **Reviewers** field. Any TA can approve, not only your own, so you can add one TA or several. A TA approval then counts, and the missed review is charged to your teammate (see R2 in [rubric.md](rubric.md)).

If you never request a review, the 48 hours are counted from when the MR was created, so check your team's open MRs regularly even without a notification.

### T3 — Design Your RAG Architecture Before You Code (Elephant/Goldfish)

**Goal:** follow the Elephant/Goldfish workflow from the required reading before writing any RAG implementation code. This is not optional — the design artifacts are deliverables, and the decisions below are substantial enough that designing them on the fly will cost you more time than it saves.

**Step 1 — Build codebase context bottom-up (the README trick).**
Divide the source directories below between your team and have each member generate a `README.md` for their assigned directories using AI. Work bottom-up: start at the deepest directories, have AI write a summary of what the code in that directory does, verify it yourself (5–10 minutes per directory), then roll up to the parent directory and repeat.

Directories to cover (divide between the two of you):
- `backend/app/routers/`, `backend/app/services/`, `backend/app/models/`, `backend/app/schemas/`, `backend/app/common/`
- One `README.md` per frontend app summarizing its structure: `frontend/student/`, `frontend/staff/`, `frontend/admin/`

Commit these to the repository — they become context you can hand to any future AI session, including your own Elephant session below.

**Step 2 — Load context with the Elephant.**
Start a Claude Code session (your Elephant) and use it to deeply explore the codebase, aided by the READMEs you just created. Ask how the `Question`/`Post` thread model works, how course-scoped `STUDENT`/`STAFF` access is enforced, how the accept/close mechanics work, and where you'll need to hook in. Push back, ask follow-up questions, and don't accept surface-level answers.

**Step 3 — Design, don't implement.**
Still in the same Elephant session, hold a 20–30 minute back-and-forth design conversation covering the full RAG feature. At minimum, your team needs to reach and defend a position on:

- **The citation data model.** Every ingested chunk needs enough metadata to produce a precise citation at answer time — a source URL, plus type-specific location data (line range for markdown, page number for PDFs, the matched text for a web-page Text Fragment link). What does this look like in your schema?
- **How an AI-generated answer fits into the existing thread model.** An AI answer needs to appear as a post in a question's thread, be clearly labeled, and be acceptable by staff through the same mechanism used for any other answer. There's no `author_role` value for this yet — you're extending the schema, not working around it.
- **The service architecture.** How Ollama (generation), Infinity (embeddings), and ChromaDB (vector store) get added to the Docker Compose stack and wired together.
- **A configuration-driven pipeline, behind a fixed contract.** T6 requires a `POST /api/courses/{course_id}/rag/compare` endpoint with a specific request/response shape (see T6) that a staff-provided harness calls to drive comparisons — that contract itself isn't a design decision, but the configuration surface behind it is. Two different kinds of configuration, handled two different ways: chunking configuration (which can vary per resource type) and embedding model choice are decided at *ingestion* time (T4's ingestion profiles), not accepted by this endpoint at all; similarity threshold, system-prompt text and generation model are accepted directly in every request, no re-ingestion needed. If chunking or embedding-model choice is hardcoded rather than driven by an ingestion profile, or the generation model is a constant instead of a per-request value, T6 will force a rewrite. Design both halves of this now, against the contract T6 already specifies.
- Ask the AI to challenge your assumptions, identify risks, and propose alternatives. Request a technical plan in prose and pseudocode — **not code**. Keep asking "what could go wrong?" and "what are we missing?"

**Step 4 — Write a design document.**
Produce `docs/design-rag.md` capturing: the problem being solved; the technical plan including every file that will be touched; alternatives considered and why they were rejected; step-by-step implementation details for each of the five points above. This document must be committed *before* any implementation code.

**Step 5 — Run the Goldfish test.**
Open a **brand new** AI session (no prior context). Give it only the design document. Ask it to explain what it learned, identify gaps or ambiguities, and critique the plan. Revise the design document based on what the Goldfish reveals. A design document that only makes sense in the context of your Elephant conversation is not ready.

**Step 6 — Implement against the document.**
Hand the finalized design document to AI with explicit instructions to follow it. Treat the document as the authoritative specification. If implementation reveals a flaw in the design, update the document first, then the code.

### T4 — Resource Ingestion

**Goal:** staff can register all four of the following resource types, and the system ingests their content with enough location detail to cite it precisely later.

| Resource | How it's provided | Content types | Citation must resolve to |
|---|---|---|---|
| Syllabus | Staff provides a URL; the app fetches it | A web page | The specific passage, via a [Text Fragment](https://developer.mozilla.org/en-US/docs/Web/URI/Reference/Fragment/Text_fragments) link (`#:~:text=...`) |
| Schedule | Staff provides a URL; the app fetches it | A web page | Same as above |
| Course repositories | Staff provides a repository URL; the app clones it | `.md` and `.pdf` files within the repo | The specific file **and location within it** — a line range for markdown, a page number for PDFs |
| Historical Q&A | Nothing to provide — reads the board's own accepted/closed threads directly | N/A | The thread itself |

Requirements:

- **URL-based ingestion is the primary path** for syllabus, schedule, and repositories — staff register a URL and the app fetches the content itself. Uploading a file directly (or a zip of files, for repositories) must remain available as a **fallback** for a resource that genuinely isn't reachable by URL.
- **Repository fetching uses a shallow clone**, authenticated with a GitLab access token that staff provide and the app stores as a runtime secret (an environment variable, not hardcoded, and not a GitLab CI/CD variable — this secret is used by the running application, not the pipeline).
- **Re-sync**: staff can re-trigger ingestion on an already-registered URL to pick up changes to the source (a syllabus or schedule updates over the semester; this must not require deleting and re-adding the resource).
- **Ingestion profiles**: re-ingestion can target a named profile instead of always overwriting the default — ingesting under a new profile label with a different chunking configuration (which can vary per resource type) or embedding model produces a separate copy of the ingested content (a separate ChromaDB collection) rather than replacing what's already there, so multiple configurations can coexist. T6 depends on this: chunking configuration and embedding model are decided when content is ingested, not when a question is asked, so comparing them means ingesting more than once, not swapping a parameter per-query.
- **Type-appropriate chunking**: don't split historical Q&A pairs (they're already atomic); chunk the syllabus/schedule pages by their own structure after stripping HTML markup; chunk markdown files by section boundary; use a sliding-window chunker with configurable overlap for PDFs and any other unstructured long passage.
- Every ingested chunk carries enough metadata to build the citation link described in the table above at answer time — this is the citation data model from your T3 design doc.

### T5 — Local RAG Pipeline

**Goal:** a new question that closely matches ingested content gets a grounded, cited AI answer; a question with no good match gets left alone for a human, exactly like the rest of this board already works.

| Requirement | Description |
|------------|-------------|
| Services | Ollama (generation), Infinity (embeddings), and ChromaDB (vector store) run as Docker Compose services alongside the existing stack. |
| Retrieval | A new question is embedded and matched against ingested content via similarity search. Below your chosen similarity threshold, the question is left unanswered — the system must never force a low-confidence guess. |
| Prompt construction | Retrieved context is wrapped in consistent structural tags per resource type, with a system-level guardrail instructing the model to answer only from the provided context. |
| Posting the answer | A matched question gets an AI-generated answer posted immediately as a new post in its thread, clearly labeled as AI-generated, including a citation link (per T4's requirements) to the source that grounded it. |
| Staff acceptance | Staff can mark an AI-generated answer accepted through the same mechanism already used for any other answer — this is not a separate code path, and it is not a pre-approval gate: the AI answer is visible before any staff review. |

### T6 — RAG Configuration Comparison

**Goal:** demonstrate, with evidence, which of several RAG configurations actually works better on this board's content — not just that you built *a* pipeline, but that you can reason about *why* it's configured the way it is.

Your pipeline must be **configurable** along all five of the following axes, and you must evaluate each one as a **controlled, one-factor-at-a-time comparison**: define a single fixed baseline configuration, vary exactly one axis away from it, measure, then repeat per axis. Every comparison holds the other four axes at baseline — this isolates each axis's effect instead of confounding several changes at once. The tradeoff: it won't surface *interaction effects* between axes (e.g., whether type-tailored chunking matters more paired with one embedding model than another) — a full factorial across five axes would be far more Docker/CPU time than this assignment calls for, so that's an accepted limitation, not an oversight. Say so plainly in your write-up (T10) rather than implying your sweep is exhaustive.

**Your baseline configuration** — fixed for every comparison except the one axis being tested:
- Chunking: the `sliding-window` profile (below)
- Embedding model: `sentence-transformers/all-MiniLM-L6-v2`
- Similarity threshold: your team's chosen default
- System prompt: T5's required baseline guardrail, verbatim (below)
- Generation model: `qwen2.5:1.5b`, served by Ollama

The five axes, and what each one-axis comparison looks like:

1. **Chunking configuration — one naive technique vs. per-type choices.** T4 already requires *structure-aware* splitting appropriate to each type (by header for markdown, atomic pairs for historical Q&A — which never needs what follows, by section for the rest) — that's a baseline, not something to compare. What's comparable is the **fallback chunker** applied within an oversized section or long passage, on top of that structural splitting. Build exactly two ingestion profiles, both using the baseline embedding model so only chunking differs:
   - **`sliding-window`** (your baseline) — a single fixed-size sliding-window chunker (a target token count per chunk, `chunk_size`, and a trailing-token overlap between consecutive chunks, `chunk_overlap`), applied identically to every resource type's oversized content. No per-type variation at all — this is your naive baseline.
   - **`type-tailored`** — for each resource type that actually needs a fallback chunker, choose whichever approach fits that type's content best, and be ready to justify the choice in your T10 write-up. Your options per type: a differently-sized/overlapped sliding window, or **semantic chunking** — embed small units (sentences or small sentence groups), merge adjacent units into a chunk while their similarity stays above a threshold, and start a new chunk when it drops. If you use semantic chunking for a type, it needs a **maximum cap** on chunk size (a sliding window has no such cap); if a semantically-coherent span would exceed that cap before a natural boundary appears, don't truncate it — recursively apply a fixed-size sliding-window chunker (with its own overlap) to just that oversized span. You don't have to pick a different approach for every type — but every choice needs a reason tied to what that type's content actually looks like (a dense PDF slide deck vs. a prose-heavy web page, say), not a default you didn't reconsider.

   Query both profiles at your default threshold and the baseline guardrail prompt — the point of this comparison is showing whether reasoning about chunking per data type beats one naive technique applied everywhere, isolated from any other axis.
2. **Embedding model choice.** Every one of these models is a full transformer stack — several self-attention/feedforward layers deep — before pooling ever happens; pooling doesn't replace attention or reduce how much computation runs, it's just the last step that collapses a sequence of already-contextualized per-token vectors into one fixed-size vector. What actually differs between the models below is the *training objective* and *attention pattern* baked in during pretraining (bidirectional representation learning vs. causal next-token prediction), which is what makes one pooling readout appropriate and another not. Ingest a third profile — `sliding-window` chunking (same as baseline, so only the model differs) with:
   - `Alibaba-NLP/gte-Qwen2-1.5B-instruct` — built on a causal, next-token-prediction-style decoder backbone (the same architecture family as the Qwen2.5 model your pipeline already uses for generation), read out via **last-token pooling**, since under causal attention only the final token has attended to the whole passage. It's much larger than the baseline's MiniLM (~1.5B vs. ~22M parameters) — that cost is itself part of what this comparison should surface, not a bug in the assignment. *(Verify this exact model ID against its current Hugging Face model card before you build against it — check it actually exists and still describes itself this way.)*

   Query this profile at your default threshold and the baseline guardrail prompt, and compare it against your baseline profile (`sliding-window` chunking + MiniLM). If you explore this axis further, add a fourth profile — `sliding-window` chunking + any embedding model of comparable practical size (roughly 20M–200M parameters, so it stays usable on a CPU-only machine — the item above is a deliberate, size-costly exception, not the norm) that uses a pooling mechanism other than mean or last-token. **CLS-token pooling** is the common third option (e.g., `BAAI/bge-small-en-v1.5`) — your choice, any model Infinity can serve. Compare it against the same baseline.
3. **Retrieval similarity threshold.** Query your baseline profile (`sliding-window` + MiniLM) with the baseline guardrail prompt, at your default threshold vs. a meaningfully different one — a conservative/high threshold against a permissive/low one, so the comparison shows an actual behavioral difference (more unanswered questions vs. more — possibly wrong — answers given), not two numbers that happen to produce identical results.
4. **System-prompt hardening.** T5 already requires a baseline guardrail: *"Only use the information provided in the tagged context to answer questions. If the context does not contain enough information to answer, say so rather than guessing."* Query your baseline profile at your default threshold, comparing that guardrail against **at least two alternative prompts your team writes**, each expressing a real, different hardening strategy (e.g., explicitly resisting instructions embedded inside retrieved content, requiring every claim to trace to a specific passage, refusing to speculate beyond the literal text). Every variant you compare is passed to `/rag/compare` as literal prompt text (see the request body below) — there's no fixed enum of hardening levels to hit.
5. **Generation model.** The model that writes the answer is a separate choice from the model that embeds text for retrieval. The two don't have to match, or even come from the same family: the generator only ever sees the retrieved text, never the vectors, so any ingestion profile works with any generation model. Query your baseline profile at your default threshold with the baseline guardrail prompt, comparing `qwen2.5:1.5b` against **at least one other model served by Ollama** that your team chooses and can justify. Two choices that each teach something different: a larger model from the same family (e.g., `qwen2.5:3b`) isolates the effect of size, and a model of similar size from a different family (e.g., `llama3.2:1b`, `gemma3:1b`) isolates the effect of the model itself. *(Verify any tag against the current Ollama library before you build against it.)* Three constraints:
   - **It has to run on your CPU-only VM.** Stay at or below roughly 4B parameters at 4-bit quantization; anything larger takes minutes per answer on 4 vCPUs. That cost is part of what this comparison should surface, so report it.
   - **It has to be pulled on your deployed VM, not just your laptop.** `/rag/compare` never pulls a model, and grading re-runs your comparison against the deployment (see below).
   - **This axis changes nothing about retrieval.** The same chunks come back, so retrieval hit rate and no-match accuracy will equal baseline by construction. The whole difference is in the answers and in generation time and CPU, so you judge it by reading the answers side by side. The same is true of axis 4.

**Axes 1 and 2 aren't adjustable the same way as 3, 4 and 5, and your endpoint contract has to reflect that.** Chunking configuration and embedding model choice are decided when content is *ingested* — they determine what gets computed and stored in ChromaDB, so comparing them means ingesting the same sample data more than once, under different **ingestion profiles** (T4), not passing a different value per question. Similarity threshold, system-prompt text and generation model are genuinely decided per question, with no re-ingestion needed. Design your pipeline around that distinction — don't build an endpoint that pretends you can swap an embedding model after the fact.

**A fixed API contract, so the provided harness can drive any team's implementation.** Unlike the rest of this project, the shape of this one endpoint is not a design decision — it's an interop requirement the harness depends on. Implement exactly this:

`POST /api/courses/{course_id}/rag/compare` — staff/admin-only (reuse your existing staff auth). This is a **dry run**: it must not create any `Question` or `Post` row. The harness calls it once per (question × configuration) combination across the whole ground-truth set — the baseline configuration plus each one-axis comparison from `configs.json` — so nothing about a compare call may be persisted to the board.

Request body:
```json
{
  "question": "free-text question — not necessarily tied to any existing Question in the board",
  "ingestion_profile": "baseline",
  "similarity_threshold": 0.75,
  "system_prompt": "Only use the information provided in the tagged context to answer questions. If the context does not contain enough information to answer, say so rather than guessing.",
  "generation_model": "qwen2.5:1.5b"
}
```

`ingestion_profile` selects which already-ingested profile (T4) to query — it must already exist; this endpoint never triggers ingestion itself. `similarity_threshold`, `system_prompt` and `generation_model` are applied live to that request — `system_prompt` is the literal text to use for that call, not a label the endpoint looks up. `generation_model` is the Ollama model tag that generates the answer for that call. It must already be pulled; if it isn't available, respond with a 4xx error instead of silently falling back to another model, because a silent fallback would make two different runs look like a comparison when they are the same model.

Response body:
```json
{
  "matched": true,
  "retrieved_chunks": [
    {"resource_type": "syllabus", "source_url": "...", "similarity_score": 0.83, "text": "..."}
  ],
  "answer": "string, or null if matched is false",
  "metrics": {
    "embedding_time_ms": 120,
    "retrieval_time_ms": 15,
    "generation_time_ms": 900,
    "cpu_percent": 45.2
  }
}
```

`retrieved_chunks` and its `source_url` per chunk are what the harness checks against the ground truth's expected source for retrieval accuracy; `answer` is what you and the harness compare against the expected answer for response quality; `metrics` is measured directly for resource cost.

Using the ground-truth question set and comparison-harness skeleton provided in [`eval/`](eval/README.md), your team must:

1. **Ingest `eval/sample_data/`** into a course, once per ingestion-time profile your one-axis comparisons need (T4) — this part is manual, through your own staff UI, not something the harness does for you. At minimum: `sliding-window` chunking + MiniLM (your baseline), `type-tailored` chunking + MiniLM (the chunking comparison), and `sliding-window` chunking + your alternate embedding model (the embedding-model comparison).
2. **Copy `eval/configs.example.json` to `eval/configs.json`.** Define your `baseline` (ingestion profile, similarity threshold, system prompt, generation model) once, then list one `comparisons` entry per axis — each overriding exactly one field away from baseline. Set `course_id`.
3. **Run the harness** — it queries the baseline once, then each comparison entry as baseline-with-one-override; it never runs a blind cross product of profiles × query variants.
4. **Commit `eval/report.json` and `eval/report.md`** — this is required evidence, not a scratch file. Do not gitignore it.
5. Document all **five one-axis comparisons**, measured along all three of: **retrieval accuracy** against the provided ground truth, **final response quality**, and **resource cost** (CPU usage and runtime) — write up which side of each comparison performed better, and why you think that is, in your individual document (T10). Then rank the axes: which single change improved answer quality the most, and what did it cost? Don't assume the answer going in. A generator can't answer from a passage that retrieval never returned, and a weak generator can garble a passage that retrieval found; your report shows which of those limits your pipeline actually hits.

**Your committed report will be independently reproduced.** Grading re-runs the unmodified `eval/compare_harness.py`, with your own committed `eval/configs.json`, against your team's **deployed** application (T9, at the URL in `DEPLOYMENT_URL.txt`) — not a fresh local boot with nothing ingested — and compares the fresh output to what you submitted and wrote up. A write-up whose claims don't hold up against a clean re-run of your own harness against your own system is exactly the kind of thing that gets raised at your TA code review (T11) — be prepared to explain any discrepancy.

The full automated evaluation harness (LLM-as-judge scoring — Faithfulness, Answer Relevance, Context Recall) is **not required**. If your team wants to go further and replace manual judgment with automated scoring along those lines, that's a good extension, not a baseline expectation.

### T7 — Integration Testing

**Goal:** the new capabilities from T4–T6 are covered by integration tests that run against the live Docker stack, using the existing pytest framework in `tests/integration/`.

- Tests verify behavior, not just that endpoints respond.
- Cover both success paths and relevant error/access-control cases.
- Existing tests must not be deleted or weakened.

### T8 — Light/Dark Theming

**Goal:** the starter's UI is functional but visually plain. Add a deliberate visual design built on a proper theme system, offering both a **light** and a **dark** theme, across all three apps (student, staff, admin).

| Requirement | Description |
|------------|-------------|
| Design tokens | Introduce a semantic color-token layer (CSS variables mapped into each app's Tailwind theme — e.g., `surface`, `text-primary`, `accent`, `danger`). Components consume tokens; raw palette utilities are eliminated outside the token definitions. |
| Light and dark themes | Both themes fully cover all three apps — every page usable and intentional-looking in each. |
| Toggle and persistence | Each app has a visible theme toggle. First visit follows the OS preference (`prefers-color-scheme`); the choice persists across reloads. |
| Accessibility | Text meets WCAG 2.1 AA contrast (4.5:1 for body text) in both themes; interactive elements have visible focus states. |
| Evidence | Before/after screenshots of key screens in both themes committed to `docs/ui/` and referenced in your individual markdown document (T10). |

Your new surfaces from T4–T6 (resource management, citation links, comparison results) must be themed too.

### T9 — Deployment

**Goal:** your application runs somewhere other than your own laptop, reachable at a public URL, and getting it there is automated.

| Requirement | Description |
|------------|-------------|
| Reachable | Your deployed application is reachable at a public URL **whenever a grading run tests it**. Each grading run checks the live deployment at the moment it runs: it does not remember an earlier success. If your VM is stopped or your application is down at that moment, that run gives no credit for the deployment checks (R10) and cannot reproduce your T6 comparison (R7). So have it up and running on the night of the due date, when the main grading run happens. If you submit late with slip days, keep it running on those nights too, because the run that grades your late submission tests the deployment again. A preliminary run two nights before the due date also tests it, if you want that early feedback. |
| Protected branch | Your repository has a protected `production` branch: no direct pushes allowed, only merges via merge request from `main`. |
| Automated | A `build`/`deploy` stage in `.gitlab-ci.yml`, gated to run only when `$CI_COMMIT_BRANCH == "production"`, deploys your application — merging a reviewed merge request into `production` results in the live deployment being updated automatically, not a manual step your team runs by hand. |
| Secrets | No credential is ever committed to the repository. The deployment guide's deploy stage signs in to Google Cloud without any stored secret, so if you follow it there is nothing to store. If your team's pipeline does need a credential (an SSH key, API key or access token), it goes in a masked, protected GitLab CI/CD variable. Production passwords and keys live only in the `.env` file on your VM. |
| Grader access | The course grader account can sign in to your deployed application. The starter creates it at startup: an admin user named `grader`, built from `GRADER_PASSWORD_HASH` in `.env.template`. Only course staff know its password. Keep that line unchanged in the `.env` on your VM, and don't remove the startup code that reads it. Grading signs in with this account to check your deployment and to re-run your T6 comparison. |
| Recorded URL | Your public URL is committed in a single line, and nothing else, in `DEPLOYMENT_URL.txt` at the repo root — this is where grading looks for it, for this task and for T6. |

> **Deployment target:** your own GCP VM, provisioned with your course-provided education credit. Follow `deployment_instructions.md` at the repo root for the full walkthrough — claiming the credit, provisioning the VM, deploying from the protected `production` branch, and wiring up the CI/CD deploy stage.
>
> **Deploy early.** Every team's pipelines share one course runner, which is busiest in the last day or two before the deadline: jobs queue, and builds fail more often for reasons unrelated to your code. Get one deploy working end to end several days before the deadline, so that later deploys are only updates. Part 9 of `deployment_instructions.md` explains how to read a failed pipeline, tell a load problem from a bug in your project, and retry.
>
> **Watch your credit.** A running VM costs about \$3.50 a day, and your \$50 also has to cover Project 4 and the Final Project. Stop the VM whenever you finish working, keep it running through the grading window, and delete it after your TA code review. Part 1 of `deployment_instructions.md` has a budget that fits, and Part 10 has the clean-up steps.

### T10 — Individual Markdown Document

**Goal:** each team member creates a personal `docs/<your-netid>.md` with the following sections, each with substantive explanations (not one-liners):

**Repository and Codebase Organization** — describe in your own words how the repository is organized, how the major components relate, and how a question flows through the system from being asked to (possibly) receiving an AI-generated, cited answer. Reference the directory READMEs your team produced — which you wrote, and what you learned writing them.

**Design Process (Elephant/Goldfish)** — your experience following T3: how the Elephant session produced the design document, what the Goldfish revealed that the Elephant missed, and how the document changed as a result. Link your `docs/design-rag.md`. Reflect on whether the process changed how you approached implementation.

**RAG Configuration Findings** — summarize what T6 taught you: which configurations you compared, what the evidence showed, which single change made the biggest difference to answer quality and at what cost, and whether the result matched your intuition going in.

**AI Tools Used** — every AI tool you used. For each: a reference to the session log, what you asked and how you used the output, and an honest assessment of where it helped and where it fell short.

> **Session log note:** Claude Code sessions are logged automatically to `ai_log/`. For other AI tools (ChatGPT, Gemini, Copilot, etc.), export your conversation to a file in `docs/` (e.g., `docs/<your-netid>-chatgpt-session.md`) and reference it here.

**Best Practices Learned** — what you learned about professional software development from this project: RAG system design, evaluating AI-generated output, working with local model-serving tools, or effective AI use.

### T11 — TA Code Review

After the deadline, your team will attend a code review with a TA.

1. Every team member attends and participates.
2. Be prepared to walk through **any** part of your team's submission — explain what it does, why it was designed that way, and how you verified it works. You are expected to demonstrate knowledge of the work you submitted, whether you typed it or an AI did.
3. Review your grade report before the meeting. If the automated grading contains any errors, **this is where you raise and address them** — bring the specific rubric item, what the report says, and the evidence it got wrong.

## Submission

By the deadline, all of the following must be true:

- [ ] All work is merged to `main` via approved merge requests.
- [ ] `docs/schedule.md` reached `main` within the first week (see Do This First).
- [ ] `docs/design-rag.md` is present on `main`, committed before the implementation it describes.
- [ ] `eval/report.json` and `eval/report.md` are present on `main` (T6).
- [ ] Each member's `docs/<your-netid>.md` is present on `main`.
- [ ] Theme screenshots are in `docs/ui/` on `main`.
- [ ] Claude Code session logs are in `ai_log/`; logs from any other AI tools are in `docs/` and referenced from your individual document.
- [ ] Your application is deployed and reachable, with its URL in `DEPLOYMENT_URL.txt` at the repo root (T9).
- [ ] No force-pushes to `main` after the deadline.
- [ ] Your team has scheduled its TA code review (T11).

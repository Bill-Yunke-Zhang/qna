# Bill Zhang (yyzhang): Project 3 individual document

## 1. Repository and Codebase Organization

The repository is a Piazza-style course board with three single-page apps in
front of one FastAPI backend. RAG was added on the backend as a set of
services next to the existing ones, rather than as a separate system.

- **`backend/app/`** has four layers:
  - `routers/` is the HTTP edge: paths, auth dependencies, status codes.
  - `schemas/` holds the Pydantic request and response shapes.
  - `services/` holds the business logic, which never touches HTTP.
  - `models/` holds the SQLAlchemy tables, with Alembic migrations in
    `backend/alembic/`.
  - `common/` has the shared pieces: auth dependencies such as
    `require_course_staff`, the exception types and their JSON handler, and
    upload helpers.
- **`backend/app/services/rag/`** is the RAG part:
  - `clients.py` is the only code that talks to Ollama, Infinity and ChromaDB.
  - `fetchers.py` fetches web pages with the SSRF check, reads uploads and
    zips, shallow-clones repos and extracts PDF text.
  - `chunking.py` does the structural splitting (web pages and markdown by
    heading, PDFs by page) and the profiles' fallback chunkers.
  - `profiles.py` is the fixed list of ingestion profiles.
  - `ingestion.py` is the background sync task.
  - `pipeline.py` and `prompt.py` handle retrieval and generation.
  - `compare.py` and `health.py` serve the eval endpoint and the readiness
    check.
- **`frontend/{student,staff,admin}/`** are three copies of the same React +
  Vite + Tailwind skeleton. Each has its own `lib/api.ts`, which sets the
  `X-App-Surface` header, and its own `components/ui/`. There's no shared
  package, so a change to a common file is made three times. That's why the
  T8 token layer exists in three identical copies.
- **Docker Compose** runs MySQL, Redis, the backend and nginx, plus the three
  RAG services: Ollama, Infinity and ChromaDB. All six have named volumes, so
  a redeploy keeps ingested collections and downloaded models.
  `docker-compose.prod.yml` is the VM's version, built and deployed by CI
  from the protected `production` branch.

**How a question flows to a cited AI answer:**

1. A student posts a question from the student app. `routers/qa.py`
   `create_question` commits the row and returns 201 first, so a RAG
   problem can never stop a question from being posted.
2. `create_question` then schedules `ai_answer_service.answer_question` as
   a background task. It skips if live answering is off, if too many
   answers are already waiting, or if the eval harness ran within the last
   minute.
3. It then calls `pipeline.run()` with the live settings (`RAG_LIVE_*`).
   `run()` does these steps in order:
   1. It checks everything first: the profile exists, the model is pulled,
      the course has a collection built with the current profile
      definition, and there is a current sync. A bad configuration is an
      error, never a silent "no match".
   2. It embeds the title and body with the collection's own embedding model
      (with the profile's query prefix) through Infinity.
   3. It queries the course's ChromaDB collection for the top 5 chunks of
      the current sync.
   4. It drops past answers that have since been un-accepted, and keeps the
      chunks at or above the similarity threshold.
   5. It builds a tagged prompt and generates with Ollama through a gate
      that runs one generation at a time. Compare calls go before live ones.
4. If nothing passes the threshold, if the answer was cut off, or if it's a
   refusal, nothing is posted, and the question waits for a person as it
   always did.
5. Otherwise the task opens a fresh DB session and re-checks the thread.
   If it's still open, with no AI, accepted or staff answer, it posts an
   ordinary `ANSWER` with `author_role='AI'` and up to three citations. The
   existing "Mark verified" flow then applies to it unchanged.
6. The student app polls the thread right after asking and shows the
   answer with its sources. Each source links into the syllabus with a Text
   Fragment, to a line range in the repo (`?plain=1#L12-L30`), to a PDF
   page (`#page=4`), or to the past thread.

**Directory READMEs.** In T3 I wrote five READMEs:
[`backend/app/schemas/`](../backend/app/schemas/README.md),
[`backend/app/common/`](../backend/app/common/README.md), and the three
frontend apps ([`student`](../frontend/student/README.md),
[`staff`](../frontend/staff/README.md),
[`admin`](../frontend/admin/README.md)). Yuthika wrote `routers/`,
`services/` and `models/`. I've kept mine updated as features landed: the
staff README covers the Resources page and theming.

Writing them taught me two things that mattered later:

- **The `X-App-Surface` header can only restrict, never grant.** A staff
  member using the student app is treated as a student, and the effective
  role, not the account's role, is what gets stored as `author_role`. That
  shaped the integration tests I wrote for resource access in T7.
- **The three frontends are copies, not a shared library.** I knew from the
  start that the T8 token layer had to be replicated in each app, and that
  "raw palette colors are gone" had to be checked in all three.

## 2. Design Process (Elephant/Goldfish)

The design is [`docs/design-rag.md`](design-rag.md). Yuthika ran the
Elephant sessions that produced the first draft (`3009900`, 10/17), with
the decisions we'd agreed on beforehand:

- the citation model, with two URLs per chunk;
- the AI post as an ordinary answer with a nullable author;
- the service layout;
- the split between ingestion-time and query-time settings.

My part was reviewing the draft before the Goldfish run. My review checked
every claim that touched existing code (delete_user, MySQL 8.0, nginx's
50 MB limit, the seeded threads, deployment Part 7). It raised six points,
which were addressed in `c7ef944`. The ones that changed the design:

- **Upload the eval pages as their real types.** The draft zipped all of
  `eval/sample_data/`, which would have chunked the syllabus and schedule as
  repo files and hidden the very difference the `type-tailored` profile is
  supposed to show. §3.2 now uploads them as single-file SYLLABUS and
  SCHEDULE resources.
- **Use the contract's names everywhere.** The draft used internal metric
  names (`embedding_ms`) that differed from the compare contract
  (`embedding_time_ms`). Since the harness reads metrics with
  `.get(name, 0)`, a mismatch would silently report zeros.
- **Name a starting threshold, and how to pick it.** I pointed out that
  MiniLM cosine scores tend to sit well below the example's 0.65. T6 bore
  this out: correct sources score as low as 0.44.
- **Commit the pre-Goldfish draft as its own commit**, so the revision
  history shows real change.

Then came five Goldfish runs (`3b2475a` … `83f1ab4`). A fresh session with
none of our context read the document as written and tried to implement
from it. What it found was mostly what an author can't see:

- **Places the doc assumed something it never said.** The compare
  endpoint's 180 s harness timeout wasn't bounded end to end. That led to
  the total budget from arrival and the shared generation gate that serves
  compare calls first. The doc records the rejected alternatives: returning
  504, and a deadline on streaming alone.
- **Unclear rules.** "Answer only students' questions" turned out to be
  undefined, because the effective role isn't stored. It became "answer
  every new question".
- **Over-engineering.** A Redis lock for the sync registry, and a staff
  "rebuild profile" action, were both rejected with reasons.

Every rejected option is kept in the doc as *"Rejected (Goldfish run N)"*,
so the reasoning survives. Later I found one more gap in my review of the
final draft: un-accepting and then re-accepting an answer would leave Q&A
content hashing to the old value, so re-index would skip it. The fix is to
clear `content_hash` on un-accept (§4.6).

**Did it change how I implemented?** Yes, in a concrete way: I could build
my parts against the document without asking anyone. The resource
endpoints, the Resources page, repo ingestion and `pipeline.run()` were
each written straight from their sections, and each MR description cites
the section it implements. Where the code had to differ, I added an
*"As built"* note to the doc, for example how repos are cloned without a
checkout. The document stayed true. The process also made me write down
*why*, which made reviews faster in both directions.

## 3. RAG Configuration Findings

`eval/configs.json` has one baseline plus eight one-axis comparisons:

| Run | What changes |
|---|---|
| baseline | `sliding-window` / MiniLM / threshold 0.40 / T5 guardrail / `qwen2.5:1.5b` |
| type-tailored-chunking | semantic chunking for prose, one chunk per PDF page |
| gte-qwen2-last-token | gte-Qwen2-1.5B embeddings (causal backbone, last-token pooling) |
| bge-small-cls | bge-small-en-v1.5 embeddings (CLS pooling) |
| threshold-0.55-conservative | threshold 0.55 |
| untrusted-context-prompt | retrieved text is data, not instructions; no outside knowledge |
| quote-grounded-prompt | every claim tied to a named passage; no inferring numbers or dates |
| qwen2.5-3b-larger | same family, about 2× parameters |
| llama3.2-1b-other-family | different family, similar size |

**Picking the threshold from data.** Before any harness run, I ran the 14
questions plus 10 held-out off-topic questions against a local stack and
logged the top similarity of each. On MiniLM, correct sources scored 0.44
to 0.66, and off-topic questions scored 0.17 to 0.47, with one at 0.54
("late policy for Math 340", which shares the syllabus's vocabulary). No
threshold separates the two groups cleanly. 0.40 answers all 13 answerable
questions and refuses q14. 0.45 would already refuse q05, whose correct
source is ranked first at 0.44. So the threshold axis is really a trade:
refusing more vs. answering off-topic more.

**Local results** (MiniLM, `qwen2.5:1.5b`): the baseline and both hardened
prompts answer all 13 answerable questions and refuse q14, with retrieval
hits on 10 of 13. q12 and q13 are seeded in-app threads the harness can't
score. q06 is a real miss: under `sliding-window`, the right file isn't in
the top 5. On q06 all three prompts produced a confident, wrong answer, the
quote-grounded one included. Prompt wording doesn't rescue a retrieval miss.

**Deployment results** (`eval/report.md`; the production VM, 4 vCPU and 16
GB, on 10/24). Yuthika ran the harness: 126 calls, all 200. Hit rates are
out of 13, so q12 and q13, which the harness can't score, cost every run
2/13.

| Run | Hit rate | No-match | Avg wall-clock |
|---|---|---|---|
| baseline | 77% | 100% | 20.6 s |
| type-tailored-chunking | 85% | 100% | 11.9 s |
| gte-qwen2-last-token | 85% | 100% | 26.9 s |
| bge-small-cls | 85% | **0%** | 23.9 s |
| threshold-0.55-conservative | 38% | 100% | 3.8 s |
| untrusted-context-prompt | 77% | 100% | 20.0 s |
| quote-grounded-prompt | 77% | 100% | 19.7 s |
| qwen2.5-3b-larger | 77% | 100% | 43.3 s |
| llama3.2-1b-other-family | 77% | 100% | 24.5 s |

We split reading the answers: Yuthika took the baseline, chunking and
prompts, and I took the embedding, threshold and generation-model runs.
What I found, reading every answer in those runs against the expected one:

- **Embeddings.** Both alternatives fix q06's retrieval. The baseline
  retrieves the wrong files there and invents a list of "missing" files.
  The answers stay vague even so: gte-Qwen2 says only that there is "a
  planted bug", not that it's the parallax scrolling. Both cut q10 to a
  bare "No" without the reason, which the baseline gives. **bge-small
  breaks the no-match guard.** Its top similarity for the off-topic q14
  ("best pizza topping") is 0.49, over the 0.40 threshold. The model then
  ignores the context and answers about pizza from its own knowledge.
  Cosine scores aren't comparable across embedding models, so a threshold
  tuned on MiniLM doesn't carry over. Each model needs its own.
- **Threshold 0.55.** It answers 5 of 13. It refuses q04 ("When is P3
  due?"), the most common kind of question, because the baseline's best
  match for it scores 0.53. It's fast because it rarely generates, but it
  isn't useful to students. This confirms my local measurement: on MiniLM,
  0.55 is above where the correct sources score.
- **Generation models.** `qwen2.5:3b` gives the most complete answers
  (q02, q03, q10, q11). On q06, where retrieval is wrong, it says the
  information isn't there instead of inventing an answer, which is better
  than the 1.5b baseline. But it drops "11:59 PM" from q04, and it takes
  twice as long (43 s vs. 20 s). `llama3.2:1b` is the weakest. Its q05
  contradicts itself, its q06 cites an unrelated rubric item (R12), and it
  hedges on q10, which the context answers.
- **Shared across runs.** Every configuration gets q05 wrong ("3 services",
  "Redis was added"). The top chunks are Lecture 9's Compose material, not
  Lecture 13's, and a bigger generator can't fix that. q12 and q13 show as
  misses only because their source is a past Q&A thread. Their answers are
  correct.

**The biggest single difference** was type-tailored chunking. It has the
same hit rate as the two new embedding models, but it is the fastest
answering run, at about half the baseline's latency (I haven't checked
why; shorter retrieved contexts are my guess). It also keeps the no-match
guard, and it answers q10 fully. I expected gte-Qwen2 to be the winner for
q06's vocabulary gap. Retrieval-wise it was, but chunking got the same hits
with the small MiniLM model, while gte-Qwen2 is the largest model Infinity
loads and the slowest to embed. The generation model
mattered less than I thought. A bigger model writes more complete answers
but can't fix wrong retrieval, which matches what the prompts showed
locally.

**On the VM**, measured during a `qwen2.5:3b` compare call (the largest
model) with all three embedding models loaded: the peak was 8.1 GB of
15.6 GB, with no swap (Infinity 4.5 GB, Ollama 2.3 GB, MySQL 0.4 GB). The
idle baseline was 6.0 GB. `compare_answer_truncated` didn't appear in the
backend log from the deploy through the harness run, and none of the 126
answers ends mid-sentence. One setting isn't in the code defaults: the VM
sets `RAG_SERVICE_TIMEOUT_S=300`, because a gte-Qwen2 ingestion batch takes
over 60 s on 4 CPUs. !43 documents it in `.env.template`.

`eval/report.json` and `eval/report.md` (about 6,700 lines) are the
harness's output, not hand-written, and they're committed under Yuthika's
name because she ran the harness.

## 4. AI Tools Used

**Claude Code, my main working session** (the desktop app's Code tab, in
`~/qna-69`). It's logged automatically as
[`ai_log/*_dd7b27ca.md`](../ai_log/), about 160 entries from 10/12 to 10/24.
What I used it for:

- **Reviewing every one of Yuthika's MRs.** It merged the branch with `main`
  in a scratch worktree, ran the unit tests, and where it mattered ran the
  change for real: real Infinity and ChromaDB for ingestion, real MySQL for
  AI posts and their database constraints, and the actual model's answers
  to check the refusal filter.
- **Writing my features**: the Compose services and `clients.py`, the
  resource endpoints, the Resources page, repo ingestion (markdown, PDF,
  zip, clone), `pipeline.run()` with the prompt and generation gate, the T8
  token layer and toggle, `eval/configs.json`, and the T7 integration tests.
- **Walking me through GCP one step at a time**: billing, the VM, the
  static IP, Docker, the production `.env`. It worked in the built-in
  browser; I signed in and clicked the IAM grant myself.
- **Keeping a shared progress file and drafting my messages to Yuthika.**

**Where it helped most:** turning "looks fine" into evidence. Examples:

- It caught a real bug in my own resource list (an unknown course returned
  200 instead of 404) by writing the integration test first.
- It showed that a teammate's refusal regex caught 0 of 4 real refusals,
  using the model's actual output.
- It measured contrast on every page in both themes instead of eyeballing
  it.
- It verified bge-small's vectors matched CLS pooling exactly.

**Where it fell short:**

- **It sometimes assumed instead of measuring.** Its first contrast audit
  reported failures that were really transitions frozen in a background tab.
  It had to find that, and then fix the same freeze for real users.
- **It hard-coded too much in tests.** A test with three collection names
  broke when a fourth profile landed.
- **It needed reminders about my preferences**: replies in Chinese, one step
  at a time when guiding me.
- **It needs a person for sign-ins, IAM grants and tokens.** It refused to
  handle credentials, which was right, but it meant some steps waited on me.

**Claude Code, a second session for GitLab** ("CS639 P3", in my home
directory, not in this repo). It held my GitLab API token, so all MR
operations went through it: opening MRs, approving and merging pinned to a
SHA, retargeting stacked MRs, and status queries. The main session never
saw the token. It also re-reviewed every MR before approving: authorship,
deleted tests, CI changes, credentials. It stopped two mistakes:

- approving !33 into an already-merged branch;
- approving !17 against the wrong target.

Its log isn't committed. It contains the token, and the token is the reason
the session exists, so I chose to describe it here instead. What it did is
visible in GitLab itself: every MR it opened, approved, merged or
retargeted shows up in the MR's activity as done by `yyzhang`. In the main
session's log, each of those steps appears as a request I sent it, followed
by the result it reported back.

I didn't use any other AI tools (no ChatGPT, Copilot or web chat) for this
project.

## 5. Best Practices Learned

- **Measure before you choose a number.** Our threshold, the model choices
  and the contrast tokens all came from small measurement scripts, not
  intuition. Where we went with intuition, like the example's 0.65
  threshold or my guess that a regex covered "the context does not…", the
  data said otherwise.
- **Evaluate AI output against the real model, not against what you expect
  it to say.** The refusal filter looked right and passed its unit tests,
  but the real model phrases refusals differently. Reusing the eval run's
  actual answers as test cases found it.
- **Make the safe path structural.** Replacing Tailwind's palette, instead
  of only adding tokens, means a raw color can't come back. A dry-run
  compare endpoint that only reads means it can't create rows. A repo clone
  with no working tree means no symlink can escape.
- **Local model serving is a resource budget.** Three embedding models plus
  Ollama on a 16 GB, 4-vCPU VM (8.1 GB peak with the 3b model), generation at
  5–30 s per answer on a laptop, and model swaps that show up in latency.
  Timeouts, a single generation gate and pausing live answers during a
  harness run all come from that budget.
- **Small MRs, one thing per commit, and pinned merges.** Approving "at this
  SHA" and checking an MR's target branch before approving caught real
  problems twice, both from stacked MRs whose base branch had already been
  merged.
- **AI makes review cheaper, so do more of it.** I reviewed every teammate
  MR by running it, not just reading it. That found a content-hash bug, an
  un-accept edge case, a missing course check and the refusal regex, all
  before they reached `main`.

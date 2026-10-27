# Yuthika Goel (ygoel3): Project 3 individual document

## 1. Repository and Codebase Organization

This repository describes a question board application where students can get their questions answered by both teaching staffs as well as an AI teaching assistant (which can answer questions on the staff’s behalf). These answers are grabbed directly from the course content and can be validated by the teaching staff. If the AI teaching assistant is unable to answer a certain question, those question can be redirected to a human staff. 

The repository is organized into the backend, three separate frontends, evaluation tools, scripts, tests, documentation, and AI logs. The backend also contains the RAG pipeline used to generate answers from course resources.

- backend/app/ contains the main FastAPI application:
  - routers/ contains the API endpoints, including auth.py, admin.py, qa.py, resources.py, and rag.py.
  - services/ contains the business logic, including authentication, Q&A, rosters, AI answering, and resource management.
  - models/ defines the database models for users, courses, questions, answers, and resources.
  - schemas/ contains the Pydantic request and response formats.
  - common/ contains shared code for authentication, exceptions, rate limiting, and uploads.
  - migrations/ uses Alembic to manage changes to the MySQL database.
- backend/app/services/rag/ contains the RAG pipeline:
  - profiles.py defines the ingestion profiles, the chunking and embedding settings that are built into the stored vectors. Query-time settings (similarity threshold, system prompt, generation model) are chosen per request instead.
  - fetchers.py collects content from websites, uploads, repositories, and previous Q&A.
  - chunking.py splits the collected content into smaller pieces.
  - ingestion.py manages background ingestion and syncing.
  - prompt.py builds the prompts sent to the model.
  - pipeline.py performs retrieval and generation.
  - clients.py communicates with Ollama, Infinity, and ChromaDB.
  - compare.py supports configuration comparisons, while health.py checks whether the RAG services are ready.
- frontend/student/, frontend/staff/, and frontend/admin/ contain the three React interfaces for the different types of users.
- eval/ contains the comparison harness, configurations, ground truth, off-topic questions, reports, and sample data used to evaluate RAG.
- scripts/ contains utilities for tasks such as ingesting evaluation data and seeding demo data.
- tests/ contains the project's unit and integration tests.
- docs/ contains project documentation, including design-rag.md.
- ai_log/ stores the AI session logs created throughout development.

The main components connect through the FastAPI backend. Nginx sends requests to FastAPI, and MySQL stores the main data. For RAG, Infinity creates embeddings, ChromaDB stores and searches them, and Ollama generates the AI answers.

When a student asks a question, qa.py sends it to the Q&A service and starts the AI response process. The RAG pipeline searches ChromaDB for useful course information and sends that information to Ollama to create an answer. If the answer is valid, it is saved along with its citations so the student and staff can see it. This answer can then be accepted or retracted by the staff.

I was responsible for writing the READMEs for the routers/, services/, and models/ directories on the docs/ygoel3-readmes branch. Writing these helped me understand what each part of the backend is responsible for and how information moves between the API routes, business logic, and database models. This also helped me understand the codebase a lot better and helped me ask reasonable design decisions questions during the Elephant-Goldfish phase of the project.

## 2. Design Process (The Elephant Goldfish Discussion)

Design document: [docs/design-rag.md](design-rag.md)

For designing the RAG pipeline, I first made use of an Elephant discussion to create a design document. I questioned Claude’s suggestions and asked for clarifications for decisions involving ingestion, citations and AI authored answers before accepting them. For example, Claude originally suggested linking repository citations to the specific commit that was ingested so that the line numbers would always match. I questioned this because students could then be sent to outdated course information. We decided to link citations to the current branch instead and keep the commit SHA in the metadata for tracking.

After completing the design document, I sent it over to Bill for a review. Bill found some issues that were added to the document. After this, I ran five Goldfish tests. Each review found problems the previous one missed, including timeouts, missing safety checks, and RAG failures affecting the normal Q&A system. I checked the Goldfish claims against the actual code before making changes, and I also disagreed with some of its suggested solutions. Rejected suggestions were kept in the document and labeled with the Goldfish run they came from.

However, Goldfish also had shortfalls. Some fixes caused new problems that were only caught in later runs. Even after five reviews, it still missed an indexing bug involving un-accepting and re-accepting answers that Bill later found.

This process showed me that AI review was useful for quickly finding many issues, but repeated AI review could still overlook more complex multi-step interactions between different parts of the system. It also made me more careful during implementation about checking AI suggestions against the code and testing edge cases. Human review was important for catching problems that the AI missed.

**Session logs for this section:**

- Elephant discussion (start): [ai_log/2026-10-16_18-48-19_b49b7f7e.md](../ai_log/2026-10-16_18-48-19_b49b7f7e.md)
- Citation links (commit SHA vs. current branch): [ai_log/2026-10-16_19-31-41_b49b7f7e.md](../ai_log/2026-10-16_19-31-41_b49b7f7e.md), agreed in [ai_log/2026-10-16_19-32-15_b49b7f7e.md](../ai_log/2026-10-16_19-32-15_b49b7f7e.md)
- Bill's review: [ai_log/2026-10-17_19-42-40_2d1a52b2.md](../ai_log/2026-10-17_19-42-40_2d1a52b2.md)
- Goldfish runs 1–5: [1](../ai_log/2026-10-17_19-49-33_2862d500.md), [2](../ai_log/2026-10-17_19-58-33_afcc857a.md), [3](../ai_log/2026-10-17_20-42-10_a50d8437.md), [4](../ai_log/2026-10-17_23-40-59_a0e949c4.md), [5](../ai_log/2026-10-17_23-49-16_4666aadf.md)
- Goldfish 1 findings in full (its own log is truncated): [ai_log/2026-10-17_19-53-42_2d1a52b2.md](../ai_log/2026-10-17_19-53-42_2d1a52b2.md)
- Bill's un-accept/re-accept bug fix: [ai_log/2026-10-18_14-56-58_c5b44b8b.md](../ai_log/2026-10-18_14-56-58_c5b44b8b.md)

## 3. RAG Configuration Findings

Results from the deployed VM run on 10/24 ([eval/report.md](../eval/report.md), 126/126 calls returned 200). Baseline: `sliding-window` chunking, MiniLM embeddings, threshold 0.40, the T5 guardrail prompt, `qwen2.5:1.5b`. Each comparison changes one setting.

| Axis | Comparison | Retrieval hit | No-match (q14) | Avg time | Avg CPU | Answer quality | Better side |
|---|---|---:|---:|---:|---:|---|---|
| — | baseline | 77% | 100% | 20.6 s | 52.6% | 8 correct / 3 partial / 2 wrong | — |
| Chunking | type-tailored | 85% | 100% | 11.9 s | 53.4% | 8 correct / 2 partial / 3 wrong. It found more of the expected sources, but some answers lost useful details. | Type-tailored was better for retrieval and speed, but did not improve the answers overall. |
| Embedding model | gte-Qwen2 | 85% | 100% | 26.9 s | 51.5% | It improved retrieval, including for q06, but some of the answers were still incomplete. | gte-Qwen2 had better retrieval, but it was more expensive and slower to embed than the baseline. |
| Embedding model | bge-small | 85% | 0% | 23.9 s | 52.8% | It improved retrieval, but answered the off-topic q14 instead of refusing it. | Baseline was better because bge-small did not work well with the same 0.40 threshold. |
| Similarity threshold | 0.55 | 38% | 100% | 3.8 s | 49.9% | It only answered 5 of the 13 questions and refused some questions that should have been answered. | The baseline 0.40 threshold was better because 0.55 filtered out too many useful results. |
| System prompt | untrusted-context | 77% | 100% | 20.0 s | 53.1% | 9 correct / 2 partial / 2 wrong. Some answers were more complete and it reduced some made-up information. | Untrusted-context was slightly better than the baseline. |
| System prompt | quote-grounded | 77% | 100% | 19.7 s | 53.2% | 9 correct / 2 partial / 2 wrong. It improved some answers but still made up information in others. | Slightly better than the baseline, but it did not completely prevent incorrect information. |
| Generation model | qwen2.5:3b | 77% | 100% | 43.3 s | 52.0% | It generally gave the most complete answers and was less likely to make something up when the needed information was missing. | qwen2.5:3b was better for answer quality, but took about twice as long as the baseline. |
| Generation model | llama3.2:1b | 77% | 100% | 24.5 s | 53.0% | Its answers were weaker, including a contradictory answer for q05 and an unrelated answer for q06. | Baseline was better overall. |

Notes on reading the table:

Retrieval was measured using 13 questions. q12 and q13 are counted as misses because their source is a previous Q&A thread that the harness cannot match, even though their answers were correct.

A retrieval hit means the system found a chunk from the correct file, but not necessarily the exact part containing the answer. This happened with q05 and q06.

The generation model made the biggest difference in the type of answer and answer quality that we got. qwen2.5:3b gave the most complete answers, but it took about twice as long as the baseline model. I originally expected better retrieval to lead to better answers, but this was not always the case. For example, in the baseline run for q07 the correct passage was ranked first, but the model still added three CI checks that were not in it. The prompt changes and the larger model fixed this. The opposite also happened: q05 counted as a retrieval hit in every run because the right file was found, but the passage with the answer was never retrieved, so every run that answered it got it wrong. This showed me that our pipeline was limited not only by finding the right information, but also by how well the model understood and used that information.

**Session logs for this section:**

- Harness run on the VM (start): [ai_log/2026-10-24_12-43-18_5ac736e0.md](../ai_log/2026-10-24_12-43-18_5ac736e0.md)
- Harness finished, 126/126, report in MR !42: [ai_log/2026-10-24_13-28-51_5ac736e0.md](../ai_log/2026-10-24_13-28-51_5ac736e0.md)
- My half of the answer-quality read (baseline, chunking, both prompts): [ai_log/2026-10-24_13-35-26_5ac736e0.md](../ai_log/2026-10-24_13-35-26_5ac736e0.md)

## 4. AI Tools Used

### Claude Code

Claude Code was the only AI tool that I used. I used it throughout the project to understand the existing codebase, design and review the RAG system, help with implementation, and debug problems. It was especially useful during the Elephant and Goldfish discussions because it helped me find problems in the design and consider different solutions before implementing them. I also made sure to check its suggestions against the actual code and test results before making changes.

However, one of my Elephant sessions was seriously disrupted when Claude had some unexpected issues and started flagging regular coding prompts as violating its guidelines, which caused the output responses to be truncated. I tried rewording my prompts multiple times, but they were still being flagged, which made the process very time consuming. I eventually had to continue the discussion in another session. Claude also sometimes gave incorrect suggestions or missed bugs that were later found through testing or human review. For example, it initially treated a "Course 19 not found" error as a test flake, but it later turned out to be an actual bug. Claude also created a draft of my ygoel3.md individual document without me asking it to, even though the assignment required the document to be written in my own words. I did not use the draft and instead asked Claude to delete the document and the branch it had created. Overall, Claude was useful for understanding and reviewing the project, but its output still needed to be verified.

**Session logs for this section:**

- All Claude Code sessions are logged in [ai_log/](../ai_log/).
- Elephant and Goldfish sessions: listed under section 2.
- Elephant session disrupted by flagged prompts: the last log of that session is [ai_log/2026-10-16_19-32-15_b49b7f7e.md](../ai_log/2026-10-16_19-32-15_b49b7f7e.md). The discussion continued in a new session, starting at [ai_log/2026-10-16_19-35-13_5df5a1ed.md](../ai_log/2026-10-16_19-35-13_5df5a1ed.md), whose first prompt explains why.
- "Course 19 not found" treated as a flake: [ai_log/2026-10-20_16-58-47_5ac736e0.md](../ai_log/2026-10-20_16-58-47_5ac736e0.md). The diagnosis on 10/22 was not captured by the logging hook. The fix is commit `a6160ae` (MR !27).
- Unrequested draft of ygoel3.md individual document, and its deletion: [ai_log/2026-10-26_13-38-29_3db489e2.md](../ai_log/2026-10-26_13-38-29_3db489e2.md)

## 5. Best Practices Learned

One of the biggest things I learned from this project was that AI output should always be verified instead of being accepted just because it looks correct. For example, Claude initially treated the "Course 19 not found" error as a test flake, but it later turned out to be an actual bug. I also learned that improving one part of a RAG pipeline does not necessarily improve the final answer. Some configurations improved retrieval but still produced worse answers, which showed me that retrieval and generation both need to be evaluated. Working with locally hosted models also showed me the tradeoff between answer quality and resource cost, since the larger generation model gave better answers but took about twice as long. Finally, working in a team gave me more experience with using separate branches, merge requests, code reviews, testing, and deployments rather than making changes directly to the main codebase.

# RAG Configuration Comparison Report

## Summary — baseline vs. each one-axis comparison

| Run | Ingestion profile | Threshold | System prompt (first 40 chars) | Generation model | Retrieval hit rate | No-match accuracy | Avg wall-clock (ms) | Avg generation (ms) | Avg CPU % |
|---|---|---|---|---|---|---|---|---|---|
| baseline | sliding-window | 0.4 | Only use the information provided in the… | qwen2.5:1.5b | 77% | 100% | 20557.0 | 20340.0 | 52.6 |
| type-tailored-chunking | type-tailored | 0.4 | Only use the information provided in the… | qwen2.5:1.5b | 85% | 100% | 11928.3 | 11812.3 | 53.4 |
| gte-qwen2-last-token | embedding-alt | 0.4 | Only use the information provided in the… | qwen2.5:1.5b | 85% | 100% | 26862.8 | 23578.2 | 51.5 |
| bge-small-cls | embedding-cls | 0.4 | Only use the information provided in the… | qwen2.5:1.5b | 85% | 0% | 23870.7 | 23684.7 | 52.8 |
| threshold-0.55-conservative | sliding-window | 0.55 | Only use the information provided in the… | qwen2.5:1.5b | 38% | 100% | 3760.3 | 3651.1 | 49.9 |
| untrusted-context-prompt | sliding-window | 0.4 | You answer students' questions about a c… | qwen2.5:1.5b | 77% | 100% | 20030.2 | 19917.5 | 53.1 |
| quote-grounded-prompt | sliding-window | 0.4 | Answer the question in <student_question… | qwen2.5:1.5b | 77% | 100% | 19739.4 | 19624.7 | 53.2 |
| qwen2.5-3b-larger | sliding-window | 0.4 | Only use the information provided in the… | qwen2.5:3b | 77% | 100% | 43275.7 | 43096.5 | 52.0 |
| llama3.2-1b-other-family | sliding-window | 0.4 | Only use the information provided in the… | llama3.2:1b | 77% | 100% | 24516.2 | 24394.5 | 53.0 |

## Per-question detail (read these to judge response quality yourself)

### q01 — baseline
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Each student has a bank of 5 slip days for the semester, usable on P1â€“P4 only (not the Final Project). Slip days waive the late deduction but never move the hard cutoff.
- actual answer: Each student gets 5 slip days, which are usable on P1–P4 (not the Final Project).

### q02 — baseline
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: No submission is accepted more than 2 days after the due date, for any project, regardless of slip days remaining. Slip days waive the deduction within that window â€” they don't extend the window itself.
- actual answer: The hard cutoff for late project submissions, even if you have slip days left, is 2 days after the due date.

### q03 — baseline
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: No â€” quizzes and written exams are closed-AI, closed-book. Using AI on them violates the AI Use Policy.
- actual answer: No, AI is not allowed during exams.

### q04 — baseline
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Tuesday, October 27 at 11:59 PM.
- actual answer: Project 3 is due on Tuesday, October 27 at 11:59 PM.

### q05 — baseline
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: The stack grows from 3 to 6 services â€” Ollama (generation), Infinity (embeddings), and ChromaDB (vector store) are the three added at Lecture 13.
- actual answer: By Lecture 13, the Docker Compose stack has 3 services. The services added are Redis caching and integration testing.

### q06 — baseline
- matched: True (expected no-match: False)
- retrieval hit: False
- expected answer: The parallax background scrolling system is broken. Background layers should scroll correctly relative to the camera and player movement: the farthest-back layer should be the smallest image and scroll slowest; the layer closest to the tiles should be the largest image and scroll fastest.
- actual answer: The Project 1 starter code does not include the necessary files for Claude Code to function properly. Specifically, it lacks the following files:

- CLAUDE.md
- SPEC.md
- RULES.md
- .claude/settings.json
- commands/
- skills/

These files are required for Claude Code to be able to run and provide the necessary context and commands for the students to use. Without these files, students will not be able to use Claude Code as intended in the project.

### q07 — baseline
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Python style (ruff check backend/ scripts/), frontend type checking (tsc --noEmit on all three apps), and GitLab's built-in secret detection scan.
- actual answer: The Project 2's CI pipeline runs the following checks before a merge request can be approved:

1. Python style check: `ruff check backend/ scripts/`
2. Frontend types check: `tsc --noEmit` (all three apps)
3. Secret detection: GitLab built-in scan
4. Code formatting: `npm run format:check`
5. Linting: `npm run lint`
6. Unit tests: `npm run test`

### q08 — baseline
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Redis holds the ephemeral live state (current question, who has answered, scores) â€” fast, per-room, expires with the room. MySQL holds the permanent record â€” every answer is written to the database immediately.
- actual answer: The live game state in Redis (current question, who has answered, scores) — fast, per-room, expires with the room.
The permanent record of what happened is in MySQL.

### q09 — baseline
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Temperature controls how the model's probability distribution over the vocabulary gets sampled. Near 0.0 is nearly deterministic (the highest-probability token); around 0.7 is balanced with some variety while staying coherent; 1.5 and above is high randomness, more likely to go off the rails.
- actual answer: Temperature controls how the probability distribution over the entire vocabulary is sampled. At temperature 0.0, the model outputs a probability distribution over the entire vocabulary, not one guaranteed next token. At temperature 0.0, the same prompt can produce slightly different output across runs on different hardware due to tiny rounding differences in parallelized floating-point matrix operations. At higher temperatures, the model outputs a more random distribution, increasing the likelihood of hallucinations.

### q10 — baseline
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: No. Even at temperature 0.0, the same prompt can produce slightly different output across runs on different hardware, because parallelized floating-point matrix operations aren't perfectly associative â€” tiny rounding differences can flip which token is technically highest-probability in a near-tie.
- actual answer: No, a language model is not fully deterministic at temperature 0. Even at temperature 0.0, the same prompt can produce slightly different output across runs on different hardware due to tiny rounding differences in parallelized floating-point matrix operations.

### q11 — baseline
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: No. Each model family trains its own tokenizer on its own vocabulary, so the same text produces a different token count on a different model â€” always count with the tokenizer for the model you're actually using.
- actual answer: No, a token count from one model's tokenizer does not transfer to a different model.

### q12 — baseline
- matched: True (expected no-match: False)
- retrieval hit: False
- expected answer: In development it's safe to nuke the volume and start clean: docker compose down -v (removes the MySQL volume), then docker compose up --build, then docker compose run --rm backend alembic upgrade head again. Don't do this against anything with data you care about â€” -v is destructive.
- actual answer: The safe way to reset your migrations in development is to nuke the volume and start clean. This can be done by running the following commands:

1. Stop the Docker containers:
   ```
   docker compose down -v
   ```

2. Remove the MySQL volume:
   ```
   docker volume rm <mysql-volume-name>
   ```

3. Start the containers again:
   ```
   docker compose up --build
   ```

4. Run Alembic upgrade again:
   ```
   docker compose run --rm backend alembic upgrade head
   ```

Remember, this will remove the MySQL volume, so be sure to replace `<mysql-volume-name>` with the actual name of your MySQL volume.

### q13 — baseline
- matched: True (expected no-match: False)
- retrieval hit: False
- expected answer: CLAUDE.md is prose, auto-loaded at session start, for codebase overview/conventions/behavioral rules. .claude/settings.json is structured config â€” permissions, hooks, environment variables. There's no 'rules' field in settings.json; behavioral rules always belong in CLAUDE.md prose.
- actual answer: CLAUDE.md is prose, where you put codebase overview, conventions, and behavioral rules for Claude to read. .claude/settings.json is structured config, where you configure permissions, hooks, and environment variables. There's no 'rules' field in settings.json; behavioral rules always belong in CLAUDE.md prose, not JSON.

### q14 — baseline
- matched: False (expected no-match: True)
- retrieval hit: None
- expected answer: None
- actual answer: None

### q01 — type-tailored-chunking
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Each student has a bank of 5 slip days for the semester, usable on P1â€“P4 only (not the Final Project). Slip days waive the late deduction but never move the hard cutoff.
- actual answer: Each student gets a bank of 5 slip days for the semester, which are usable on P1–P4 only (not the Final Project).

### q02 — type-tailored-chunking
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: No submission is accepted more than 2 days after the due date, for any project, regardless of slip days remaining. Slip days waive the deduction within that window â€” they don't extend the window itself.
- actual answer: The hard cutoff for late project submissions, even if you have slip days left, is 2 days after the due date.

### q03 — type-tailored-chunking
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: No â€” quizzes and written exams are closed-AI, closed-book. Using AI on them violates the AI Use Policy.
- actual answer: No, AI is not allowed during exams.

### q04 — type-tailored-chunking
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Tuesday, October 27 at 11:59 PM.
- actual answer: Project 3 is due on Tuesday, October 27 at 11:59 PM.

### q05 — type-tailored-chunking
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: The stack grows from 3 to 6 services â€” Ollama (generation), Infinity (embeddings), and ChromaDB (vector store) are the three added at Lecture 13.
- actual answer: By Lecture 13, the Docker Compose stack has 2 services. The services added are a production override and a multi-stage build.

### q06 — type-tailored-chunking
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: The parallax background scrolling system is broken. Background layers should scroll correctly relative to the camera and player movement: the farthest-back layer should be the smallest image and scroll slowest; the layer closest to the tiles should be the largest image and scroll fastest.
- actual answer: The Project 1 starter code has the following requirements that students must fix by the deadline:

- [ ] All work is merged to `main` via approved merge requests.
- [ ] Each member's `docs/<your-login>.md` is present on `main`.
- [ ] Claude Code session logs are in `ai_log/`; logs from any other AI tools are in `docs/` and referenced from your individual document.
- [ ] No force-pushes to `main` after the deadline.

### q07 — type-tailored-chunking
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Python style (ruff check backend/ scripts/), frontend type checking (tsc --noEmit on all three apps), and GitLab's built-in secret detection scan.
- actual answer: The pipeline runs on every merge request.

### q08 — type-tailored-chunking
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Redis holds the ephemeral live state (current question, who has answered, scores) â€” fast, per-room, expires with the room. MySQL holds the permanent record â€” every answer is written to the database immediately.
- actual answer: In Buzzer's real-time architecture, the live game state lives in Redis (current question, who has answered, scores) — fast, per-room, expires with the room.

### q09 — type-tailored-chunking
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Temperature controls how the model's probability distribution over the vocabulary gets sampled. Near 0.0 is nearly deterministic (the highest-probability token); around 0.7 is balanced with some variety while staying coherent; 1.5 and above is high randomness, more likely to go off the rails.
- actual answer: Temperature controls how the probability distribution over the vocabulary is sampled. At a temperature of 0.0, the model outputs a nearly deterministic result, favoring the highest-probability token. At temperatures above 1.5, the output becomes more random, with a higher likelihood of going off the rails.

### q10 — type-tailored-chunking
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: No. Even at temperature 0.0, the same prompt can produce slightly different output across runs on different hardware, because parallelized floating-point matrix operations aren't perfectly associative â€” tiny rounding differences can flip which token is technically highest-probability in a near-tie.
- actual answer: No, a language model is not fully deterministic at temperature 0. Even at temperature 0.0, the same prompt can produce slightly different output across runs on different hardware due to tiny rounding differences in parallelized floating-point matrix operations.

### q11 — type-tailored-chunking
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: No. Each model family trains its own tokenizer on its own vocabulary, so the same text produces a different token count on a different model â€” always count with the tokenizer for the model you're actually using.
- actual answer: No, a token count from one model's tokenizer does not transfer to a different model.

### q12 — type-tailored-chunking
- matched: True (expected no-match: False)
- retrieval hit: False
- expected answer: In development it's safe to nuke the volume and start clean: docker compose down -v (removes the MySQL volume), then docker compose up --build, then docker compose run --rm backend alembic upgrade head again. Don't do this against anything with data you care about â€” -v is destructive.
- actual answer: The safe way to reset your migrations in development is to nuke the volume and start clean. This can be done by running `docker compose down -v` to remove the MySQL volume, then `docker compose up --build` to rebuild the containers, and finally `docker compose run --rm backend alembic upgrade head` again. This method is safe in development but should not be used against any data that you care about, as it is destructive.

### q13 — type-tailored-chunking
- matched: True (expected no-match: False)
- retrieval hit: False
- expected answer: CLAUDE.md is prose, auto-loaded at session start, for codebase overview/conventions/behavioral rules. .claude/settings.json is structured config â€” permissions, hooks, environment variables. There's no 'rules' field in settings.json; behavioral rules always belong in CLAUDE.md prose.
- actual answer: CLAUDE.md is prose, where you put codebase overview, conventions, and behavioral rules for Claude to read. .claude/settings.json is structured config, where you configure permissions, hooks, and environment variables. There's no 'rules' field in settings.json; behavioral rules always belong in CLAUDE.md prose, not JSON.

### q14 — type-tailored-chunking
- matched: False (expected no-match: True)
- retrieval hit: None
- expected answer: None
- actual answer: None

### q01 — gte-qwen2-last-token
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Each student has a bank of 5 slip days for the semester, usable on P1â€“P4 only (not the Final Project). Slip days waive the late deduction but never move the hard cutoff.
- actual answer: Each student gets 5 slip days, which are usable on P1–P4 only (not the Final Project).

### q02 — gte-qwen2-last-token
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: No submission is accepted more than 2 days after the due date, for any project, regardless of slip days remaining. Slip days waive the deduction within that window â€” they don't extend the window itself.
- actual answer: The hard cutoff for late project submissions is 2 days after the due date, regardless of slip days remaining.

### q03 — gte-qwen2-last-token
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: No â€” quizzes and written exams are closed-AI, closed-book. Using AI on them violates the AI Use Policy.
- actual answer: No, AI is not allowed during exams.

### q04 — gte-qwen2-last-token
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Tuesday, October 27 at 11:59 PM.
- actual answer: Project 3 is due on Tuesday, October 27 at 11:59 PM.

### q05 — gte-qwen2-last-token
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: The stack grows from 3 to 6 services â€” Ollama (generation), Infinity (embeddings), and ChromaDB (vector store) are the three added at Lecture 13.
- actual answer: By Lecture 13, the Docker Compose stack has 3 services: FastAPI, MySQL, and Redis. The Redis service was added to the stack.

### q06 — gte-qwen2-last-token
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: The parallax background scrolling system is broken. Background layers should scroll correctly relative to the camera and player movement: the farthest-back layer should be the smallest image and scroll slowest; the layer closest to the tiles should be the largest image and scroll fastest.
- actual answer: The starter code contains a planted bug (T4), and the failing tests and lint errors point straight at it. See T2 for what this means for your merge order.

### q07 — gte-qwen2-last-token
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Python style (ruff check backend/ scripts/), frontend type checking (tsc --noEmit on all three apps), and GitLab's built-in secret detection scan.
- actual answer: The Project 2's CI pipeline runs the following checks before a merge request can be approved:

1. Python style: `ruff check backend/ scripts/`
2. Frontend types: `tsc --noEmit` (all three apps)
3. Secret detection: GitLab built-in scan

These checks must pass before the merge request can be approved.

### q08 — gte-qwen2-last-token
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Redis holds the ephemeral live state (current question, who has answered, scores) â€” fast, per-room, expires with the room. MySQL holds the permanent record â€” every answer is written to the database immediately.
- actual answer: In Buzzer's real-time architecture, the live game state lives in Redis, while the permanent record of what happened lives in MySQL.

### q09 — gte-qwen2-last-token
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Temperature controls how the model's probability distribution over the vocabulary gets sampled. Near 0.0 is nearly deterministic (the highest-probability token); around 0.7 is balanced with some variety while staying coherent; 1.5 and above is high randomness, more likely to go off the rails.
- actual answer: Temperature controls how the probability distribution over the entire vocabulary is sampled. At temperature 0.0, the model outputs a probability distribution that is nearly deterministic, meaning it is highly likely to output the highest-probability token. At higher temperatures (above 1.5), the model outputs a probability distribution that is more random, meaning it is more likely to output tokens that are not the highest-probability token. This can lead to hallucinations, where the model outputs plausible but incorrect information. At temperature 0, the model is more likely to output the highest-probability token, but it is not guaranteed to do so.

### q10 — gte-qwen2-last-token
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: No. Even at temperature 0.0, the same prompt can produce slightly different output across runs on different hardware, because parallelized floating-point matrix operations aren't perfectly associative â€” tiny rounding differences can flip which token is technically highest-probability in a near-tie.
- actual answer: No, a language model is not fully deterministic at temperature 0.

### q11 — gte-qwen2-last-token
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: No. Each model family trains its own tokenizer on its own vocabulary, so the same text produces a different token count on a different model â€” always count with the tokenizer for the model you're actually using.
- actual answer: No, a token count from one model's tokenizer does not transfer to another model.

### q12 — gte-qwen2-last-token
- matched: True (expected no-match: False)
- retrieval hit: False
- expected answer: In development it's safe to nuke the volume and start clean: docker compose down -v (removes the MySQL volume), then docker compose up --build, then docker compose run --rm backend alembic upgrade head again. Don't do this against anything with data you care about â€” -v is destructive.
- actual answer: In development, it's safe to nuke the volume and start clean: `docker compose down -v` (removes the MySQL volume), then `docker compose up --build`, then `docker compose run --rm backend alembic upgrade head` again. Don't do this against anything with data you care about — `-v` is destructive.

### q13 — gte-qwen2-last-token
- matched: True (expected no-match: False)
- retrieval hit: False
- expected answer: CLAUDE.md is prose, auto-loaded at session start, for codebase overview/conventions/behavioral rules. .claude/settings.json is structured config â€” permissions, hooks, environment variables. There's no 'rules' field in settings.json; behavioral rules always belong in CLAUDE.md prose.
- actual answer: The actual difference between CLAUDE.md and .claude/settings.json is that CLAUDE.md is prose where you put codebase overview, conventions, and behavioral rules for Claude to read, while .claude/settings.json is structured config where permissions, hooks, and environment variables are configured. There's no 'rules' field in settings.json; behavioral rules always belong in CLAUDE.md prose, not JSON.

### q14 — gte-qwen2-last-token
- matched: False (expected no-match: True)
- retrieval hit: None
- expected answer: None
- actual answer: None

### q01 — bge-small-cls
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Each student has a bank of 5 slip days for the semester, usable on P1â€“P4 only (not the Final Project). Slip days waive the late deduction but never move the hard cutoff.
- actual answer: Each student gets a bank of 5 slip days for the semester, which are usable on P1–P4 only (not the Final Project).

### q02 — bge-small-cls
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: No submission is accepted more than 2 days after the due date, for any project, regardless of slip days remaining. Slip days waive the deduction within that window â€” they don't extend the window itself.
- actual answer: The hard cutoff for late project submissions is 2 days after the due date, regardless of slip days remaining.

### q03 — bge-small-cls
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: No â€” quizzes and written exams are closed-AI, closed-book. Using AI on them violates the AI Use Policy.
- actual answer: No, AI is not allowed during exams.

### q04 — bge-small-cls
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Tuesday, October 27 at 11:59 PM.
- actual answer: Project 3 is due on Tuesday, October 27 at 11:59 PM.

### q05 — bge-small-cls
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: The stack grows from 3 to 6 services â€” Ollama (generation), Infinity (embeddings), and ChromaDB (vector store) are the three added at Lecture 13.
- actual answer: By Lecture 13, the Docker Compose stack has 3 services. The services added are Redis caching and integration testing.

### q06 — bge-small-cls
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: The parallax background scrolling system is broken. Background layers should scroll correctly relative to the camera and player movement: the farthest-back layer should be the smallest image and scroll slowest; the layer closest to the tiles should be the largest image and scroll fastest.
- actual answer: The Project 1 starter code ships with some unit tests, but the students have to add tests covering their own changes. Specifically, they need to add tests for the T4 fix and each T5 feature.

### q07 — bge-small-cls
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Python style (ruff check backend/ scripts/), frontend type checking (tsc --noEmit on all three apps), and GitLab's built-in secret detection scan.
- actual answer: The Project 2's CI pipeline runs the following checks before a merge request can be approved:

1. Python style check: `ruff check backend/ scripts/`
2. Frontend types check: `tsc --noEmit`
3. Secret detection: GitLab built-in scan

These checks must pass for the merge request to be approved.

### q08 — bge-small-cls
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Redis holds the ephemeral live state (current question, who has answered, scores) â€” fast, per-room, expires with the room. MySQL holds the permanent record â€” every answer is written to the database immediately.
- actual answer: The live game state (current question, who has answered, scores) lives in Redis, while the permanent record of what happened lives in MySQL.

### q09 — bge-small-cls
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Temperature controls how the model's probability distribution over the vocabulary gets sampled. Near 0.0 is nearly deterministic (the highest-probability token); around 0.7 is balanced with some variety while staying coherent; 1.5 and above is high randomness, more likely to go off the rails.
- actual answer: Temperature controls how the probability distribution over the entire vocabulary is sampled. At temperature 0.0, the model outputs a probability distribution over the entire vocabulary, not one guaranteed next token. At temperature 0.0, the same prompt can produce slightly different output, even on different hardware, due to tiny rounding differences in parallelized floating-point matrix operations. At higher temperatures (above 1.5), the output becomes more random, with a higher likelihood of going off the rails. At temperature 0, the model is not fully deterministic, even though it is deterministic at temperature 0.0.

### q10 — bge-small-cls
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: No. Even at temperature 0.0, the same prompt can produce slightly different output across runs on different hardware, because parallelized floating-point matrix operations aren't perfectly associative â€” tiny rounding differences can flip which token is technically highest-probability in a near-tie.
- actual answer: No, a language model is not fully deterministic at temperature 0.

### q11 — bge-small-cls
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: No. Each model family trains its own tokenizer on its own vocabulary, so the same text produces a different token count on a different model â€” always count with the tokenizer for the model you're actually using.
- actual answer: No, a token count from one model's tokenizer does not transfer to another model.

### q12 — bge-small-cls
- matched: True (expected no-match: False)
- retrieval hit: False
- expected answer: In development it's safe to nuke the volume and start clean: docker compose down -v (removes the MySQL volume), then docker compose up --build, then docker compose run --rm backend alembic upgrade head again. Don't do this against anything with data you care about â€” -v is destructive.
- actual answer: In development, it's safe to nuke the volume and start clean: `docker compose down -v` (removes the MySQL volume), then `docker compose up --build`, then `docker compose run --rm backend alembic upgrade head` again. Don't do this against anything with data you care about.

### q13 — bge-small-cls
- matched: True (expected no-match: False)
- retrieval hit: False
- expected answer: CLAUDE.md is prose, auto-loaded at session start, for codebase overview/conventions/behavioral rules. .claude/settings.json is structured config â€” permissions, hooks, environment variables. There's no 'rules' field in settings.json; behavioral rules always belong in CLAUDE.md prose.
- actual answer: CLAUDE.md is prose, auto-loaded at session start and where you put codebase overview, conventions, and behavioral rules for Claude to read. .claude/settings.json is structured config, permissions, hooks, and environment variables. There's no 'rules' field in settings.json; behavioral rules always belong in CLAUDE.md prose, not JSON.

### q14 — bge-small-cls
- matched: True (expected no-match: True)
- retrieval hit: None
- expected answer: None
- actual answer: The best pizza topping is a matter of personal preference and taste, so it's difficult to provide a universally best answer. However, some popular toppings include pepperoni, mushrooms, onions, and anchovies.

### q01 — threshold-0.55-conservative
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Each student has a bank of 5 slip days for the semester, usable on P1â€“P4 only (not the Final Project). Slip days waive the late deduction but never move the hard cutoff.
- actual answer: Each student gets a bank of 5 slip days across P1–P4 (not the Final Project). Slip days waive the late deduction but never move the hard cutoff — see Late Policy below.

### q02 — threshold-0.55-conservative
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: No submission is accepted more than 2 days after the due date, for any project, regardless of slip days remaining. Slip days waive the deduction within that window â€” they don't extend the window itself.
- actual answer: The hard cutoff for late project submissions, even if you have slip days left, is 2 days after the due date.

### q03 — threshold-0.55-conservative
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: No â€” quizzes and written exams are closed-AI, closed-book. Using AI on them violates the AI Use Policy.
- actual answer: No, AI is not allowed during exams.

### q04 — threshold-0.55-conservative
- matched: False (expected no-match: False)
- retrieval hit: False
- expected answer: Tuesday, October 27 at 11:59 PM.
- actual answer: None

### q05 — threshold-0.55-conservative
- matched: False (expected no-match: False)
- retrieval hit: False
- expected answer: The stack grows from 3 to 6 services â€” Ollama (generation), Infinity (embeddings), and ChromaDB (vector store) are the three added at Lecture 13.
- actual answer: None

### q06 — threshold-0.55-conservative
- matched: False (expected no-match: False)
- retrieval hit: False
- expected answer: The parallax background scrolling system is broken. Background layers should scroll correctly relative to the camera and player movement: the farthest-back layer should be the smallest image and scroll slowest; the layer closest to the tiles should be the largest image and scroll fastest.
- actual answer: None

### q07 — threshold-0.55-conservative
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Python style (ruff check backend/ scripts/), frontend type checking (tsc --noEmit on all three apps), and GitLab's built-in secret detection scan.
- actual answer: The Project 2's CI pipeline runs the following checks before a merge request can be approved:

1. Python style check: `ruff check backend/ scripts/`
2. Frontend types check: `tsc --noEmit` (all three apps)
3. Secret detection: GitLab built-in scan

These checks must pass before the merge request can be approved.

### q08 — threshold-0.55-conservative
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Redis holds the ephemeral live state (current question, who has answered, scores) â€” fast, per-room, expires with the room. MySQL holds the permanent record â€” every answer is written to the database immediately.
- actual answer: In Buzzer's real-time architecture, the live game state lives in **Redis** (current question, who has answered, scores) — fast, per-room, expires with the room. The permanent record of what happened lives in **MySQL** persistence — every answer is written to the database immediately.

### q09 — threshold-0.55-conservative
- matched: False (expected no-match: False)
- retrieval hit: False
- expected answer: Temperature controls how the model's probability distribution over the vocabulary gets sampled. Near 0.0 is nearly deterministic (the highest-probability token); around 0.7 is balanced with some variety while staying coherent; 1.5 and above is high randomness, more likely to go off the rails.
- actual answer: None

### q10 — threshold-0.55-conservative
- matched: False (expected no-match: False)
- retrieval hit: False
- expected answer: No. Even at temperature 0.0, the same prompt can produce slightly different output across runs on different hardware, because parallelized floating-point matrix operations aren't perfectly associative â€” tiny rounding differences can flip which token is technically highest-probability in a near-tie.
- actual answer: None

### q11 — threshold-0.55-conservative
- matched: False (expected no-match: False)
- retrieval hit: False
- expected answer: No. Each model family trains its own tokenizer on its own vocabulary, so the same text produces a different token count on a different model â€” always count with the tokenizer for the model you're actually using.
- actual answer: None

### q12 — threshold-0.55-conservative
- matched: False (expected no-match: False)
- retrieval hit: False
- expected answer: In development it's safe to nuke the volume and start clean: docker compose down -v (removes the MySQL volume), then docker compose up --build, then docker compose run --rm backend alembic upgrade head again. Don't do this against anything with data you care about â€” -v is destructive.
- actual answer: None

### q13 — threshold-0.55-conservative
- matched: True (expected no-match: False)
- retrieval hit: False
- expected answer: CLAUDE.md is prose, auto-loaded at session start, for codebase overview/conventions/behavioral rules. .claude/settings.json is structured config â€” permissions, hooks, environment variables. There's no 'rules' field in settings.json; behavioral rules always belong in CLAUDE.md prose.
- actual answer: CLAUDE.md is prose, auto-loaded at session start, and where you put codebase overview, conventions, and behavioral rules for Claude to read. .claude/settings.json is structured config, permissions, hooks, and environment variables. There's no 'rules' field in settings.json; behavioral rules always belong in CLAUDE.md prose, not JSON.

### q14 — threshold-0.55-conservative
- matched: False (expected no-match: True)
- retrieval hit: None
- expected answer: None
- actual answer: None

### q01 — untrusted-context-prompt
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Each student has a bank of 5 slip days for the semester, usable on P1â€“P4 only (not the Final Project). Slip days waive the late deduction but never move the hard cutoff.
- actual answer: Each student gets a bank of 5 slip days for the semester, which can be used across P1–P4 (not the Final Project).

### q02 — untrusted-context-prompt
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: No submission is accepted more than 2 days after the due date, for any project, regardless of slip days remaining. Slip days waive the deduction within that window â€” they don't extend the window itself.
- actual answer: The hard cutoff for late project submissions is 2 days after the due date, regardless of how many slip days you have remaining. Slip days do not extend the hard cutoff; they only waive the late deduction within that 2-day window.

### q03 — untrusted-context-prompt
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: No â€” quizzes and written exams are closed-AI, closed-book. Using AI on them violates the AI Use Policy.
- actual answer: No, AI is not allowed during exams. The AI Use Policy states that AI usage is expected and required in this course, but it must be explained, defended, and verified. AI-generated code cannot be submitted as is, and students must be able to explain the reasoning behind it.

### q04 — untrusted-context-prompt
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Tuesday, October 27 at 11:59 PM.
- actual answer: Project 3 is due on Tuesday, October 27 at 11:59 PM.

### q05 — untrusted-context-prompt
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: The stack grows from 3 to 6 services â€” Ollama (generation), Infinity (embeddings), and ChromaDB (vector store) are the three added at Lecture 13.
- actual answer: By Lecture 13, the Docker Compose stack has 3 services: FastAPI, MySQL, and Redis. The Redis service was added to the stack.

### q06 — untrusted-context-prompt
- matched: True (expected no-match: False)
- retrieval hit: False
- expected answer: The parallax background scrolling system is broken. Background layers should scroll correctly relative to the camera and player movement: the farthest-back layer should be the smallest image and scroll slowest; the layer closest to the tiles should be the largest image and scroll fastest.
- actual answer: The Project 1 starter code has a bug where the game does not start playing the sound when the user clicks the "Play" button. Students need to fix this issue by implementing the logic to play the sound when the "Play" button is clicked.

### q07 — untrusted-context-prompt
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Python style (ruff check backend/ scripts/), frontend type checking (tsc --noEmit on all three apps), and GitLab's built-in secret detection scan.
- actual answer: The Project 2's CI pipeline runs the following checks before a merge request can be approved:

1. Python style: `ruff check backend/ scripts/`
2. Frontend types: `tsc --noEmit` (all three apps)
3. Secret detection: GitLab built-in scan

These checks must all pass before the merge request can be merged.

### q08 — untrusted-context-prompt
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Redis holds the ephemeral live state (current question, who has answered, scores) â€” fast, per-room, expires with the room. MySQL holds the permanent record â€” every answer is written to the database immediately.
- actual answer: In Buzzer's real-time architecture, the live game state is stored in **Redis**. This is where the ephemeral, current state of the game is held, including the current question, who has answered, and scores. The permanent record of what happened is stored in **MySQL**. This includes the state of the game as it was at any point in time, which is crucial for maintaining the history of the game.

### q09 — untrusted-context-prompt
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Temperature controls how the model's probability distribution over the vocabulary gets sampled. Near 0.0 is nearly deterministic (the highest-probability token); around 0.7 is balanced with some variety while staying coherent; 1.5 and above is high randomness, more likely to go off the rails.
- actual answer: Temperature controls how the probability distribution over the entire vocabulary is sampled. At a temperature of 0.0, the model outputs a probability distribution over the entire vocabulary, not one guaranteed next token. This means that the model is more likely to produce a highly random output, with a higher chance of going off the rails. At a temperature of 1.5 or above, the model's output becomes more coherent and less random, with a lower chance of hallucinating or producing highly unlikely outputs.

### q10 — untrusted-context-prompt
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: No. Even at temperature 0.0, the same prompt can produce slightly different output across runs on different hardware, because parallelized floating-point matrix operations aren't perfectly associative â€” tiny rounding differences can flip which token is technically highest-probability in a near-tie.
- actual answer: No, a language model is not fully deterministic at temperature 0. Even at temperature 0.0, the same prompt can produce slightly different output across runs on different hardware due to tiny rounding differences in parallelized floating-point matrix operations.

### q11 — untrusted-context-prompt
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: No. Each model family trains its own tokenizer on its own vocabulary, so the same text produces a different token count on a different model â€” always count with the tokenizer for the model you're actually using.
- actual answer: No, a token count from one model's tokenizer does not transfer to a different model. Each model family trains its own tokenizer on its own vocabulary, so the same text will produce a different token count on a different model.

### q12 — untrusted-context-prompt
- matched: True (expected no-match: False)
- retrieval hit: False
- expected answer: In development it's safe to nuke the volume and start clean: docker compose down -v (removes the MySQL volume), then docker compose up --build, then docker compose run --rm backend alembic upgrade head again. Don't do this against anything with data you care about â€” -v is destructive.
- actual answer: In development, it's safe to nuke the volume and start clean: `docker compose down -v` (removes the MySQL volume), then `docker compose up --build`, then `docker compose run --rm backend alembic upgrade head` again. Don't do this against anything with data you care about — `-v` is destructive.

### q13 — untrusted-context-prompt
- matched: True (expected no-match: False)
- retrieval hit: False
- expected answer: CLAUDE.md is prose, auto-loaded at session start, for codebase overview/conventions/behavioral rules. .claude/settings.json is structured config â€” permissions, hooks, environment variables. There's no 'rules' field in settings.json; behavioral rules always belong in CLAUDE.md prose.
- actual answer: CLAUDE.md is prose where you put codebase overview, conventions, and behavioral rules for Claude to read. .claude/settings.json is structured config where you configure permissions, hooks, and environment variables for Claude. There's no 'rules' field in settings.json; behavioral rules always belong in CLAUDE.md prose, not JSON.

### q14 — untrusted-context-prompt
- matched: False (expected no-match: True)
- retrieval hit: None
- expected answer: None
- actual answer: None

### q01 — quote-grounded-prompt
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Each student has a bank of 5 slip days for the semester, usable on P1â€“P4 only (not the Final Project). Slip days waive the late deduction but never move the hard cutoff.
- actual answer: Each student gets 5 slip days, which are usable on P1–P4 (not the Final Project).

### q02 — quote-grounded-prompt
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: No submission is accepted more than 2 days after the due date, for any project, regardless of slip days remaining. Slip days waive the deduction within that window â€” they don't extend the window itself.
- actual answer: The hard cutoff for late project submissions is 2 days after the due date, regardless of slip days remaining.

### q03 — quote-grounded-prompt
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: No â€” quizzes and written exams are closed-AI, closed-book. Using AI on them violates the AI Use Policy.
- actual answer: NOT Acceptable: submitting AI-generated code you cannot explain, defend, or reproduce the reasoning behind; using AI on quizzes or written exams (which are closed-AI, closed-book); having a non-partner (human or AI acting on their behalf) do your share of a paired project's work.

### q04 — quote-grounded-prompt
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Tuesday, October 27 at 11:59 PM.
- actual answer: Project 3 is due on Tuesday, October 27 at 11:59 PM.

### q05 — quote-grounded-prompt
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: The stack grows from 3 to 6 services â€” Ollama (generation), Infinity (embeddings), and ChromaDB (vector store) are the three added at Lecture 13.
- actual answer: By Lecture 13, the Docker Compose stack has 3 services: FastAPI, MySQL, and Redis. The Redis service was added in Lecture 14.

### q06 — quote-grounded-prompt
- matched: True (expected no-match: False)
- retrieval hit: False
- expected answer: The parallax background scrolling system is broken. Background layers should scroll correctly relative to the camera and player movement: the farthest-back layer should be the smallest image and scroll slowest; the layer closest to the tiles should be the largest image and scroll fastest.
- actual answer: The Project 1 starter code has a bug that students need to fix. Specifically, the code is missing the `onLoad` event listener for the `#buzzer` element, which is necessary for the frontend side-scroller game to function properly.

### q07 — quote-grounded-prompt
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Python style (ruff check backend/ scripts/), frontend type checking (tsc --noEmit on all three apps), and GitLab's built-in secret detection scan.
- actual answer: The checks run before a merge request can be approved in Project 2's CI pipeline are:

1. Python style check (`ruff check backend/ scripts/`)
2. Frontend types check (`tsc --noEmit`)
3. Secret detection (`GitLab built-in scan`)

These checks must pass for the merge request to be approved.

### q08 — quote-grounded-prompt
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Redis holds the ephemeral live state (current question, who has answered, scores) â€” fast, per-room, expires with the room. MySQL holds the permanent record â€” every answer is written to the database immediately.
- actual answer: The live game state, including the current question, who has answered, and scores, lives in **Redis**. The permanent record of what happened, including the scoring logic and the answers written to the database immediately, lives in **MySQL**.

### q09 — quote-grounded-prompt
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Temperature controls how the model's probability distribution over the vocabulary gets sampled. Near 0.0 is nearly deterministic (the highest-probability token); around 0.7 is balanced with some variety while staying coherent; 1.5 and above is high randomness, more likely to go off the rails.
- actual answer: Temperature controls how the probability distribution over the entire vocabulary is sampled. At temperature 0.0, the model outputs a probability distribution over the entire vocabulary, not one guaranteed next token. At temperature 0.0, the same prompt can produce slightly different output across runs on different hardware due to tiny rounding differences in parallelized floating-point matrix operations. At temperature 1.5+, the model outputs a probability distribution over the entire vocabulary, and the distribution is more likely to be sampled randomly, leading to higher hallucination risk.

### q10 — quote-grounded-prompt
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: No. Even at temperature 0.0, the same prompt can produce slightly different output across runs on different hardware, because parallelized floating-point matrix operations aren't perfectly associative â€” tiny rounding differences can flip which token is technically highest-probability in a near-tie.
- actual answer: No, a language model is not fully deterministic at temperature 0. This is supported by the passage stating that even at temperature 0.0, the same prompt can produce slightly different output across runs on different hardware due to parallelized floating-point matrix operations not being perfectly associative.

### q11 — quote-grounded-prompt
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: No. Each model family trains its own tokenizer on its own vocabulary, so the same text produces a different token count on a different model â€” always count with the tokenizer for the model you're actually using.
- actual answer: No, a token count from one model's tokenizer does not transfer to a different model.

### q12 — quote-grounded-prompt
- matched: True (expected no-match: False)
- retrieval hit: False
- expected answer: In development it's safe to nuke the volume and start clean: docker compose down -v (removes the MySQL volume), then docker compose up --build, then docker compose run --rm backend alembic upgrade head again. Don't do this against anything with data you care about â€” -v is destructive.
- actual answer: The safe way to reset migrations in development is to nuke the MySQL volume and start clean. Specifically, you should run `docker compose down -v` to remove the MySQL volume, then `docker compose up --build` to rebuild the containers, and finally `docker compose run --rm backend alembic upgrade head` to reset the migrations.

### q13 — quote-grounded-prompt
- matched: True (expected no-match: False)
- retrieval hit: False
- expected answer: CLAUDE.md is prose, auto-loaded at session start, for codebase overview/conventions/behavioral rules. .claude/settings.json is structured config â€” permissions, hooks, environment variables. There's no 'rules' field in settings.json; behavioral rules always belong in CLAUDE.md prose.
- actual answer: The actual difference between CLAUDE.md and .claude/settings.json is that CLAUDE.md is prose where you put codebase overview, conventions, and behavioral rules for Claude to read, while .claude/settings.json is structured config where permissions, hooks, and environment variables are configured. There's no 'rules' field in settings.json; behavioral rules always belong in CLAUDE.md prose, not JSON.

### q14 — quote-grounded-prompt
- matched: False (expected no-match: True)
- retrieval hit: None
- expected answer: None
- actual answer: None

### q01 — qwen2.5-3b-larger
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Each student has a bank of 5 slip days for the semester, usable on P1â€“P4 only (not the Final Project). Slip days waive the late deduction but never move the hard cutoff.
- actual answer: Each student has a bank of 5 slip days to use across P1–P4 (not the Final Project). Slip days waive the late deduction but never move the hard cutoff.

### q02 — qwen2.5-3b-larger
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: No submission is accepted more than 2 days after the due date, for any project, regardless of slip days remaining. Slip days waive the deduction within that window â€” they don't extend the window itself.
- actual answer: The hard cutoff for late project submissions is 2 days after the due date, for any project, regardless of slip days remaining. Slip days waive the late deduction within that 2-day window — they do not extend the window itself.

### q03 — qwen2.5-3b-larger
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: No â€” quizzes and written exams are closed-AI, closed-book. Using AI on them violates the AI Use Policy.
- actual answer: Based on the information provided in the syllabus, AI is not allowed during exams. The syllabus states that the AI Use Policy supplements the standard UW-Madison academic integrity policy, and it specifically mentions that using AI on quizzes or written exams is not allowed.

### q04 — qwen2.5-3b-larger
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Tuesday, October 27 at 11:59 PM.
- actual answer: Project 3 is due on Tuesday, October 27.

### q05 — qwen2.5-3b-larger
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: The stack grows from 3 to 6 services â€” Ollama (generation), Infinity (embeddings), and ChromaDB (vector store) are the three added at Lecture 13.
- actual answer: By Lecture 13, the Docker Compose stack has 3 services: FastAPI, MySQL, and Redis. These were added as part of the course material for Lecture 9, which covered Docker Compose: multi-service stacks, including FastAPI, MySQL, and Redis.

### q06 — qwen2.5-3b-larger
- matched: True (expected no-match: False)
- retrieval hit: False
- expected answer: The parallax background scrolling system is broken. Background layers should scroll correctly relative to the camera and player movement: the farthest-back layer should be the smallest image and scroll slowest; the layer closest to the tiles should be the largest image and scroll fastest.
- actual answer: There is no information provided about what is broken in the Project 1 starter code or what students have to fix. The context provided is about the Claude Code course, including lectures, activities, and project details, but does not specify any issues with Project 1 starter code.

### q07 — qwen2.5-3b-larger
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Python style (ruff check backend/ scripts/), frontend type checking (tsc --noEmit on all three apps), and GitLab's built-in secret detection scan.
- actual answer: Project 2's CI pipeline runs checks for Python style, frontend types, and secret detection before a merge request can be approved.

### q08 — qwen2.5-3b-larger
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Redis holds the ephemeral live state (current question, who has answered, scores) â€” fast, per-room, expires with the room. MySQL holds the permanent record â€” every answer is written to the database immediately.
- actual answer: In Buzzer's real-time architecture, the live game state lives in Redis, while the permanent record of what happened is stored in MySQL.

### q09 — qwen2.5-3b-larger
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Temperature controls how the model's probability distribution over the vocabulary gets sampled. Near 0.0 is nearly deterministic (the highest-probability token); around 0.7 is balanced with some variety while staying coherent; 1.5 and above is high randomness, more likely to go off the rails.
- actual answer: Temperature in a language model controls how the probability distribution over the entire vocabulary is sampled. At temperature 0.0, the model outputs the highest-probability token, which is nearly deterministic. This means that the model's output is very consistent and follows the most likely next token. 

As the temperature increases, the model becomes more random and less likely to stick to the highest-probability token. Near temperature 0, the model's output is still quite consistent, but above a temperature of approximately 1.5, the model's output becomes more varied and less likely to be the most probable next token. This increased randomness can lead to more varied and potentially less coherent outputs, which can be beneficial for tasks like generating creative text or exploring different possibilities.

### q10 — qwen2.5-3b-larger
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: No. Even at temperature 0.0, the same prompt can produce slightly different output across runs on different hardware, because parallelized floating-point matrix operations aren't perfectly associative â€” tiny rounding differences can flip which token is technically highest-probability in a near-tie.
- actual answer: No, a language model is not fully deterministic at temperature 0. According to the slides, even at temperature 0.0, the same prompt can produce slightly different outputs across runs on different hardware. This is due to the inherent non-perfect associativity of parallelized floating-point matrix operations, which can lead to tiny rounding differences that affect which token is technically "highest probability" in a near-tie.

### q11 — qwen2.5-3b-larger
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: No. Each model family trains its own tokenizer on its own vocabulary, so the same text produces a different token count on a different model â€” always count with the tokenizer for the model you're actually using.
- actual answer: No, a token count from one model's tokenizer does not transfer to a different model. Each model family trains its own tokenizer on its own vocabulary, which means the same text will produce a different token count on a different model.

### q12 — qwen2.5-3b-larger
- matched: True (expected no-match: False)
- retrieval hit: False
- expected answer: In development it's safe to nuke the volume and start clean: docker compose down -v (removes the MySQL volume), then docker compose up --build, then docker compose run --rm backend alembic upgrade head again. Don't do this against anything with data you care about â€” -v is destructive.
- actual answer: In development, if your migrations are stuck in a bad state, the safe way to reset is to nuke the volume and start clean. This can be done by running `docker compose down -v`, which removes the MySQL volume. Then, you can start a new container by running `docker compose up --build`. Finally, you can run `docker compose run --rm backend alembic upgrade head` to reset your migrations to the latest version. This approach is safe for development environments as it does not affect anything with data you care about, as the `-v` flag is used for the destructive action of removing the volume.

### q13 — qwen2.5-3b-larger
- matched: True (expected no-match: False)
- retrieval hit: False
- expected answer: CLAUDE.md is prose, auto-loaded at session start, for codebase overview/conventions/behavioral rules. .claude/settings.json is structured config â€” permissions, hooks, environment variables. There's no 'rules' field in settings.json; behavioral rules always belong in CLAUDE.md prose.
- actual answer: Based on the information provided in the past question, CLAUDE.md and .claude/settings.json serve different purposes in configuring Claude Code.

CLAUDE.md is used for prose configuration. It is auto-loaded at session start and is where you put codebase overview, conventions, and behavioral rules for Claude to read. This file is for setting up the general context and rules for how Claude should behave and interpret the codebase.

On the other hand, .claude/settings.json is for structured configuration. It includes permissions (allow/deny specific tools or commands), hooks, and environment variables. This file is used to set up more specific configurations and settings for Claude Code. There is no 'rules' field in settings.json; behavioral rules always belong in CLAUDE.md prose, not JSON.

### q14 — qwen2.5-3b-larger
- matched: False (expected no-match: True)
- retrieval hit: None
- expected answer: None
- actual answer: None

### q01 — llama3.2-1b-other-family
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Each student has a bank of 5 slip days for the semester, usable on P1â€“P4 only (not the Final Project). Slip days waive the late deduction but never move the hard cutoff.
- actual answer: According to the syllabus, each student has a bank of 5 slip days for the semester, usable on P1–P4 only (not the Final Project).

### q02 — llama3.2-1b-other-family
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: No submission is accepted more than 2 days after the due date, for any project, regardless of slip days remaining. Slip days waive the deduction within that window â€” they don't extend the window itself.
- actual answer: The hard cutoff for late project submissions is 2 days after the due date, regardless of the number of slip days remaining.

### q03 — llama3.2-1b-other-family
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: No â€” quizzes and written exams are closed-AI, closed-book. Using AI on them violates the AI Use Policy.
- actual answer: According to the syllabus, AI is not allowed during exams. It is mentioned in the context of the "Academic Integrity" section, which states that "The AI Use Policy above supplements it for AI-specific scenarios in this course."

### q04 — llama3.2-1b-other-family
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Tuesday, October 27 at 11:59 PM.
- actual answer: The due date for Project 3 is Tuesday, October 27 at 11:59 PM.

### q05 — llama3.2-1b-other-family
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: The stack grows from 3 to 6 services â€” Ollama (generation), Infinity (embeddings), and ChromaDB (vector store) are the three added at Lecture 13.
- actual answer: The Docker Compose stack has 3 services:

1. Backend (host/player/admin)
2. FastAPI (player)
3. MySQL (admin)

The question asks about the number of services and what got added, but the provided context does not mention any changes to the services or the addition of new services. It only mentions the existing services and the changes made to the backend service.

### q06 — llama3.2-1b-other-family
- matched: True (expected no-match: False)
- retrieval hit: False
- expected answer: The parallax background scrolling system is broken. Background layers should scroll correctly relative to the camera and player movement: the farthest-back layer should be the smallest image and scroll slowest; the layer closest to the tiles should be the largest image and scroll fastest.
- actual answer: The broken part in the Project 1 starter code that students have to fix is the automated-grading concern raised with specific items and evidence in the course file "Course repo (eval snapshot) › p2-buzzer/rubric.md › Project 2: Buzzer — Rubric › R12 — TA Code Review (10 points)".

### q07 — llama3.2-1b-other-family
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Python style (ruff check backend/ scripts/), frontend type checking (tsc --noEmit on all three apps), and GitLab's built-in secret detection scan.
- actual answer: The checks that Project 2's CI pipeline runs before a merge request can be approved are:

1. Python style check
2. Frontend types check
3. Secret detection check

These checks are run on every merge request to ensure that the pipeline passes before the MR can be approved.

### q08 — llama3.2-1b-other-family
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Redis holds the ephemeral live state (current question, who has answered, scores) â€” fast, per-room, expires with the room. MySQL holds the permanent record â€” every answer is written to the database immediately.
- actual answer: The live game state in Buzzer's real-time architecture lives in **Redis**, while the permanent record of what happened is stored in **MySQL**.

### q09 — llama3.2-1b-other-family
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: Temperature controls how the model's probability distribution over the vocabulary gets sampled. Near 0.0 is nearly deterministic (the highest-probability token); around 0.7 is balanced with some variety while staying coherent; 1.5 and above is high randomness, more likely to go off the rails.
- actual answer: According to the context, temperature controls how a language model's output is sampled from the entire vocabulary. Specifically, it controls the probability distribution over the entire vocabulary, not one guaranteed next token.

Near temperature 0, the model outputs a probability distribution that is highly deterministic, with the highest-probability token being the one that is most likely to be correct. This is because the model is making predictions based on the same input prompt, and the same prompt can produce slightly different output across runs on different hardware.

In contrast, near temperature 1.5 or above, the model's output is more random and less deterministic, with a higher likelihood of producing hallucinations or incorrect outputs. This is because the model is making predictions based on a more diverse set of inputs, and the same prompt can produce a wide range of possible outputs.

### q10 — llama3.2-1b-other-family
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: No. Even at temperature 0.0, the same prompt can produce slightly different output across runs on different hardware, because parallelized floating-point matrix operations aren't perfectly associative â€” tiny rounding differences can flip which token is technically highest-probability in a near-tie.
- actual answer: The context only mentions that temperature 0.0 "Isn't Fully" deterministic, which means that even at temperature 0, the same prompt can produce slightly different output. There is no further information provided to determine if a language model is fully deterministic at temperature 0.

### q11 — llama3.2-1b-other-family
- matched: True (expected no-match: False)
- retrieval hit: True
- expected answer: No. Each model family trains its own tokenizer on its own vocabulary, so the same text produces a different token count on a different model â€” always count with the tokenizer for the model you're actually using.
- actual answer: A token count from one model's tokenizer does not transfer to a different model. The text explains that each model family trains its own tokenizer on its own vocabulary, so the same text produces a different token count on a different model.

### q12 — llama3.2-1b-other-family
- matched: True (expected no-match: False)
- retrieval hit: False
- expected answer: In development it's safe to nuke the volume and start clean: docker compose down -v (removes the MySQL volume), then docker compose up --build, then docker compose run --rm backend alembic upgrade head again. Don't do this against anything with data you care about â€” -v is destructive.
- actual answer: Based on the provided context, the safe way to reset a migration in development is to use the accepted answer:

"In development it's safe to nuke the volume and start clean: `docker compose down -v` (removes the MySQL volume), then `docker compose up --build`, then `docker compose run --rm backend alembic upgrade head` again. Don't do this against anything with data you care about — `-v` is destructive."

This method is safe because it:

* Removes the MySQL volume, which means any data is lost.
* Uses `--build` to rebuild the Alembic migrations, which ensures that the migrations are up-to-date.
* Uses `--rm` to remove the container after the upgrade, which prevents any accidental data from being left behind.

This approach is recommended in development because it allows you to start fresh with a clean slate, without risking data loss.

### q13 — llama3.2-1b-other-family
- matched: True (expected no-match: False)
- retrieval hit: False
- expected answer: CLAUDE.md is prose, auto-loaded at session start, for codebase overview/conventions/behavioral rules. .claude/settings.json is structured config â€” permissions, hooks, environment variables. There's no 'rules' field in settings.json; behavioral rules always belong in CLAUDE.md prose.
- actual answer: The actual difference between CLAUDE.md and .claude/settings.json is that CLAUDE.md is prose, which is auto-loaded at session start and contains codebase overview, conventions, and behavioral rules for Claude to read, while .claude/settings.json is structured config, which contains permissions, hooks, and environment variables.

### q14 — llama3.2-1b-other-family
- matched: False (expected no-match: True)
- retrieval hit: None
- expected answer: None
- actual answer: None

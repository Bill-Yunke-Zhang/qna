# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**QnA** is a Piazza-style course question-and-answer board. Students post questions, course staff (and other students) answer them, and every question is the root of a discussion thread that stays open until staff explicitly close it. There is currently **no AI component** — that is the assignment.

## Development Commands

### Docker Environment
```bash
docker compose up
docker compose up --build
docker compose down
docker compose logs -f [service_name]
docker compose exec backend [command]
```

### Backend (FastAPI / Python)
```bash
# Run inside the container or with venv active
alembic upgrade head
alembic revision --autogenerate -m "description"
pytest
ruff check .
ruff format .
```

### Frontend Applications
```bash
npm run dev            # all three apps concurrently
npm run dev:student
npm run dev:staff
npm run dev:admin
npm run build
```

### Scripts
```bash
python scripts/seed_demo.py
```

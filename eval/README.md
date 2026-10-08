# RAG Evaluation Kit (T6)

Everything in this directory is provided by course staff for **T6 — RAG Configuration Comparison**. You don't need to build any of this; you need to build the pipeline and the endpoint (T5, T6) that it drives.

## What's here

| Path | What it is |
|---|---|
| `sample_data/` | Real content, standing in for what your team's T4 ingestion would fetch from live URLs — a real course syllabus and schedule page (HTML), real markdown docs and a real slide deck PDF from a course repo. |
| `ground_truth.json` | 14 questions, each with the expected source and (for 13 of them) an expected answer, pulled directly from the files in `sample_data/`. Question `q14` is deliberately out-of-scope — nothing in the sample data answers it — to check that your pipeline correctly returns no match instead of guessing. |
| `configs.example.json` | A template defining your baseline configuration and one one-axis comparison per T6 axis. Copy it to `configs.json` and edit it. |
| `compare_harness.py` | Queries — never ingests — every question against your baseline, then against each one-axis comparison, via your `POST /api/courses/{course_id}/rag/compare` endpoint (see T6 in `instructions.md` for the exact contract), and writes `report.json` / `report.md`. |

## Why sample_data/ isn't fetched live

T6 is about comparing chunking/embedding/retrieval/generation *configurations* — not re-testing whether your URL-fetching or git-cloning code works, which is what T4 and T7 already cover. Ingesting `sample_data/` through T4's file-upload fallback path gets your pipeline real, messy, realistic content (actual production HTML with nav-bar noise to strip, real markdown structure, a real PDF) without needing live network access or a GitLab token during grading — which would make T6 fragile and non-reproducible.

## One-factor-at-a-time — this changes how you run the harness

T6 requires a controlled comparison: one fixed **baseline** configuration, and one **comparison** per axis that changes exactly that axis and nothing else. Chunking configuration (which can vary per resource type) and embedding model choice are decided when content is **ingested** — they're baked into what's stored in ChromaDB. Similarity threshold, system-prompt text and generation model are decided per **query**, with no re-ingestion needed. `compare_harness.py` only queries; it never ingests, and it never runs a blind cross product of profiles × variants — it runs exactly the baseline plus each comparison you define. That means the ingestion-time comparisons are a manual step you drive first, not something the harness automates end to end:

1. **Ingest `sample_data/` once per ingestion profile your comparisons need**, via your team's staff-facing upload UI, using T4's ingestion-profile mechanism (each profile is a separate, named copy of the ingested content — nothing gets overwritten):
   - `sample_data/web/syllabus.html` and `sample_data/web/schedule.html` — as syllabus / schedule resources
   - Everything under `sample_data/repo/` — as course-repository resources (`.md` and `.pdf` files)
   - Historical Q&A needs no action — it reads your board's own seeded threads directly (see `scripts/seed_demo.py` in the repo root), and isn't affected by ingestion profiles
   - At minimum, ingest three profiles: `"sliding-window"` + your baseline embedding model (your baseline), `"type-tailored"` + the same embedding model (isolates the chunking axis), and `"sliding-window"` + your alternate embedding model (isolates the embedding-model axis)
2. **Copy `configs.example.json` to `configs.json`.** Define `baseline` once (the ingestion profile, threshold, system prompt, and generation model everything else is measured against), then list one `comparisons` entry per axis, each overriding exactly one field away from baseline. Set `course_id`.
3. **Pull every generation model your `configs.json` names** into Ollama, on every machine you run against (your laptop and your deployed VM). The endpoint never pulls a model.
4. **Run the harness** — it queries the baseline once, then each comparison as baseline-with-one-override, with no re-ingestion in between:
   ```bash
   python eval/compare_harness.py
   ```
   It warns (without stopping) if a comparison in your `configs.json` changes more or fewer than one field from baseline — that's a sign the comparison won't isolate the axis it claims to.
5. **Read `eval/report.md`.** It gives you, per run (baseline and each comparison): a deterministic retrieval-hit rate (did the right source get retrieved?) and no-match accuracy (checked automatically), plus every question's actual vs. expected answer side by side (for you to judge response quality — see T6, this is intentionally not auto-scored) and the raw CPU/runtime metrics your endpoint reported. The system-prompt and generation-model comparisons retrieve exactly what the baseline retrieves, so their hit rate and no-match accuracy match baseline; their whole effect is in the answers and the generation time.

All five of T6's axes must be represented as a one-axis comparison against the same baseline — this intentionally won't show you interaction effects between axes (see T6), only each axis's isolated effect.

## Running against your deployment

Grading re-runs this harness against your deployed application (T9), so run it there yourself first. Your local `.env` holds your development password, so pass the deployment's values with the `HARNESS_` prefix, which always wins over `.env`:

```bash
HARNESS_BASE_URL=http://<your-static-ip> HARNESS_ADMIN_PASSWORD='<the VM's admin password>' \
    python eval/compare_harness.py
```

The deployment needs its own copy of everything the comparison uses: the ingested profiles and the pulled generation models. See Part 8 of `deployment_instructions.md`.

## Commit the report — it's evidence, not a scratch file

`report.json`/`report.md` are a required deliverable (T6, and the Submission checklist) — commit them, don't gitignore them. **Grading independently re-runs this exact, unmodified script against your team's own running application** and compares the fresh output to what you submitted. If your write-up's claims (T10) don't match a clean re-run of your own harness against your own system, that's exactly the kind of thing that gets raised at your TA code review (T11).

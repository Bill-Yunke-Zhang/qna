#!/usr/bin/env python3
"""
RAG configuration comparison harness (T6).

Runs every question in ground_truth.json against your team's baseline
configuration, then against each one-axis comparison in configs.json, via
your POST /api/courses/{course_id}/rag/compare endpoint (the fixed contract
specified in instructions.md T6), and writes a structured report you can use
to write up which side of each comparison performed better.

This is a controlled, one-factor-at-a-time (OFAT) evaluation, not a full
cross product: every comparison changes exactly one field away from the
shared baseline, holding the other four axes fixed, so any difference in
results is attributable to that one axis — see instructions.md T6. This
script warns (but does not refuse to run) if a comparison entry in
configs.json changes zero or more than one field, since that silently
breaks the guarantee the whole design depends on.

Two kinds of axes, handled differently — see instructions.md T6:
  - Ingestion-time axes (chunking configuration, embedding model) are baked
    in when content is ingested. This harness does NOT ingest anything — it
    only queries. Before running it, ingest eval/sample_data/ once per
    ingestion profile your comparisons need, through your own staff UI's T4
    ingestion-profile mechanism.
  - Query-time axes (similarity threshold, system-prompt text, generation
    model) need no re-ingestion. This harness applies those directly, per
    call. Every generation model named in configs.json must already be
    pulled into Ollama.

This script is a skeleton, not a finished evaluator: it drives your endpoint
and computes a simple, deterministic retrieval-accuracy signal (did any
retrieved chunk come from the expected source?) and reports raw metrics —
but final *response quality* is left for you to read and judge from the
report, per T6 (no LLM-as-judge scoring is required).

Setup:
    1. Ingest eval/sample_data/ into a course, once per ingestion profile
       your comparisons need (via T4's ingestion-profile mechanism) — see
       eval/README.md. At minimum: your baseline profile, the chunking
       comparison's profile, and the embedding-model comparison's profile.
    2. Copy eval/configs.example.json to eval/configs.json: define your
       `baseline` once, then list one `comparisons` entry per axis, each
       overriding exactly one field away from baseline.
    3. Run this script; read eval/report.json and eval/report.md.
    4. Commit both report files — they're required evidence (T6), and your
       committed report will be independently reproduced at grading time by
       re-running this same script against your running application.

Usage:
    python eval/compare_harness.py

Optional settings, read from .env, then the environment (defaults shown):
    BASE_URL        http://localhost:8000
    ADMIN_USERNAME  admin
    ADMIN_PASSWORD  change_me_admin

Running against your deployment: your local .env holds your development
password, so name the deployment's values with the HARNESS_ prefix, which
always wins over .env:
    HARNESS_BASE_URL=http://<your-static-ip> HARNESS_ADMIN_PASSWORD='<the VM's admin password>' \
        python eval/compare_harness.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx

EVAL_DIR = Path(__file__).parent
REPO_ROOT = EVAL_DIR.parent

OVERRIDABLE_FIELDS = ("ingestion_profile", "similarity_threshold", "system_prompt", "generation_model")


# HARNESS_<KEY> on the command line overrides .env and the environment for KEY.
OVERRIDES = {k[len("HARNESS_"):]: v for k, v in os.environ.items() if k.startswith("HARNESS_")}


def _env_value(key: str, default: str) -> str:
    """
    Read `key` from a variable set on the command line (see "Running against
    your deployment" above), then from .env, then fall back to `default`.
    Reading .env directly (rather than relying solely on os.getenv) means this
    works whether or not the venv was activated in this shell — a script run
    without that step would otherwise silently fall back to the hardcoded
    default instead of your real admin password, producing a confusing 401
    unrelated to your actual RAG work.
    """
    if key in OVERRIDES:
        return OVERRIDES[key]
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                if k.strip() == key:
                    return v.strip()
    return os.environ.get(key, default)


BASE_URL = _env_value("BASE_URL", "http://localhost:8000").rstrip("/")
ADMIN_USERNAME = _env_value("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = _env_value("ADMIN_PASSWORD", "change_me_admin")
GROUND_TRUTH_PATH = EVAL_DIR / "ground_truth.json"
CONFIGS_PATH = EVAL_DIR / "configs.json"
REPORT_JSON_PATH = EVAL_DIR / "report.json"
REPORT_MD_PATH = EVAL_DIR / "report.md"

G = "\033[92m✓\033[0m"
X = "\033[91m✗\033[0m"
AR = "\033[94m→\033[0m"
WARN = "\033[93m!\033[0m"


def login(client: httpx.Client) -> str:
    resp = client.post(
        f"{BASE_URL}/api/auth/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def load_json(path: Path) -> dict:
    if not path.exists():
        sys.exit(
            f"✗ {path} not found.\n"
            f"  {'Copy configs.example.json to configs.json and edit it.' if path == CONFIGS_PATH else ''}"
        )
    return json.loads(path.read_text())


def resolve_runs(baseline: dict, comparisons: list[dict]) -> list[tuple[str, dict]]:
    """
    Build the ordered list of (label, config) runs: the baseline itself,
    then each comparison resolved as baseline-with-overrides. Warns (does
    not raise) if a comparison changes a field count other than exactly 1 —
    that's what makes it a one-factor-at-a-time comparison in the first
    place, and configs.json is hand-edited, so it's easy to get wrong.
    """
    runs = [("baseline", dict(baseline))]
    for comp in comparisons:
        label = comp.get("label", "unlabeled")
        changed = [f for f in OVERRIDABLE_FIELDS if f in comp and comp[f] != baseline[f]]
        if len(changed) != 1:
            print(
                f"{WARN} comparison '{label}' changes {len(changed)} field(s) from "
                f"baseline ({changed or 'none'}), not exactly 1 — this breaks the "
                f"one-factor-at-a-time guarantee T6 asks for.",
                file=sys.stderr,
            )
        resolved = dict(baseline)
        resolved.update({f: comp[f] for f in OVERRIDABLE_FIELDS if f in comp})
        runs.append((label, resolved))
    return runs


def retrieval_hit(expected_source: str | None, retrieved_chunks: list[dict]) -> bool | None:
    """
    A simple, deterministic retrieval-accuracy signal: did any retrieved
    chunk's source_url reference the expected source file/URL? Returns None
    for the no-match ground-truth entries, where "hit" isn't a meaningful
    concept — those are checked separately (see `matched` in the report).
    """
    if expected_source is None:
        return None
    return any(expected_source in (chunk.get("source_url") or "") for chunk in retrieved_chunks)


def run_one(client: httpx.Client, course_id: int, question: dict, label: str, config: dict) -> dict:
    body = {
        "question": question["question"],
        "ingestion_profile": config["ingestion_profile"],
        "similarity_threshold": config["similarity_threshold"],
        "system_prompt": config["system_prompt"],
        "generation_model": config["generation_model"],
    }
    started = time.perf_counter()
    resp = client.post(f"{BASE_URL}/api/courses/{course_id}/rag/compare", json=body, timeout=180)
    wall_ms = (time.perf_counter() - started) * 1000
    resp.raise_for_status()
    result = resp.json()

    expects_no_match = question["resource_type"] == "no_match"
    matched = result.get("matched", False)

    return {
        "question_id": question["id"],
        "label": label,
        "config": {k: config[k] for k in OVERRIDABLE_FIELDS},
        "matched": matched,
        "expected_no_match": expects_no_match,
        "no_match_correct": (matched is False) if expects_no_match else None,
        "retrieval_hit": retrieval_hit(question.get("expected_source"), result.get("retrieved_chunks", [])),
        "answer": result.get("answer"),
        "expected_answer": question.get("expected_answer"),
        "retrieved_chunks": result.get("retrieved_chunks", []),
        "metrics": result.get("metrics", {}),
        "wall_clock_ms": round(wall_ms, 1),
    }


def summarize(results: list[dict]) -> dict:
    by_label: dict[str, list[dict]] = {}
    for r in results:
        by_label.setdefault(r["label"], []).append(r)

    summary = {}
    for label, rows in by_label.items():
        scored = [r for r in rows if r["retrieval_hit"] is not None]
        no_match_rows = [r for r in rows if r["expected_no_match"]]
        summary[label] = {
            "config": rows[0]["config"],
            "questions": len(rows),
            "retrieval_hit_rate": (
                sum(1 for r in scored if r["retrieval_hit"]) / len(scored) if scored else None
            ),
            "no_match_accuracy": (
                sum(1 for r in no_match_rows if r["no_match_correct"]) / len(no_match_rows)
                if no_match_rows
                else None
            ),
            "avg_wall_clock_ms": round(sum(r["wall_clock_ms"] for r in rows) / len(rows), 1),
            "avg_generation_time_ms": round(
                sum(r["metrics"].get("generation_time_ms", 0) for r in rows) / len(rows), 1
            ),
            "avg_cpu_percent": round(
                sum(r["metrics"].get("cpu_percent", 0) for r in rows) / len(rows), 1
            ),
        }
    return summary


def write_markdown_report(results: list[dict], summary: dict) -> None:
    lines = ["# RAG Configuration Comparison Report", ""]
    lines.append("## Summary — baseline vs. each one-axis comparison")
    lines.append("")
    lines.append("| Run | Ingestion profile | Threshold | System prompt (first 40 chars) | Generation model | Retrieval hit rate | No-match accuracy | Avg wall-clock (ms) | Avg generation (ms) | Avg CPU % |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for label, s in summary.items():
        cfg = s["config"]
        hit = f"{s['retrieval_hit_rate']:.0%}" if s["retrieval_hit_rate"] is not None else "n/a"
        nomatch = f"{s['no_match_accuracy']:.0%}" if s["no_match_accuracy"] is not None else "n/a"
        prompt_preview = (cfg["system_prompt"][:40] + "…") if len(cfg["system_prompt"]) > 40 else cfg["system_prompt"]
        lines.append(
            f"| {label} | {cfg['ingestion_profile']} | {cfg['similarity_threshold']} | {prompt_preview} "
            f"| {cfg['generation_model']} | {hit} | {nomatch} | {s['avg_wall_clock_ms']} "
            f"| {s['avg_generation_time_ms']} | {s['avg_cpu_percent']} |"
        )

    lines.append("")
    lines.append("## Per-question detail (read these to judge response quality yourself)")
    lines.append("")
    for r in results:
        lines.append(f"### {r['question_id']} — {r['label']}")
        lines.append(f"- matched: {r['matched']} (expected no-match: {r['expected_no_match']})")
        lines.append(f"- retrieval hit: {r['retrieval_hit']}")
        lines.append(f"- expected answer: {r['expected_answer']}")
        lines.append(f"- actual answer: {r['answer']}")
        lines.append("")

    REPORT_MD_PATH.write_text("\n".join(lines))


def main() -> None:
    ground_truth = load_json(GROUND_TRUTH_PATH)
    configs_doc = load_json(CONFIGS_PATH)
    course_id = configs_doc["course_id"]
    runs = resolve_runs(configs_doc["baseline"], configs_doc["comparisons"])

    total_calls = len(runs) * len(ground_truth["questions"])
    print(
        f"\n{AR} RAG comparison harness — baseline + {len(runs) - 1} one-axis comparison(s) x "
        f"{len(ground_truth['questions'])} question(s) = {total_calls} calls\n"
    )

    with httpx.Client(timeout=15) as client:
        token = login(client)
        client.headers["Authorization"] = f"Bearer {token}"

        results = []
        for label, config in runs:
            print(f"{AR} {label}")
            for question in ground_truth["questions"]:
                result = run_one(client, course_id, question, label, config)
                status = G if (result["retrieval_hit"] or result["no_match_correct"]) else X
                print(f"  {status} {question['id']}: {question['question'][:60]}")
                results.append(result)

    summary = summarize(results)
    REPORT_JSON_PATH.write_text(json.dumps({"results": results, "summary": summary}, indent=2))
    write_markdown_report(results, summary)

    print(f"\n{AR} Wrote {REPORT_JSON_PATH.name} and {REPORT_MD_PATH.name}\n")


if __name__ == "__main__":
    try:
        main()
    except httpx.HTTPStatusError as exc:
        print(f"\n✗ HTTP {exc.response.status_code}: {exc.response.text}", file=sys.stderr)
        sys.exit(1)
    except httpx.ConnectError:
        print(f"\n✗ Could not connect to {BASE_URL}. Is the Docker stack running?", file=sys.stderr)
        sys.exit(1)

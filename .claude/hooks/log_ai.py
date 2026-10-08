#!/usr/bin/env python3
"""
Claude Code AI Logger Hook
Captures user prompts and session summaries, commits them to ai_log/.

Usage (configured in .claude/settings.json):
  UserPromptSubmit → python3 .claude/hooks/log_ai.py prompt
  Stop             → python3 .claude/hooks/log_ai.py stop
"""

import json
import os
import sys
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

# Use the OS temp directory rather than a hardcoded "/tmp". On Windows,
# "/tmp/..." resolves to <current drive>:\tmp, which normally does not exist.
TEMP_PROMPTS_FILE = os.path.join(tempfile.gettempdir(), "claude_ai_prompts.json")


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def load_temp_prompts() -> dict:
    try:
        with open(TEMP_PROMPTS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_temp_prompts(data: dict):
    with open(TEMP_PROMPTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)


def parse_transcript(transcript_path: str) -> dict:
    """
    Parse a Claude Code JSONL transcript and extract:
      - The latest user message text
      - All tool calls with their inputs
      - Claude's final assistant text response

    Claude Code transcript entries look like:
      {"type": "assistant", "message": {"role": "assistant", "content": [...]}, ...}
      {"type": "user",      "message": {"role": "user",      "content": [...]}, ...}

    Older / alternate formats may have role/content at the top level, so we
    try both layouts.
    """
    tool_calls = []
    assistant_texts = []
    user_messages = []

    try:
        # Transcripts are UTF-8. Without an explicit encoding, Python uses the
        # system codepage on Windows (GBK, cp1252, ...) and fails to decode.
        with open(transcript_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if not isinstance(entry, dict):
                    continue

                # ── Resolve role & content ────────────────────────────────
                # Primary layout: {type, message: {role, content}}
                msg = entry.get("message")
                if isinstance(msg, dict):
                    role = msg.get("role", "")
                    content = msg.get("content", [])
                else:
                    # Fallback: role/content at top level
                    role = entry.get("role", "")
                    content = entry.get("content", [])
                # ─────────────────────────────────────────────────────────

                # Content can be a plain string
                if isinstance(content, str):
                    if role == "user":
                        user_messages.append(content)
                    elif role == "assistant":
                        assistant_texts.append(content)
                    continue

                if not isinstance(content, list):
                    continue

                for block in content:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type", "")

                    if role == "user" and btype == "text":
                        text = block.get("text", "").strip()
                        if text:
                            user_messages.append(text)

                    elif role == "assistant" and btype == "text":
                        text = block.get("text", "").strip()
                        if text:
                            assistant_texts.append(text)

                    elif btype == "tool_use":
                        name = block.get("name", "unknown")
                        inp = block.get("input", {})
                        tool_calls.append({"tool": name, "input": inp})

    except FileNotFoundError:
        pass

    return {
        "user_messages": user_messages,
        "tool_calls": tool_calls,
        "final_response": assistant_texts[-1] if assistant_texts else "",
    }


def summarise_tool_calls(tool_calls: list) -> list[str]:
    """Return human-readable bullet lines for each tool call."""
    lines = []
    for tc in tool_calls:
        tool = tc["tool"]
        inp = tc["input"]

        if tool == "Bash":
            cmd = inp.get("command", "").strip().replace("\n", " ")
            lines.append(f"- **Bash:** `{cmd[:120]}`")
        elif tool in ("Write", "Create"):
            fp = inp.get("file_path", inp.get("path", "?"))
            lines.append(f"- **{tool}:** `{fp}`")
        elif tool in ("Edit", "MultiEdit", "StrReplace"):
            fp = inp.get("file_path", inp.get("path", "?"))
            lines.append(f"- **Edit:** `{fp}`")
        elif tool == "Read":
            fp = inp.get("file_path", inp.get("path", "?"))
            lines.append(f"- **Read:** `{fp}`")
        elif tool in ("Glob", "Grep"):
            pattern = inp.get("pattern", inp.get("glob", "?"))
            lines.append(f"- **{tool}:** `{pattern}`")
        elif tool == "WebFetch":
            url = inp.get("url", "?")
            lines.append(f"- **WebFetch:** {url}")
        elif tool == "WebSearch":
            q = inp.get("query", "?")
            lines.append(f"- **WebSearch:** {q}")
        else:
            lines.append(f"- **{tool}:** {json.dumps(inp)[:100]}")
    return lines


def write_log(log_dir: Path, session_id: str, prompt: str, parsed: dict):
    """Write the markdown log file."""
    log_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    short_id = session_id[:8] if session_id else "unknown"
    filename = log_dir / f"{ts}_{short_id}.md"

    tool_lines = summarise_tool_calls(parsed["tool_calls"])
    tool_section = "\n".join(tool_lines) if tool_lines else "_No tools used._"

    # Trim the final response for the log (cap at ~1 000 chars)
    final = parsed["final_response"].strip()
    if len(final) > 1000:
        final = final[:1000] + "\n\n_(truncated — see full transcript for details)_"

    content = f"""# AI Session Log

**Date:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Session ID:** `{session_id}`

---

## User Prompt

{prompt.strip()}

---

## Tools Used

{tool_section}

---

## AI Summary

{final if final else "_No summary available._"}
"""

    filename.write_text(content, encoding="utf-8")
    return filename


def git_commit(repo_root: Path, log_file: Path):
    """Stage the log file and commit to the current branch."""
    rel = log_file.relative_to(repo_root)

    def run(cmd, **kwargs):
        return subprocess.run(
            cmd, cwd=str(repo_root), capture_output=True, text=True, **kwargs
        )

    # Check we're inside a git repo
    result = run(["git", "rev-parse", "--is-inside-work-tree"])
    if result.returncode != 0:
        print("Not a git repo — skipping commit/push.", file=sys.stderr)
        return

    run(["git", "add", str(rel)])
    # Also stage the .gitkeep so ai_log/ is always tracked
    gitkeep = repo_root / "ai_log" / ".gitkeep"
    if gitkeep.exists():
        run(["git", "add", str(gitkeep.relative_to(repo_root))])

    commit_msg = f"ai_log: record session {log_file.stem}"
    result = run(["git", "commit", "-m", commit_msg])
    if result.returncode != 0:
        print(result.stderr.strip() or "Nothing to commit.", file=sys.stderr)
        return

    print(f"✅ ai_log committed: {rel}", file=sys.stderr)


# ──────────────────────────────────────────────
# Entry points
# ──────────────────────────────────────────────

def handle_prompt():
    """Called on UserPromptSubmit — save the prompt for later."""
    data = json.loads(sys.stdin.read())
    session_id = data.get("session_id", "")
    prompt = data.get("prompt", "").strip()

    if prompt and session_id:
        store = load_temp_prompts()
        store[session_id] = prompt
        save_temp_prompts(store)


def handle_stop():
    """Called on Stop — write the log, commit, and push."""
    data = json.loads(sys.stdin.read())

    # Avoid re-triggering if a Stop hook is already running
    if data.get("stop_hook_active"):
        return

    session_id = data.get("session_id", "")
    transcript_path = data.get("transcript_path", "")
    cwd = data.get("cwd", os.getcwd())
    repo_root = Path(cwd)
    log_dir = repo_root / "ai_log"

    # Retrieve the prompt saved during UserPromptSubmit
    store = load_temp_prompts()
    prompt = store.pop(session_id, "_(prompt not captured)_")
    save_temp_prompts(store)  # remove used entry

    parsed = parse_transcript(transcript_path)

    # Fall back to transcript's first user message if prompt wasn't captured
    if prompt == "_(prompt not captured)_" and parsed["user_messages"]:
        prompt = parsed["user_messages"][0]

    log_file = write_log(log_dir, session_id, prompt, parsed)
    git_commit(repo_root, log_file)


def handle_debug():
    """
    Debug helper — parse a transcript and print what was extracted.
    Usage:  python3 log_ai.py debug /path/to/transcript.jsonl
    """
    if len(sys.argv) < 3:
        print("Usage: python3 log_ai.py debug <transcript_path>", file=sys.stderr)
        sys.exit(1)
    transcript_path = sys.argv[2]
    parsed = parse_transcript(transcript_path)
    print(f"User messages found : {len(parsed['user_messages'])}")
    for i, m in enumerate(parsed["user_messages"], 1):
        print(f"  [{i}] {m[:120]}")
    print(f"\nTool calls found    : {len(parsed['tool_calls'])}")
    for tc in parsed["tool_calls"]:
        print(f"  {tc['tool']} — {str(tc['input'])[:80]}")
    print(f"\nFinal response      : {parsed['final_response'][:300] if parsed['final_response'] else '(none)'}")


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if action == "prompt":
            handle_prompt()
        elif action == "stop":
            handle_stop()
        elif action == "debug":
            handle_debug()
        else:
            print(f"Unknown action: {action}", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        # Never crash loudly — hooks should be transparent
        print(f"[log_ai.py] Error: {e}", file=sys.stderr)

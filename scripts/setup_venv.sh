#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# setup_venv.sh — create and configure the Python virtual environment
#
# Supported: macOS and Linux (bash required).
# Windows:   Use WSL or Git Bash, or follow the manual steps in README.md.
#
# Run once after cloning the repo (from the project root):
#   bash scripts/setup_venv.sh
#
# After this, simply activating the venv also loads all .env variables:
#   source .venv/bin/activate
# ---------------------------------------------------------------------------

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# ---------------------------------------------------------------------------
# Pick a Python interpreter. The backend's Docker image always runs 3.12
# regardless of what's used here — this venv is only for local tooling
# (scripts, tests, alembic commands run outside Docker), so any 3.10+
# interpreter works. Prefer 3.12 for the closest match if it's available.
# ---------------------------------------------------------------------------
PYTHON=""
for candidate in python3.12 python3.13 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PYTHON="$candidate"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "✗ No python3 interpreter found on PATH. Install Python 3.10+ and re-run." >&2
    exit 1
fi

version="$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
major="${version%%.*}"
minor="${version##*.}"
if [ "$major" -lt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -lt 10 ]; }; then
    echo "✗ Found $PYTHON (Python $version), but this project needs 3.10+." >&2
    exit 1
fi

echo "→ Creating virtual environment (.venv) with $PYTHON (Python $version) …"
"$PYTHON" -m venv .venv

echo "→ Installing dependencies …"
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r backend/requirements.txt
.venv/bin/pip install --quiet -r tests/integration/requirements.txt

# ---------------------------------------------------------------------------
# Patch the activate script so that sourcing it also loads .env.
# Uses $VIRTUAL_ENV (set by activate itself) to locate the project root,
# so it works regardless of where the developer runs 'source .venv/bin/activate'.
# ---------------------------------------------------------------------------
echo "→ Patching activate script to auto-load .env …"
cat >> .venv/bin/activate << 'PATCH'

# Load project .env variables whenever the venv is activated.
if [ -f "$VIRTUAL_ENV/../.env" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$VIRTUAL_ENV/../.env"
    set +a
fi
PATCH

echo ""
echo "✓ Done!  Activate the environment with:"
echo ""
echo "    source .venv/bin/activate"
echo ""
echo "  Your .env variables (ADMIN_USERNAME, ADMIN_PASSWORD, etc.) will load"
echo "  automatically every time you activate the venv."
echo ""

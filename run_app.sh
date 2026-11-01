#!/usr/bin/env bash
# One-command launcher for macOS/Linux: creates a private environment, installs packages, starts the app.
set -e
cd "$(dirname "$0")"
PY=$(command -v python3.11 || command -v python3 || true)
[ -n "$PY" ] || { echo "Python 3.11+ not found. Install it from https://www.python.org/downloads/"; exit 1; }
[ -x .venv/bin/python ] || "$PY" -m venv .venv
if ! cmp -s requirements.txt .venv/requirements.installed; then
  .venv/bin/python -m pip install --upgrade pip >/dev/null
  .venv/bin/python -m pip install -r requirements.txt
  cp requirements.txt .venv/requirements.installed
fi
[ -f .env ] || { [ -f .env.example ] && cp .env.example .env; }
command -v ffmpeg >/dev/null || echo "ffmpeg is missing: install it (Mac: brew install ffmpeg; Linux: sudo apt install ffmpeg)."
exec .venv/bin/python -m streamlit run app.py --server.headless=false --browser.gatherUsageStats=false

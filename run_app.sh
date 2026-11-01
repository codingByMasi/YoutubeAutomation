#!/usr/bin/env bash
# One-command launcher for macOS/Linux: creates a private environment, installs packages, starts the app.
set -e
cd "$(dirname "$0")"
PY=$(command -v python3.11 || command -v python3 || true)
[ -n "$PY" ] || { echo "Python 3.11+ not found. Install it from https://www.python.org/downloads/"; exit 1; }
"$PY" -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" \
  || { echo "Python 3.11 or newer is needed (found $("$PY" -V)). Install it from https://www.python.org/downloads/"; exit 1; }
[ -x .venv/bin/python ] || "$PY" -m venv .venv
if ! cmp -s requirements.txt .venv/requirements.installed; then
  echo "Installing packages. This takes a few minutes the first time. Please wait..."
  .venv/bin/python -m pip install --upgrade pip >/dev/null 2>&1 || true
  .venv/bin/python -m pip install -r requirements.txt \
    || { echo "Installing packages failed. Check your internet connection and run ./run_app.sh again."; exit 1; }
  cp requirements.txt .venv/requirements.installed
fi
if [ ! -f .env ]; then
  if [ -f .env.example ]; then cp .env.example .env; else echo "LLM_PROVIDER=claude_code" > .env; fi
fi
# Streamlit asks for an email on its first run and waits forever. Answer it up front.
if [ ! -f "$HOME/.streamlit/credentials.toml" ]; then
  mkdir -p "$HOME/.streamlit"
  printf '[general]\nemail = ""\n' > "$HOME/.streamlit/credentials.toml"
fi
export STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
command -v ffmpeg >/dev/null || echo "ffmpeg is missing: install it (Mac: brew install ffmpeg; Linux: sudo apt install ffmpeg)."
exec .venv/bin/python -m streamlit run app.py --server.headless=false --browser.gatherUsageStats=false

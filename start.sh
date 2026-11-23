#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required. Install Python 3, then run this script again." >&2
  exit 1
fi

if [[ ! -x .venv/bin/python ]]; then
  echo "Creating the app's Python environment…"
  python3 -m venv .venv
fi

echo "Checking backend dependencies…"
.venv/bin/python -m pip install --disable-pip-version-check -r backend/requirements.txt

export HOST="${HOST:-127.0.0.1}"
export PORT="${PORT:-8000}"
OPEN_HOST="$HOST"
if [[ "$OPEN_HOST" == "0.0.0.0" || "$OPEN_HOST" == "::" ]]; then
  OPEN_HOST="127.0.0.1"
fi
APP_URL="http://${OPEN_HOST}:${PORT}"

echo "Starting Noisy Cell Counter (backend and frontend)…"
echo "Open ${APP_URL} if it does not open automatically. Press Ctrl+C to stop."

python_pid=""
cleanup() {
  if [[ -n "$python_pid" ]] && kill -0 "$python_pid" 2>/dev/null; then
    kill "$python_pid" 2>/dev/null || true
    wait "$python_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

.venv/bin/python backend/app.py &
python_pid=$!

if [[ "${NO_OPEN:-0}" != "1" ]] && command -v open >/dev/null 2>&1; then
  (
    for _ in {1..30}; do
      if ! kill -0 "$python_pid" 2>/dev/null; then exit 0; fi
      if curl --silent --fail "${APP_URL}/healthz" >/dev/null; then
        open "$APP_URL"
        exit 0
      fi
      sleep 1
    done
  ) >/dev/null 2>&1 &
fi

wait "$python_pid"

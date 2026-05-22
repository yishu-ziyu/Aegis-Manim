#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${AEGIS_LOCAL_VENV:-$ROOT_DIR/.aegis-local-venv}"
if [[ "$VENV_DIR" != /* ]]; then
  VENV_DIR="$ROOT_DIR/$VENV_DIR"
fi
WEB_HOST="${AEGIS_WEB_HOST:-127.0.0.1}"
WEB_PORT="${AEGIS_WEB_PORT:-8000}"
RENDER_PORT="${AEGIS_RENDER_PORT:-5001}"
WEB_URL="http://${WEB_HOST}:${WEB_PORT}"

export MANIM_API_KEY="${MANIM_API_KEY:-dev-key-change-in-production}"
export RENDER_BACKEND_URL="http://127.0.0.1:${RENDER_PORT}"
export AEGIS_CLOUD_GENERATE_URL="${AEGIS_CLOUD_GENERATE_URL:-https://manim-main.vercel.app/api/generate}"
export PYTHONUNBUFFERED=1

cleanup() {
  if [[ -n "${WEB_PID:-}" ]]; then kill "$WEB_PID" >/dev/null 2>&1 || true; fi
  if [[ -n "${RENDER_PID:-}" ]]; then kill "$RENDER_PID" >/dev/null 2>&1 || true; fi
}
trap cleanup EXIT INT TERM

echo "Aegis local launcher"
echo "Project: $ROOT_DIR"
echo

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3 was not found. Install Python 3, then run this launcher again."
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg was not found. Install ffmpeg first, for example: brew install ffmpeg"
  exit 1
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "Creating local Python environment..."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

echo "Installing/updating local render dependencies..."
"$VENV_DIR/bin/python" -m pip install --upgrade pip >/dev/null
"$VENV_DIR/bin/python" -m pip install -r render_backend/requirements.txt

echo
echo "Starting local render backend on http://127.0.0.1:${RENDER_PORT} ..."
(
  cd "$ROOT_DIR/render_backend"
  PORT="$RENDER_PORT" "$VENV_DIR/bin/python" app.py
) &
RENDER_PID=$!

echo "Starting local Aegis Web on ${WEB_URL} ..."
"$VENV_DIR/bin/python" core/web_app.py --host "$WEB_HOST" --port "$WEB_PORT" &
WEB_PID=$!

echo "Waiting for local services..."
for _ in {1..60}; do
  if curl -fsS "http://127.0.0.1:${RENDER_PORT}/health" >/dev/null 2>&1 \
    && curl -fsS "${WEB_URL}/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! curl -fsS "http://127.0.0.1:${RENDER_PORT}/health" >/dev/null 2>&1; then
  echo "Render backend did not become healthy. See the terminal output above."
  exit 1
fi
if ! curl -fsS "${WEB_URL}/api/health" >/dev/null 2>&1; then
  echo "Aegis Web did not become healthy. See the terminal output above."
  exit 1
fi

echo
echo "Ready: ${WEB_URL}"
echo "Generation uses the configured cloud trial endpoint; rendering uses this computer."

if command -v open >/dev/null 2>&1; then
  open "$WEB_URL"
fi

wait "$WEB_PID"

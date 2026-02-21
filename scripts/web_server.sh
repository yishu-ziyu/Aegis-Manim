#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT_DIR/.aegis_web.pid"
LOG_FILE="${AEGIS_WEB_LOG_FILE:-/tmp/aegis_web_live.log}"
HOST="${AEGIS_WEB_HOST:-127.0.0.1}"
PORT="${AEGIS_WEB_PORT:-8000}"

resolve_python() {
  if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
    printf '%s' "$ROOT_DIR/.venv/bin/python"
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return
  fi
  echo "Error: no python runtime found (.venv/bin/python or python3)." >&2
  exit 1
}

is_running() {
  if [[ ! -f "$PID_FILE" ]]; then
    return 1
  fi
  local pid
  pid="$(cat "$PID_FILE")"
  if [[ -z "$pid" ]]; then
    return 1
  fi
  if kill -0 "$pid" >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

start_server() {
  if is_running; then
    echo "Aegis Web already running (pid $(cat "$PID_FILE"))."
    return 0
  fi

  local py_bin
  py_bin="$(resolve_python)"
  (
    cd "$ROOT_DIR"
    nohup "$py_bin" core/web_app.py --host "$HOST" --port "$PORT" >"$LOG_FILE" 2>&1 &
    echo $! >"$PID_FILE"
  )
  sleep 1
  if is_running; then
    echo "Aegis Web started at http://$HOST:$PORT (pid $(cat "$PID_FILE"))."
    echo "Log: $LOG_FILE"
    return 0
  fi

  echo "Failed to start Aegis Web. Recent log:"
  tail -n 80 "$LOG_FILE" 2>/dev/null || true
  rm -f "$PID_FILE"
  return 1
}

stop_server() {
  if ! is_running; then
    echo "Aegis Web is not running."
    rm -f "$PID_FILE"
    return 0
  fi
  local pid
  pid="$(cat "$PID_FILE")"
  kill "$pid" >/dev/null 2>&1 || true
  sleep 1
  if kill -0 "$pid" >/dev/null 2>&1; then
    kill -9 "$pid" >/dev/null 2>&1 || true
  fi
  rm -f "$PID_FILE"
  echo "Aegis Web stopped."
}

status_server() {
  if is_running; then
    local pid
    pid="$(cat "$PID_FILE")"
    echo "Aegis Web is running (pid $pid) at http://$HOST:$PORT"
    return 0
  fi
  echo "Aegis Web is not running."
  return 1
}

usage() {
  cat <<'EOF'
Usage:
  ./scripts/web_server.sh start
  ./scripts/web_server.sh stop
  ./scripts/web_server.sh status
  ./scripts/web_server.sh restart

Optional env:
  AEGIS_WEB_HOST=127.0.0.1
  AEGIS_WEB_PORT=8000
  AEGIS_WEB_LOG_FILE=/tmp/aegis_web_live.log
EOF
}

action="${1:-}"
case "$action" in
  start)
    start_server
    ;;
  stop)
    stop_server
    ;;
  status)
    status_server
    ;;
  restart)
    stop_server
    start_server
    ;;
  *)
    usage
    exit 1
    ;;
esac

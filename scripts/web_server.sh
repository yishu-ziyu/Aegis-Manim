#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT_DIR/.aegis_web.pid"
LOG_FILE="${AEGIS_WEB_LOG_FILE:-/tmp/aegis_web_live.log}"
HOST="${AEGIS_WEB_HOST:-127.0.0.1}"
PORT="${AEGIS_WEB_PORT:-8000}"

# 渲染后端（Flask）与 Web 服务一并管理；AEGIS_WITH_RENDER=0 可只跑 Web。
# 端口与 core/web_app.py 的 RENDER_BACKEND_URL 默认值（http://127.0.0.1:5001）对齐。
RENDER_PID_FILE="$ROOT_DIR/.aegis_render.pid"
RENDER_LOG_FILE="${AEGIS_RENDER_LOG_FILE:-/tmp/aegis_render_live.log}"
RENDER_PORT="${AEGIS_RENDER_PORT:-5001}"
WITH_RENDER="${AEGIS_WITH_RENDER:-1}"

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

is_render_running() {
  if [[ ! -f "$RENDER_PID_FILE" ]]; then
    return 1
  fi
  local pid
  pid="$(cat "$RENDER_PID_FILE")"
  if [[ -z "$pid" ]]; then
    return 1
  fi
  if kill -0 "$pid" >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

start_render_backend() {
  if [[ "$WITH_RENDER" != "1" ]]; then
    echo "Render backend disabled (AEGIS_WITH_RENDER=0)."
    return 0
  fi
  if is_render_running; then
    echo "Render backend already running (pid $(cat "$RENDER_PID_FILE"))."
    return 0
  fi
  local py_bin
  py_bin="$(resolve_python)"
  if ! "$py_bin" -c "import flask, flask_cors" >/dev/null 2>&1; then
    echo "Render backend skipped: flask/flask_cors not available in $py_bin (install render_backend/requirements.txt, or AEGIS_WITH_RENDER=0 to silence)."
    return 0
  fi
  # 后端只认 MANIM_API_KEY，而 core/web_app.py 发送的是 RENDER_BACKEND_API_KEY
  # （.env 可定义，回退 MANIM_API_KEY，再回退开发默认值）。两侧必须一致，
  # 否则代理路径一律 401/403。先注入 .env（与 web_app 的 dotenv 语义一致）再解析。
  (
    cd "$ROOT_DIR/render_backend"
    if [[ -f "$ROOT_DIR/.env" ]]; then
      set -a
      # shellcheck disable=SC1091
      . "$ROOT_DIR/.env"
      set +a
    fi
    local render_key="${RENDER_BACKEND_API_KEY:-${MANIM_API_KEY:-dev-key-change-in-production}}"
    nohup env PORT="$RENDER_PORT" MANIM_API_KEY="$render_key" "$py_bin" app.py >"$RENDER_LOG_FILE" 2>&1 &
    echo $! >"$RENDER_PID_FILE"
  )
  sleep 2
  if is_render_running; then
    echo "Render backend started at http://127.0.0.1:$RENDER_PORT (pid $(cat "$RENDER_PID_FILE"))."
    return 0
  fi
  echo "Warning: render backend failed to start. Recent log:"
  tail -n 30 "$RENDER_LOG_FILE" 2>/dev/null || true
  rm -f "$RENDER_PID_FILE"
  return 0
}

start_server() {
  if is_running; then
    echo "Aegis Web already running (pid $(cat "$PID_FILE"))."
  else
    local py_bin
    py_bin="$(resolve_python)"
    (
      cd "$ROOT_DIR"
      nohup "$py_bin" core/web_app.py --host "$HOST" --port "$PORT" >"$LOG_FILE" 2>&1 &
      echo $! >"$PID_FILE"
    )
    sleep 1
    if ! is_running; then
      echo "Failed to start Aegis Web. Recent log:"
      tail -n 80 "$LOG_FILE" 2>/dev/null || true
      rm -f "$PID_FILE"
      return 1
    fi
    echo "Aegis Web started at http://$HOST:$PORT (pid $(cat "$PID_FILE"))."
    echo "Log: $LOG_FILE"
  fi
  start_render_backend
}

stop_server() {
  if is_running; then
    local pid
    pid="$(cat "$PID_FILE")"
    kill "$pid" >/dev/null 2>&1 || true
    sleep 1
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill -9 "$pid" >/dev/null 2>&1 || true
    fi
    echo "Aegis Web stopped."
  else
    echo "Aegis Web is not running."
  fi
  rm -f "$PID_FILE"

  if is_render_running; then
    local rpid
    rpid="$(cat "$RENDER_PID_FILE")"
    kill "$rpid" >/dev/null 2>&1 || true
    sleep 1
    if kill -0 "$rpid" >/dev/null 2>&1; then
      kill -9 "$rpid" >/dev/null 2>&1 || true
    fi
    echo "Render backend stopped."
  fi
  rm -f "$RENDER_PID_FILE"
  return 0
}

status_server() {
  if is_running; then
    local pid
    pid="$(cat "$PID_FILE")"
    echo "Aegis Web is running (pid $pid) at http://$HOST:$PORT"
  else
    echo "Aegis Web is not running."
  fi
  if is_render_running; then
    echo "Render backend is running (pid $(cat "$RENDER_PID_FILE")) at http://127.0.0.1:$RENDER_PORT"
  elif [[ "$WITH_RENDER" == "1" ]]; then
    echo "Render backend is not running (community/works and warmup pings will 502 until it is)."
  else
    echo "Render backend disabled (AEGIS_WITH_RENDER=0)."
  fi
  if is_running; then
    return 0
  fi
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
  AEGIS_WITH_RENDER=1        (also manage the local render backend; 0 to disable)
  AEGIS_RENDER_PORT=5001     (must match RENDER_BACKEND_URL expected by core/web_app.py)
  AEGIS_RENDER_LOG_FILE=/tmp/aegis_render_live.log
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

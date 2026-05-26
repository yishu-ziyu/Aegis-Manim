#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-aegis-manim-render}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:5000/health}"
LOG_FILE="${LOG_FILE:-/var/log/aegis-render-watchdog.log}"
LOCK_FILE="${LOCK_FILE:-/tmp/aegis-render-watchdog.lock}"
COOLDOWN_FILE="${COOLDOWN_FILE:-/tmp/aegis-render-watchdog.last-restart}"
COOLDOWN_SECONDS="${COOLDOWN_SECONDS:-180}"
HEALTH_TIMEOUT_SECONDS="${HEALTH_TIMEOUT_SECONDS:-12}"

log() {
  printf '%s %s\n' "$(date -Is)" "$*" >> "$LOG_FILE"
}

restart_container() {
  local now last elapsed
  now="$(date +%s)"
  last="0"
  if [[ -f "$COOLDOWN_FILE" ]]; then
    last="$(cat "$COOLDOWN_FILE" 2>/dev/null || printf '0')"
  fi
  elapsed=$((now - last))
  if (( elapsed < COOLDOWN_SECONDS )); then
    log "health failed, restart skipped during cooldown container=${CONTAINER_NAME} elapsed=${elapsed}s"
    return 2
  fi

  log "health failed, restarting container=${CONTAINER_NAME}"
  docker restart "$CONTAINER_NAME" >/dev/null
  printf '%s\n' "$now" > "$COOLDOWN_FILE"
  sleep 8

  if curl -fsS --max-time "$HEALTH_TIMEOUT_SECONDS" "$HEALTH_URL" >/dev/null; then
    log "restart recovered health container=${CONTAINER_NAME}"
    return 0
  fi

  log "restart did not recover health container=${CONTAINER_NAME}"
  return 1
}

main() {
  mkdir -p "$(dirname "$LOG_FILE")"
  exec 9>"$LOCK_FILE"
  if ! flock -n 9; then
    exit 0
  fi

  if ! docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
    log "container missing container=${CONTAINER_NAME}"
    exit 1
  fi

  if curl -fsS --max-time "$HEALTH_TIMEOUT_SECONDS" "$HEALTH_URL" >/dev/null; then
    log "health ok container=${CONTAINER_NAME}"
    exit 0
  fi

  restart_container
}

main "$@"

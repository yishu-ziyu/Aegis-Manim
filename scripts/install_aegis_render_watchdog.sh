#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WATCHDOG_SOURCE="${SOURCE_DIR}/aegis_render_watchdog.sh"
WATCHDOG_TARGET="${WATCHDOG_TARGET:-/usr/local/bin/aegis_render_watchdog.sh}"
SERVICE_PATH="${SERVICE_PATH:-/etc/systemd/system/aegis-render-watchdog.service}"
TIMER_PATH="${TIMER_PATH:-/etc/systemd/system/aegis-render-watchdog.timer}"

if [[ "$(id -u)" != "0" ]]; then
  echo "Run as root so systemd unit files can be installed." >&2
  exit 1
fi

install -m 0755 "$WATCHDOG_SOURCE" "$WATCHDOG_TARGET"

cat > "$SERVICE_PATH" <<SERVICE
[Unit]
Description=Aegis Manim render backend health watchdog
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
Environment=CONTAINER_NAME=aegis-manim-render
Environment=HEALTH_URL=http://127.0.0.1:5000/health
Environment=LOG_FILE=/var/log/aegis-render-watchdog.log
ExecStart=${WATCHDOG_TARGET}
SERVICE

cat > "$TIMER_PATH" <<'TIMER'
[Unit]
Description=Run Aegis Manim render backend health watchdog every minute

[Timer]
OnBootSec=90s
OnUnitActiveSec=60s
AccuracySec=10s
Unit=aegis-render-watchdog.service

[Install]
WantedBy=timers.target
TIMER

systemctl daemon-reload
systemctl enable --now aegis-render-watchdog.timer
systemctl list-timers aegis-render-watchdog.timer --no-pager

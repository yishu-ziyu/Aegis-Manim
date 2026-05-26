#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
OUTPUT="${OUTPUT:-/tmp/aegis-vision-server-update.tgz}"
REMOTE_HOST="${REMOTE_HOST:-root@121.89.90.68}"
REMOTE_ARCHIVE="${REMOTE_ARCHIVE:-/opt/aegis/aegis-vision-server-update.tgz}"
REMOTE_PROJECT_DIR="${REMOTE_PROJECT_DIR:-/opt/aegis/Aegis-Manim}"
REMOTE_DOCTOR_LOG="${REMOTE_DOCTOR_LOG:-/opt/aegis/vision-doctor.log}"
REMOTE_DOCTOR_PID="${REMOTE_DOCTOR_PID:-/opt/aegis/vision-doctor.pid}"
REMOTE_ARCHIVE_DIR="$(dirname "$REMOTE_ARCHIVE")"

cd "$PROJECT_DIR"

OUTPUT="$OUTPUT" scripts/package_aegis_vision_server_update.sh

echo
echo "== Uploading Vision Server update and running remote doctor on $REMOTE_HOST =="
echo "This uses one SSH session; if password login is used, expect one password prompt."
ssh "$REMOTE_HOST" "bash -lc 'set -euo pipefail; mkdir -p \"$REMOTE_ARCHIVE_DIR\"; cat > \"$REMOTE_ARCHIVE\"; cd \"$REMOTE_PROJECT_DIR\"; tar -xzf \"$REMOTE_ARCHIVE\" -C \"$REMOTE_PROJECT_DIR\"; chmod +x scripts/aegis_vision_server.py scripts/install_aegis_vision_server.sh scripts/aegis_vision_server_doctor.sh; if [[ -f \"$REMOTE_DOCTOR_PID\" ]] && kill -0 \"\$(cat \"$REMOTE_DOCTOR_PID\")\" 2>/dev/null; then echo \"Vision doctor already running with pid \$(cat \"$REMOTE_DOCTOR_PID\")\"; else nohup bash -lc \"cd $REMOTE_PROJECT_DIR && scripts/aegis_vision_server_doctor.sh\" > \"$REMOTE_DOCTOR_LOG\" 2>&1 < /dev/null & echo \$! > \"$REMOTE_DOCTOR_PID\"; echo \"Started Vision doctor with pid \$(cat \"$REMOTE_DOCTOR_PID\")\"; fi; echo \"Log: $REMOTE_DOCTOR_LOG\"; echo \"Follow with: ssh $REMOTE_HOST tail -f $REMOTE_DOCTOR_LOG\"; tail -n 40 \"$REMOTE_DOCTOR_LOG\" 2>/dev/null || true'" < "$OUTPUT"

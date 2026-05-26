#!/usr/bin/env bash
set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-root@121.89.90.68}"
REMOTE_DOCTOR_LOG="${REMOTE_DOCTOR_LOG:-/opt/aegis/vision-doctor.log}"
REMOTE_DOCTOR_PID="${REMOTE_DOCTOR_PID:-/opt/aegis/vision-doctor.pid}"
TAIL_LINES="${TAIL_LINES:-160}"
PUBLIC_VISION_URL="${PUBLIC_VISION_URL:-https://manim.yishuziyu.cn/api/vision/analyze}"

echo "== Checking Aegis Vision Server update on $REMOTE_HOST =="
echo "If password login is used, expect one SSH password prompt."

ssh "$REMOTE_HOST" "bash -lc 'set -euo pipefail; echo \"== doctor process ==\"; if [[ -f \"$REMOTE_DOCTOR_PID\" ]]; then pid=\$(cat \"$REMOTE_DOCTOR_PID\"); echo \"pid=\$pid\"; ps -p \"\$pid\" -o pid=,stat=,etime=,cmd= || true; else echo \"pid file missing: $REMOTE_DOCTOR_PID\"; fi; echo; echo \"== doctor log tail ==\"; tail -n $TAIL_LINES \"$REMOTE_DOCTOR_LOG\" 2>/dev/null || echo \"log missing: $REMOTE_DOCTOR_LOG\"; echo; echo \"== evidence markers ==\"; grep -E \"Probe passed|summary|passed|failed|error|ERROR|Traceback\" \"$REMOTE_DOCTOR_LOG\" 2>/dev/null | tail -n 80 || true; echo; echo \"== service ==\"; systemctl status aegis-vision.service --no-pager -l 2>/dev/null || true; echo; echo \"== health ==\"; curl -fsS http://127.0.0.1:5050/health 2>/dev/null || true; echo; echo \"== exposure decision ==\"; cd /opt/aegis/Aegis-Manim 2>/dev/null && python3 scripts/decide_aegis_vision_exposure.py --public-vision-url \"$PUBLIC_VISION_URL\" || true; echo'"

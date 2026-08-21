#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/aegis/Aegis-Manim}"
USER_IMAGE_PATH="${IMAGE_PATH:-}"
IMAGE_PATH="${IMAGE_PATH:-/opt/aegis/vision-test.png}"
REPORT_PATH="${REPORT_PATH:-/opt/aegis/vision-probe-report.json}"
TIMEOUT="${TIMEOUT:-320}"
INSTALL_ON_PASS="${INSTALL_ON_PASS:-1}"
RUN_BATCH_ACCEPTANCE="${RUN_BATCH_ACCEPTANCE:-1}"
ENV_FILE="${ENV_FILE:-/opt/aegis/vision.env}"
ACCEPTANCE_JSONL="${ACCEPTANCE_JSONL:-/opt/aegis/vision-economics-acceptance.jsonl}"

if [[ ! -d "$PROJECT_DIR" ]]; then
  echo "Project directory not found: $PROJECT_DIR"
  echo "Set PROJECT_DIR=/path/to/Aegis-Manim and rerun."
  exit 2
fi

cd "$PROJECT_DIR"

if [[ ! -f scripts/probe_kimi_vision_cli.py ]]; then
  echo "Missing scripts/probe_kimi_vision_cli.py. Run git pull first."
  exit 2
fi

if [[ ! -f "$IMAGE_PATH" && -z "$USER_IMAGE_PATH" && -f fixtures/vision-test.png ]]; then
  IMAGE_PATH="$PROJECT_DIR/fixtures/vision-test.png"
fi

if [[ ! -f "$IMAGE_PATH" ]]; then
  echo "Test image not found: $IMAGE_PATH"
  echo "Upload or copy one Chinese economics question/chart image to that path, then rerun."
  echo "Example: scp ./your-image.png \$REMOTE_HOST:$IMAGE_PATH"
  exit 2
fi

choose_binary() {
  if [[ -n "${BINARY:-}" ]]; then
    printf '%s\n' "$BINARY"
    return
  fi
  if command -v kimi >/dev/null 2>&1; then
    printf 'kimi\n'
    return
  fi
  if command -v codex >/dev/null 2>&1; then
    printf 'codex\n'
    return
  fi
  if command -v claude >/dev/null 2>&1; then
    printf 'claude\n'
    return
  fi
}

BINARY_TO_TEST="$(choose_binary || true)"
if [[ -z "$BINARY_TO_TEST" ]]; then
  echo "No supported CLI found. Install and login kimi, codex, or claude first."
  exit 2
fi

ARGS=(
  python3 scripts/probe_kimi_vision_cli.py
  --image "$IMAGE_PATH"
  --binary "$BINARY_TO_TEST"
  --timeout "$TIMEOUT"
  --report "$REPORT_PATH"
)

ARGS_JSON_TO_PERSIST="${ARGS_JSON:-}"
if [[ -n "${ARGS_JSON:-}" ]]; then
  ARGS+=(--args-json "$ARGS_JSON")
elif [[ "$BINARY_TO_TEST" == "codex" ]]; then
  ARGS_JSON_TO_PERSIST='["exec","--skip-git-repo-check","{prompt}","--image","{image_path}"]'
  ARGS+=(--args-json "$ARGS_JSON_TO_PERSIST")
elif [[ "$BINARY_TO_TEST" == "claude" ]]; then
  ARGS_JSON_TO_PERSIST='["-p","{prompt}"]'
  ARGS+=(--args-json "$ARGS_JSON_TO_PERSIST")
fi

upsert_env_line() {
  local key="$1"
  local value="$2"
  local formatted_value
  local tmp_file

  mkdir -p "$(dirname "$ENV_FILE")"
  touch "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  formatted_value="$(format_env_value "$value")"
  tmp_file="$(mktemp "${ENV_FILE}.XXXXXX")"
  awk -v key="$key" -v value="$formatted_value" '
    BEGIN { found = 0 }
    index($0, key "=") == 1 {
      print key "=" value
      found = 1
      next
    }
    { print }
    END {
      if (!found) {
        print key "=" value
      }
    }
  ' "$ENV_FILE" > "$tmp_file"
  cat "$tmp_file" > "$ENV_FILE"
  rm -f "$tmp_file"
  chmod 600 "$ENV_FILE"
}

format_env_value() {
  local value="$1"
  if [[ -z "$value" ]]; then
    printf '\n'
    return
  fi
  printf "'%s'\n" "$value"
}

persist_tested_cli_env() {
  upsert_env_line "KIMI_VISION_CLI_BINARY" "$BINARY_TO_TEST"
  upsert_env_line "KIMI_VISION_CLI_ARGS_JSON" "$ARGS_JSON_TO_PERSIST"
  upsert_env_line "KIMI_VISION_CLI_TIMEOUT_SECONDS" "$TIMEOUT"
  upsert_env_line "KIMI_VISION_IMAGE_TOKEN_TEMPLATE" "${KIMI_VISION_IMAGE_TOKEN_TEMPLATE:-@{image_path}}"
  upsert_env_line "KIMI_VISION_CLI_COMMAND" "python3 $PROJECT_DIR/scripts/kimi_vision_cli_bridge.py {image_path} {prompt_path}"
}

echo "== Aegis Vision CLI Probe =="
echo "project: $PROJECT_DIR"
echo "image:   $IMAGE_PATH"
echo "binary:  $BINARY_TO_TEST"
echo "report:  $REPORT_PATH"
echo

"${ARGS[@]}"

python3 - "$REPORT_PATH" <<'PY'
import json
import sys
from pathlib import Path

report_path = Path(sys.argv[1])
payload = json.loads(report_path.read_text(encoding="utf-8"))
if not payload.get("ok"):
    print("Probe did not pass. Do not enable public image upload yet.")
    print(json.dumps(payload.get("failureReasons", []), ensure_ascii=False))
    raise SystemExit(1)
print("Probe passed.")
PY

echo "Persisting tested CLI settings to $ENV_FILE"
persist_tested_cli_env

if [[ "$INSTALL_ON_PASS" == "1" ]]; then
  chmod +x scripts/aegis_vision_server.py scripts/install_aegis_vision_server.sh
  scripts/install_aegis_vision_server.sh
else
  echo "INSTALL_ON_PASS=0, skipping service installation."
fi

if [[ "$INSTALL_ON_PASS" == "1" ]]; then
  echo
  echo "== Vision Server Health =="
  curl -fsS http://127.0.0.1:5050/health
  echo
fi

if [[ "$RUN_BATCH_ACCEPTANCE" == "1" ]]; then
  FIXTURES=(
    fixtures/01-tax-wedge.png
    fixtures/02-consumer-choice.png
    fixtures/03-monopoly.png
    fixtures/04-externality.png
    fixtures/05-is-lm.png
  )
  missing_fixture=0
  for fixture in "${FIXTURES[@]}"; do
    if [[ ! -f "$fixture" ]]; then
      missing_fixture=1
    fi
  done
  if [[ "$missing_fixture" == "1" ]]; then
    echo "Fixture images are missing; skipping 5-image acceptance. Set RUN_BATCH_ACCEPTANCE=0 to skip intentionally."
  else
    VISION_API_KEY=""
    if [[ -f "$ENV_FILE" ]]; then
      VISION_API_KEY="$(grep '^AEGIS_VISION_BACKEND_API_KEY=' "$ENV_FILE" | tail -n 1 | cut -d= -f2- || true)"
    fi
    echo
    echo "== 5-Image Vision Acceptance =="
    python3 scripts/production_vision_economics_acceptance.py \
      "${FIXTURES[@]}" \
      --base-url http://127.0.0.1:5050 \
      --request-timeout "$TIMEOUT" \
      --skip-render \
      --jsonl "$ACCEPTANCE_JSONL" \
      --api-key "$VISION_API_KEY"
  fi
else
  echo "RUN_BATCH_ACCEPTANCE=0, skipping 5-image acceptance."
fi

echo
echo "== Next =="
echo "1. Verify: curl -sS http://127.0.0.1:5050/health"
echo "2. Configure public gateway only after the probe and 5-image acceptance pass:"
echo "   AEGIS_VISION_PUBLIC_ENABLED=1"
echo "   VISION_BACKEND_URL=http://YOUR_HOST:5050"
echo "   VISION_BACKEND_API_KEY=(read from /opt/aegis/vision.env; do not paste it into chat)"

#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/aegis/Aegis-Manim}"
ENV_FILE="${ENV_FILE:-/opt/aegis/vision.env}"
SERVICE_FILE="/etc/systemd/system/aegis-vision.service"
PORT="${AEGIS_VISION_PORT:-5050}"
HOST="${AEGIS_VISION_HOST:-0.0.0.0}"

if [[ ! -f "$PROJECT_DIR/scripts/aegis_vision_server.py" ]]; then
  echo "Missing $PROJECT_DIR/scripts/aegis_vision_server.py"
  echo "Set PROJECT_DIR=/path/to/Aegis-Manim and rerun."
  exit 2
fi

mkdir -p "$(dirname "$ENV_FILE")"
touch "$ENV_FILE"
chmod 600 "$ENV_FILE"

if ! grep -q '^AEGIS_VISION_BACKEND_API_KEY=' "$ENV_FILE"; then
  if command -v openssl >/dev/null 2>&1; then
    GENERATED_KEY="$(openssl rand -hex 32)"
  else
    GENERATED_KEY="$(date +%s)-replace-me"
  fi
  printf 'AEGIS_VISION_BACKEND_API_KEY=%s\n' "$GENERATED_KEY" >> "$ENV_FILE"
fi

ensure_env_line() {
  local key="$1"
  local value="$2"
  if ! grep -q "^${key}=" "$ENV_FILE"; then
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

ensure_env_line "AEGIS_VISION_HOST" "$HOST"
ensure_env_line "AEGIS_VISION_PORT" "$PORT"
ensure_env_line "AEGIS_VISION_MAX_IMAGE_BYTES" "7340032"
ensure_env_line "AEGIS_VISION_MAX_REQUEST_BYTES" "9437184"
ensure_env_line "KIMI_VISION_CLI_TIMEOUT_SECONDS" "320"
ensure_env_line "KIMI_VISION_CLI_BINARY" "kimi"
ensure_env_line "KIMI_VISION_CLI_ARGS_JSON" ""
ensure_env_line "KIMI_VISION_IMAGE_TOKEN_TEMPLATE" "@{image_path}"
ensure_env_line "KIMI_VISION_CLI_COMMAND" "python3 $PROJECT_DIR/scripts/kimi_vision_cli_bridge.py {image_path} {prompt_path}"

cat > "$SERVICE_FILE" <<SERVICE
[Unit]
Description=Aegis Manim Vision CLI Bridge
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$PROJECT_DIR
EnvironmentFile=$ENV_FILE
ExecStart=/usr/bin/env python3 $PROJECT_DIR/scripts/aegis_vision_server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable --now aegis-vision.service

echo "Aegis vision server installed."
echo "Health: curl -sS http://127.0.0.1:${PORT}/health"
echo "Env: $ENV_FILE"
echo "Use this on the public gateway after CLI probe passes:"
echo "  AEGIS_VISION_PUBLIC_ENABLED=1"
echo "  VISION_BACKEND_URL=http://<server-ip>:${PORT}"
echo "  VISION_BACKEND_API_KEY=\$(grep '^AEGIS_VISION_BACKEND_API_KEY=' '$ENV_FILE' | cut -d= -f2-)"

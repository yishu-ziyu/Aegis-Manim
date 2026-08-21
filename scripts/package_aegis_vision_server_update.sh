#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
OUTPUT="${OUTPUT:-/tmp/aegis-vision-server-update.tgz}"
TMP_DIR="$(mktemp -d)"

FILES=(
  core/vision_analysis.py
  scripts/aegis_vision_server.py
  scripts/install_aegis_vision_server.sh
  scripts/aegis_vision_server_doctor.sh
  scripts/kimi_vision_cli_bridge.py
  scripts/probe_kimi_vision_cli.py
  scripts/decide_aegis_vision_exposure.py
  scripts/generate_vision_economics_fixtures.py
  scripts/production_vision_economics_acceptance.py
)

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

cd "$PROJECT_DIR"

for file in "${FILES[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "Missing required file: $file"
    exit 2
  fi
done

for file in "${FILES[@]}"; do
  mkdir -p "$TMP_DIR/$(dirname "$file")"
  cp "$file" "$TMP_DIR/$file"
done

python3 scripts/generate_vision_economics_fixtures.py --output-dir "$TMP_DIR/fixtures" >/dev/null
cp "$TMP_DIR/fixtures/01-tax-wedge.png" "$TMP_DIR/fixtures/vision-test.png"

tar -C "$TMP_DIR" -czf "$OUTPUT" .

echo "Created: $OUTPUT"
echo "Included default test image: fixtures/vision-test.png"
echo
echo "Preferred one-command push:"
echo "  scripts/push_aegis_vision_server_update.sh"
echo "  # Starts remote doctor under nohup and writes /opt/aegis/vision-doctor.log"
echo "  scripts/check_aegis_vision_server_update.sh"
echo "  # Reads remote pid, doctor log, systemd status, and local health"
echo
echo "Upload to server:"
echo "  scp $OUTPUT \$REMOTE_HOST:/opt/aegis/aegis-vision-server-update.tgz"
echo
echo "Then run on server:"
echo "  cd /opt/aegis/Aegis-Manim"
echo "  tar -xzf /opt/aegis/aegis-vision-server-update.tgz -C /opt/aegis/Aegis-Manim"
echo "  chmod +x scripts/aegis_vision_server.py scripts/install_aegis_vision_server.sh scripts/aegis_vision_server_doctor.sh"
echo "  scripts/aegis_vision_server_doctor.sh"

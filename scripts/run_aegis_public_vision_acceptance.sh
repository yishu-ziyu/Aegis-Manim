#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-https://manim.yishuziyu.cn}"
PROVIDER="${PROVIDER:-trial-minimax-direct}"
FIXTURE_DIR="${FIXTURE_DIR:-/tmp/aegis-public-vision-fixtures}"
OUTPUT_DIR="${OUTPUT_DIR:-/tmp/aegis-public-vision-acceptance}"
JSONL="${JSONL:-$OUTPUT_DIR/full-render.jsonl}"
REQUEST_TIMEOUT="${REQUEST_TIMEOUT:-360}"
RENDER_TIMEOUT="${RENDER_TIMEOUT:-360}"
POLL_INTERVAL="${POLL_INTERVAL:-8}"
POLL_ATTEMPTS="${POLL_ATTEMPTS:-75}"

mkdir -p "$OUTPUT_DIR"

python3 scripts/generate_vision_economics_fixtures.py \
  --output-dir "$FIXTURE_DIR" >/dev/null

python3 scripts/production_vision_economics_acceptance.py \
  "$FIXTURE_DIR/01-tax-wedge.png" \
  "$FIXTURE_DIR/02-consumer-choice.png" \
  "$FIXTURE_DIR/03-monopoly.png" \
  "$FIXTURE_DIR/04-externality.png" \
  "$FIXTURE_DIR/05-is-lm.png" \
  --base-url "$BASE_URL" \
  --provider "$PROVIDER" \
  --output-dir "$OUTPUT_DIR" \
  --request-timeout "$REQUEST_TIMEOUT" \
  --render-timeout "$RENDER_TIMEOUT" \
  --poll-interval "$POLL_INTERVAL" \
  --poll-attempts "$POLL_ATTEMPTS" \
  --jsonl "$JSONL"

echo "Full public acceptance JSONL: $JSONL"
echo "Use public exposure only if all records have ok=true, status=done, videoUrl, and videoBytes."

#!/usr/bin/env bash
#
# Vercel production deploy helper for Aegis-Manim
#
# Problem: Vercel detects pyproject.toml and runs uv sync,
# but manimpango requires system pangocairo which is unavailable.
# Workaround: temporarily hide pyproject.toml during deploy.
#
# Usage:
#   scripts/deploy_vercel.sh        # deploy to production
#   scripts/deploy_vercel.sh --preview  # deploy to preview

set -euo pipefail

cd "$(dirname "$0")/.."

ENV_ARG="--prod"
if [ "${1:-}" = "--preview" ]; then
    ENV_ARG=""
fi

echo "==> Backing up pyproject.toml..."
cp pyproject.toml pyproject.toml.bak

echo "==> Hiding pyproject.toml from Vercel build..."
mv pyproject.toml pyproject.toml.hidden

cleanup() {
    echo "==> Restoring pyproject.toml..."
    if [ -f pyproject.toml.hidden ]; then
        mv pyproject.toml.hidden pyproject.toml
    fi
}
trap cleanup EXIT

echo "==> Deploying to Vercel..."
if [ -n "$ENV_ARG" ]; then
    vercel --prod --yes
else
    vercel --yes
fi

echo "==> Done."

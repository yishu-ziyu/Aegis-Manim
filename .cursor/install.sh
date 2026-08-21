#!/usr/bin/env bash
# Idempotent setup for Aegis-Manim: system libraries for the Manim render
# pipeline (Cairo/Pango/ffmpeg/LaTeX + CJK fonts), the uv toolchain, the locked
# Python environment, and the Flask render backend dependencies.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

APT_PACKAGES=(
  build-essential libcairo2-dev libpango1.0-dev libffi-dev pkg-config python3-dev
  ffmpeg fontconfig fonts-noto-cjk fonts-noto-color-emoji
  sox libsox-fmt-mp3
  libgl1 python3-opengl xvfb freeglut3-dev
  texlive-latex-base texlive-latex-extra texlive-fonts-extra texlive-science dvisvgm
)

need_apt=0
for pkg in "${APT_PACKAGES[@]}"; do
  dpkg -s "$pkg" >/dev/null 2>&1 || need_apt=1
done
if [ "$need_apt" = "1" ]; then
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${APT_PACKAGES[@]}"
fi

# uv is the package/venv manager pinned by uv.lock (matches CI).
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"

# Main + dev dependencies (locked) into .venv, building the editable manim package.
uv sync --locked

# Flask render backend runs in the same .venv; its deps live outside pyproject.
uv pip install -r render_backend/requirements.txt

echo "Aegis-Manim environment ready."

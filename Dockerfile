# Root Dockerfile for Render.com
# The actual application lives in render_backend/; this file ensures
# Render can find the Dockerfile at repo root regardless of Root Directory settings.

FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libcairo2-dev \
    libpango1.0-dev \
    libffi-dev \
    pkg-config \
    ffmpeg \
    fontconfig \
    fonts-noto-cjk \
    fonts-noto-color-emoji \
    sox \
    libsox-fmt-mp3 \
    texlive-latex-base \
    texlive-latex-extra \
    texlive-fonts-extra \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

FROM base AS deps
COPY render_backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM base AS runtime
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

WORKDIR /app
RUN mkdir -p /app/temp /app/outputs

# Force cache bust on code changes
ARG CACHE_BUST=1
COPY render_backend/app.py .
COPY render_backend/supabase_client.py .

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MANIM_API_KEY="" \
    MANIM_CJK_FONT="Noto Sans CJK SC" \
    MANIM_RENDER_QUALITY="-ql" \
    PORT=5000 \
    FLASK_DEBUG=0

EXPOSE 5000

CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5000", "--timeout", "300", "--keep-alive", "5", "app:app"]

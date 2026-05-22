# Multi-stage build for Manim rendering backend
# Stage 1: Base with system dependencies
FROM python:3.12-slim AS base

# Install system dependencies required by Manim
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

# Stage 2: Install Python dependencies
FROM base AS deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 3: Final runtime image
FROM base AS runtime
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

WORKDIR /app

# Create directories for temp and output files
RUN mkdir -p /app/temp /app/outputs

# Copy application code
COPY app.py .

# Environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MANIM_API_KEY="" \
    MANIM_CJK_FONT="Noto Sans CJK SC" \
    MANIM_RENDER_QUALITY="-qm" \
    PORT=5000 \
    FLASK_DEBUG=0

EXPOSE 5000

# Use gunicorn for production
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5000", "--timeout", "300", "--keep-alive", "5", "app:app"]

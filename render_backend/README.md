# Manim Rendering Backend API

A lightweight Flask-based API for rendering Manim scenes. Supports synchronous and asynchronous rendering with proper error handling, rate limiting, and security controls.

## Features

- **POST /render** - Synchronous rendering, returns MP4 directly
- **POST /render-async** - Asynchronous rendering with job polling
- **GET /status/<job_id>** - Check async render status
- **GET /download/<job_id>** - Download rendered video
- **GET /health** - Health check
- API key validation via `X-API-Key` header
- In-memory rate limiting (10 requests / 60s per IP)
- Supabase-backed job persistence when `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` are configured
- Supabase Storage video URLs for async renders when persistence is configured
- Memory-only fallback for local development when Supabase is not configured
- Optional Cloud Run Jobs executor for long-running production renders
- Max code size: 100 KB
- CORS enabled for browser requests
- Automatic temp file cleanup

## Quick Start

### Local Development

```bash
cd render_backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set API key (optional, defaults to "dev-key-change-in-production")
export MANIM_API_KEY="your-secret-key"

# Run development server
python app.py
```

The server starts on `http://0.0.0.0:5000`.

### Docker

```bash
cd render_backend

# Build
docker build -t manim-render-backend .

# Run
docker run -d \
  -p 5000:5000 \
  -e MANIM_API_KEY="your-secret-key" \
  -v $(pwd)/outputs:/app/outputs \
  manim-render-backend
```

## API Usage

### Authentication

All endpoints (except `/health`) require the `X-API-Key` header:

```bash
curl -H "X-API-Key: your-secret-key" http://localhost:5000/health
```

### Synchronous Render

```bash
curl -X POST http://localhost:5000/render \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-key" \
  -d '{
    "code": "from manim import *\nclass GeneratedScene(Scene):\n    def construct(self):\n        self.play(Create(Circle()))\n        self.wait(1)",
    "scene_name": "GeneratedScene"
  }' \
  --output scene.mp4
```

Returns the MP4 file directly. On error, returns JSON with details.

### Asynchronous Render

```bash
# Submit job
curl -X POST http://localhost:5000/render-async \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-key" \
  -d '{
    "code": "from manim import *\nclass GeneratedScene(Scene):\n    def construct(self):\n        self.play(Create(Circle()))\n        self.wait(1)",
    "scene_name": "GeneratedScene"
  }'
```

Response:
```json
{
  "job_id": "uuid",
  "status": "pending",
  "status_url": "/status/uuid",
  "download_url": "/download/uuid"
}
```

Poll status:
```bash
curl -H "X-API-Key: your-secret-key" http://localhost:5000/status/<job_id>
```

Download when done:
```bash
curl -H "X-API-Key: your-secret-key" http://localhost:5000/download/<job_id> --output scene.mp4
```

### Health Check

```bash
curl http://localhost:5000/health
```

## Error Codes

| Status | Meaning |
|--------|---------|
| 400 | Syntax error in code or invalid payload |
| 401 | Missing X-API-Key header |
| 403 | Invalid API key |
| 404 | Job not found |
| 409 | Video not ready (async) |
| 413 | Payload exceeds 100 KB |
| 429 | Rate limit exceeded |
| 500 | Manim render failure |
| 504 | Rendering timed out (default 300s) |

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `MANIM_API_KEY` | `dev-key-change-in-production` | API key for authentication |
| `PORT` | `5000` | Server port |
| `FLASK_DEBUG` | `0` | Enable Flask debug mode |
| `SUPABASE_URL` | unset | Supabase project URL. When unset, the backend uses memory-only mode |
| `SUPABASE_SERVICE_KEY` | unset | Supabase service-role key for render job persistence |
| `SUPABASE_STORAGE_BUCKET` | `manim-videos` | Storage bucket for rendered async videos |
| `MANIM_EXECUTOR` | `local` | `local` runs Manim in the current container; `cloud_run` dispatches async renders to Cloud Run Jobs |
| `CLOUD_RUN_PROJECT` | unset | Google Cloud project ID used when `MANIM_EXECUTOR=cloud_run` |
| `CLOUD_RUN_REGION` | unset | Cloud Run region, for example `asia-east1` |
| `CLOUD_RUN_JOB_NAME` | unset | Existing Cloud Run Job name that runs `python cloud_run_worker.py` |
| `CLOUD_RUN_JOB_TIMEOUT_SECONDS` | unset | Optional per-execution timeout override passed to Cloud Run Jobs |
| `CLOUD_RUN_CONTAINER_NAME` | unset | Optional container name override for multi-container jobs |
| `GOOGLE_APPLICATION_CREDENTIALS` | unset | Optional path to a Google service account file |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | unset | Optional service account JSON value for platforms that cannot mount a file |
| `CLOUD_RUN_ACCESS_TOKEN` | unset | Optional short-lived access token for local/manual dispatch tests |

### Supabase Setup

Before enabling `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` in Render, apply
[supabase/schema.sql](../supabase/schema.sql) to the target Supabase project. The
backend expects the `render_jobs` and `job_logs` tables to be available through
PostgREST, and the configured Storage bucket to exist.

Read-only readiness check:

```bash
python scripts/verify_render_persistence.py --external-read-only --env-file .env.local
```

### Cloud Run Jobs Executor

The production render architecture keeps the public Vercel and Supabase
contract unchanged:

1. Vercel calls this backend's `POST /render-async`.
2. The backend writes a `render_jobs` row and returns `job_id`.
3. With `MANIM_EXECUTOR=cloud_run`, the backend calls the Cloud Run Jobs API and
   passes only `AEGIS_RENDER_JOB_ID` and `AEGIS_RENDER_MODE` as execution env
   overrides.
4. The Cloud Run Job container runs `python cloud_run_worker.py`, fetches the
   job from Supabase, renders Manim, uploads the MP4 to Supabase Storage, and
   updates the existing job status.
5. The frontend keeps polling `/status/<job_id>` and downloading through
   `/download/<job_id>`.

Create the Cloud Run Job from the same render backend image and override the
command to run the worker:

```bash
gcloud run jobs create aegis-manim-render \
  --image REGION-docker.pkg.dev/PROJECT/REPO/aegis-manim-render:latest \
  --region asia-east1 \
  --command python \
  --args cloud_run_worker.py \
  --task-timeout 3600 \
  --memory 4Gi \
  --cpu 2 \
  --set-env-vars SUPABASE_URL=... \
  --set-secrets SUPABASE_SERVICE_KEY=...
```

The control-plane service that receives `/render-async` needs permission to run
that job. If it runs outside Google Cloud, configure either
`GOOGLE_APPLICATION_CREDENTIALS_JSON` or `GOOGLE_APPLICATION_CREDENTIALS`; never
log or expose those values.

Local memory-mode API smoke:

```bash
python scripts/verify_render_persistence.py --local-memory-smoke
```

## Production Notes

- When Supabase is configured, `render_jobs` is the authoritative job source and memory is only a cache.
- On startup, pending/running jobs are recovered from Supabase and stale pending/running jobs are reaped as failed.
- Async render success requires uploading the video to Supabase Storage; `/download/<job_id>` returns a `video_url` JSON payload for Storage-backed jobs.
- The in-memory rate limiter is not persistent across restarts. For production scale, replace it with Redis or another shared limiter.
- The default `gunicorn` config uses 2 workers. Adjust `-w` based on CPU cores and expected load.
- Manim rendering is CPU-intensive. Consider queue-based workers (Celery + Redis) for high throughput.
- Local fallback output videos are stored in `./outputs/` and are not automatically cleaned up. Set up a cron job or lifecycle policy.
- Supabase Storage videos need their own retention policy to stay within storage limits.

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

## Production Notes

- The in-memory rate limiter and job store are not persistent across restarts. For production scale, replace with Redis.
- The default `gunicorn` config uses 2 workers. Adjust `-w` based on CPU cores and expected load.
- Manim rendering is CPU-intensive. Consider queue-based workers (Celery + Redis) for high throughput.
- Output videos are stored in `./outputs/` and are not automatically cleaned up. Set up a cron job or lifecycle policy.

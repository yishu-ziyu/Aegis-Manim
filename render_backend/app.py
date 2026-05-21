"""
Manim Rendering Backend API

A lightweight Flask-based API for rendering Manim scenes.
Supports synchronous and asynchronous rendering with proper
error handling, rate limiting, and security controls.
"""

from __future__ import annotations

import functools
import hashlib
import os
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from werkzeug.exceptions import RequestEntityTooLarge

from supabase_client import (
    get_job as supa_get_job,
    health_check as supa_health,
    insert_job as supa_insert_job,
    insert_log as supa_insert_log,
    is_configured as supa_is_configured,
    update_job as supa_update_job,
    upload_video as supa_upload_video,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_KEY = os.environ.get("MANIM_API_KEY", "dev-key-change-in-production")
MAX_CODE_SIZE = 100 * 1024  # 100 KB
DEFAULT_TIMEOUT = 300  # seconds
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX_REQUESTS = 10

# Directories
BASE_DIR = Path(__file__).parent.resolve()
TEMP_DIR = BASE_DIR / "temp"
OUTPUT_DIR = BASE_DIR / "outputs"
TEMP_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Flask App
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CODE_SIZE + 4096  # JSON overhead
CORS(app)


# ---------------------------------------------------------------------------
# Rate Limiting (simple in-memory)
# ---------------------------------------------------------------------------

@dataclass
class RateLimitEntry:
    count: int = 0
    window_start: float = field(default_factory=time.time)


_rate_limit_store: dict[str, RateLimitEntry] = {}
_rate_limit_lock = threading.Lock()


def _is_rate_limited(client_id: str) -> bool:
    now = time.time()
    with _rate_limit_lock:
        entry = _rate_limit_store.get(client_id)
        if entry is None or now - entry.window_start > RATE_LIMIT_WINDOW:
            _rate_limit_store[client_id] = RateLimitEntry(count=1, window_start=now)
            return False
        if entry.count >= RATE_LIMIT_MAX_REQUESTS:
            return True
        entry.count += 1
        return False


def _cleanup_old_rate_limits() -> None:
    now = time.time()
    with _rate_limit_lock:
        stale = [
            k for k, v in _rate_limit_store.items() if now - v.window_start > RATE_LIMIT_WINDOW
        ]
        for k in stale:
            del _rate_limit_store[k]


# ---------------------------------------------------------------------------
# API Key Validation
# ---------------------------------------------------------------------------

def require_api_key(view_func):
    @functools.wraps(view_func)
    def wrapper(*args, **kwargs):
        key = request.headers.get("X-API-Key", "")
        if not key:
            return jsonify({"error": "Missing X-API-Key header"}), 401
        if key != API_KEY:
            return jsonify({"error": "Invalid API key"}), 403
        return view_func(*args, **kwargs)

    return wrapper


# ---------------------------------------------------------------------------
# Job State Management
# ---------------------------------------------------------------------------

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class RenderJob:
    job_id: str
    status: JobStatus
    created_at: str
    updated_at: str
    code: str
    scene_name: str
    video_path: str | None = None
    error_message: str | None = None
    stderr: str | None = None


_jobs: dict[str, RenderJob] = {}
_jobs_lock = threading.Lock()


def _use_supabase() -> bool:
    return supa_is_configured()


def _register_job(code: str, scene_name: str, client_ip: str | None = None) -> str:
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    if _use_supabase():
        supa_insert_job(job_id=job_id, code=code, scene_name=scene_name, client_ip=client_ip)
    job = RenderJob(
        job_id=job_id,
        status=JobStatus.PENDING,
        created_at=now,
        updated_at=now,
        code=code,
        scene_name=scene_name,
    )
    with _jobs_lock:
        _jobs[job_id] = job
    return job_id


def _update_job(
    job_id: str,
    status: JobStatus | None = None,
    video_path: str | None = None,
    error_message: str | None = None,
    stderr: str | None = None,
) -> None:
    if _use_supabase():
        supa_update_job(
            job_id=job_id,
            status=status.value if status else None,
            video_path=video_path,
            error_message=error_message,
            stderr=stderr,
        )
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        if status is not None:
            job.status = status
        if video_path is not None:
            job.video_path = video_path
        if error_message is not None:
            job.error_message = error_message
        if stderr is not None:
            job.stderr = stderr
        job.updated_at = datetime.now(timezone.utc).isoformat()


def _get_job(job_id: str) -> RenderJob | None:
    if _use_supabase():
        row = supa_get_job(job_id)
        if row:
            return RenderJob(
                job_id=row["job_id"],
                status=JobStatus(row["status"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                code=row["code"],
                scene_name=row["scene_name"],
                video_path=row.get("video_path"),
                error_message=row.get("error_message"),
                stderr=row.get("stderr"),
            )
    with _jobs_lock:
        return _jobs.get(job_id)


# ---------------------------------------------------------------------------
# Rendering Logic
# ---------------------------------------------------------------------------

def _find_rendered_video(temp_dir: Path, scene_name: str) -> Path | None:
    """Manim outputs to temp_dir / videos / {scene_name}.mp4 or similar."""
    # Manim default output path: temp_dir / videos / {quality_prefix}{scene_name}.mp4
    videos_dir = temp_dir / "videos"
    if not videos_dir.exists():
        return None

    # Search recursively for any MP4 matching the scene name
    candidates = list(videos_dir.rglob(f"*{scene_name}.mp4"))
    if candidates:
        # Return the most recently modified
        return max(candidates, key=lambda p: p.stat().st_mtime)
    return None


def _run_manim_render(
    code: str,
    scene_name: str,
    job_id: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """
    Execute manim render. Returns dict with keys:
    - success: bool
    - video_path: str | None
    - error: str | None
    - stderr: str | None
    """
    # Create a unique temp workspace
    workspace = TEMP_DIR / f"render_{uuid.uuid4().hex}"
    workspace.mkdir(parents=True, exist_ok=True)

    scene_file = workspace / "scene.py"
    scene_file.write_text(code, encoding="utf-8")

    if job_id:
        _update_job(job_id, status=JobStatus.RUNNING)

    cmd = [
        "python",
        "-m",
        "manim",
        "-ql",  # low quality for speed
        "--media_dir",
        str(workspace),
        str(scene_file),
        scene_name,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(workspace),
        )
    except subprocess.TimeoutExpired as exc:
        _cleanup_workspace(workspace)
        return {
            "success": False,
            "video_path": None,
            "error": f"Rendering timed out after {timeout}s",
            "stderr": exc.stderr if hasattr(exc, "stderr") else None,
        }
    except Exception as exc:
        _cleanup_workspace(workspace)
        return {
            "success": False,
            "video_path": None,
            "error": str(exc),
            "stderr": None,
        }

    if result.returncode != 0:
        _cleanup_workspace(workspace)
        return {
            "success": False,
            "video_path": None,
            "error": "Manim rendering failed",
            "stderr": result.stderr,
        }

    video_path = _find_rendered_video(workspace, scene_name)
    if video_path is None or not video_path.exists():
        _cleanup_workspace(workspace)
        return {
            "success": False,
            "video_path": None,
            "error": "Video file not found after rendering",
            "stderr": result.stderr,
        }

    # Upload to Supabase Storage if configured, otherwise keep local
    supa_video_url: str | None = None
    if _use_supabase() and job_id:
        supa_video_url = supa_upload_video(job_id, video_path)
        if supa_video_url:
            supa_insert_log(
                job_id=job_id,
                level="info",
                stage="upload",
                message="Video uploaded to Supabase Storage",
                detail=f"url={supa_video_url}",
            )

    # Keep local copy for fallback serving
    output_filename = f"{job_id or uuid.uuid4().hex}_{scene_name}.mp4"
    output_path = OUTPUT_DIR / output_filename
    shutil.move(str(video_path), str(output_path))
    _cleanup_workspace(workspace)

    return {
        "success": True,
        "video_path": str(output_path),
        "video_url": supa_video_url,
        "error": None,
        "stderr": result.stderr,
    }


def _cleanup_workspace(workspace: Path) -> None:
    """Remove temporary workspace directory."""
    try:
        if workspace.exists():
            shutil.rmtree(workspace)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_render_payload(data: dict) -> tuple[str, str] | tuple[None, str]:
    code = data.get("code")
    scene_name = data.get("scene_name", "GeneratedScene")

    if not code:
        return None, "Missing required field: code"
    if not isinstance(code, str):
        return None, "Field 'code' must be a string"
    if not isinstance(scene_name, str):
        return None, "Field 'scene_name' must be a string"

    # Basic syntax check (fast path)
    try:
        compile(code, "<scene.py>", "exec")
    except SyntaxError as exc:
        return None, f"Syntax error in code: {exc.msg} (line {exc.lineno})"

    return (code, scene_name), ""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/health", methods=["GET"])
def health() -> tuple:
    payload = {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
    # Debug: check why _use_supabase returns False
    payload["debug"] = {
        "url": os.environ.get("SUPABASE_URL", "NOT_SET")[:30],
        "key_present": bool(os.environ.get("SUPABASE_SERVICE_KEY")),
        "key_len": len(os.environ.get("SUPABASE_SERVICE_KEY", "")),
        "use_supabase": _use_supabase(),
    }
    if _use_supabase():
        payload["supabase"] = supa_health()
    else:
        payload["supabase"] = {"ok": False, "mode": "memory-only"}
    return jsonify(payload), 200


@app.route("/render", methods=["POST"])
@require_api_key
def render_sync() -> tuple:
    client_id = request.remote_addr or "unknown"
    if _is_rate_limited(client_id):
        return (
            jsonify(
                {
                    "error": "Rate limit exceeded",
                    "limit": RATE_LIMIT_MAX_REQUESTS,
                    "window_seconds": RATE_LIMIT_WINDOW,
                }
            ),
            429,
        )

    data = request.get_json(force=True, silent=True) or {}
    validated, error = _validate_render_payload(data)
    if validated is None:
        return jsonify({"error": error}), 400

    code, scene_name = validated
    result = _run_manim_render(code, scene_name)

    if not result["success"]:
        status_code = 504 if "timed out" in (result["error"] or "").lower() else 500
        resp = {"error": result["error"]}
        if result.get("stderr"):
            resp["stderr"] = result["stderr"]
        return jsonify(resp), status_code

    return send_file(
        result["video_path"],
        mimetype="video/mp4",
        as_attachment=True,
        download_name=f"{scene_name}.mp4",
    )


@app.route("/render-async", methods=["POST"])
@require_api_key
def render_async() -> tuple:
    client_id = request.remote_addr or "unknown"
    if _is_rate_limited(client_id):
        return (
            jsonify(
                {
                    "error": "Rate limit exceeded",
                    "limit": RATE_LIMIT_MAX_REQUESTS,
                    "window_seconds": RATE_LIMIT_WINDOW,
                }
            ),
            429,
        )

    data = request.get_json(force=True, silent=True) or {}
    validated, error = _validate_render_payload(data)
    if validated is None:
        return jsonify({"error": error}), 400

    code, scene_name = validated
    job_id = _register_job(code, scene_name, client_ip=client_id)

    def _background_render() -> None:
        result = _run_manim_render(code, scene_name, job_id=job_id)
        if result["success"]:
            video_url = result.get("video_url")
            _update_job(
                job_id,
                status=JobStatus.DONE,
                video_path=video_url or result["video_path"],
            )
        else:
            _update_job(
                job_id,
                status=JobStatus.FAILED,
                error_message=result["error"],
                stderr=result.get("stderr"),
            )
            if _use_supabase():
                supa_insert_log(
                    job_id=job_id,
                    level="error",
                    stage="render",
                    message="Rendering failed",
                    detail=result.get("error"),
                )

    thread = threading.Thread(target=_background_render, daemon=True)
    thread.start()

    return (
        jsonify(
            {
                "job_id": job_id,
                "status": JobStatus.PENDING.value,
                "status_url": f"/status/{job_id}",
                "download_url": f"/download/{job_id}",
            }
        ),
        202,
    )


@app.route("/status/<job_id>", methods=["GET"])
@require_api_key
def get_status(job_id: str) -> tuple:
    job = _get_job(job_id)
    if job is None:
        return jsonify({"error": "Job not found"}), 404

    resp = {
        "job_id": job.job_id,
        "status": job.status.value,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }
    if job.error_message:
        resp["error"] = job.error_message
    if job.stderr:
        resp["stderr"] = job.stderr
    return jsonify(resp), 200


@app.route("/download/<job_id>", methods=["GET"])
@require_api_key
def download_video(job_id: str) -> tuple:
    job = _get_job(job_id)
    if job is None:
        return jsonify({"error": "Job not found"}), 404
    if job.status != JobStatus.DONE:
        return (
            jsonify(
                {
                    "error": "Video not ready",
                    "status": job.status.value,
                }
            ),
            409,
        )

    # If video_path is a URL (Supabase Storage), redirect to it
    if job.video_path and job.video_path.startswith("http"):
        return jsonify({
            "ok": True,
            "video_url": job.video_path,
            "scene_name": job.scene_name,
        }), 200

    if not job.video_path or not Path(job.video_path).exists():
        return jsonify({"error": "Video file missing"}), 500

    return send_file(
        job.video_path,
        mimetype="video/mp4",
        as_attachment=True,
        download_name=f"{job.scene_name}.mp4",
    )


# ---------------------------------------------------------------------------
# Error Handlers
# ---------------------------------------------------------------------------

@app.errorhandler(413)
@app.errorhandler(RequestEntityTooLarge)
def handle_too_large(e):
    return jsonify({"error": f"Payload too large. Max code size is {MAX_CODE_SIZE} bytes."}), 413


@app.errorhandler(404)
def handle_not_found(e):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def handle_server_error(e):
    return jsonify({"error": "Internal server error"}), 500


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)

"""
Manim Rendering Backend API

A lightweight Flask-based API for rendering Manim scenes.
Supports synchronous and asynchronous rendering with proper
error handling, rate limiting, and security controls.
"""

from __future__ import annotations

import ast
import functools
import os
import signal
import shutil
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from supabase_client import (
    SupabaseReadUnavailable,
)
from supabase_client import (
    get_job as supa_get_job,
)
from supabase_client import (
    health_check as supa_health,
)
from supabase_client import (
    insert_job as supa_insert_job,
)
from supabase_client import (
    insert_log as supa_insert_log,
)
from supabase_client import (
    is_configured as supa_is_configured,
)
from supabase_client import (
    list_jobs_by_status as supa_list_jobs_by_status,
)
from supabase_client import (
    update_job as supa_update_job,
)
from supabase_client import (
    upload_video as supa_upload_video,
)
from werkzeug.exceptions import RequestEntityTooLarge

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_KEY = os.environ.get("MANIM_API_KEY", "dev-key-change-in-production")
MAX_CODE_SIZE = 100 * 1024  # 100 KB
DEFAULT_TIMEOUT = int(os.environ.get("MANIM_RENDER_TIMEOUT_SECONDS", "180"))
SEGMENT_RENDER_THRESHOLD = int(os.environ.get("MANIM_SEGMENT_RENDER_THRESHOLD", "10"))
SEGMENT_RENDER_SIZE = int(os.environ.get("MANIM_SEGMENT_RENDER_SIZE", "6"))
SEGMENT_RENDER_TIMEOUT = int(os.environ.get("MANIM_SEGMENT_RENDER_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT)))
MANIM_RENDER_QUALITY = os.environ.get("MANIM_RENDER_QUALITY", "-ql").strip() or "-ql"
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX_REQUESTS = 10
ORPHAN_JOB_THRESHOLD_SECONDS = int(
    os.environ.get("ORPHAN_JOB_THRESHOLD_SECONDS", str(DEFAULT_TIMEOUT + 60))
)
ORPHAN_JOB_SCAN_SECONDS = 30
ORPHAN_JOB_MESSAGE = "Render instance restarted unexpectedly. Please resubmit."

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
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RenderSegment:
    index: int
    start: int
    end: int


_jobs: dict[str, RenderJob] = {}
_jobs_lock = threading.Lock()
_active_render_threads: set[str] = set()
_active_render_threads_lock = threading.Lock()
_orphan_reaper_lock = threading.Lock()
_orphan_reaper_started = False


def _use_supabase() -> bool:
    return supa_is_configured()


def _row_to_job(row: dict[str, Any]) -> RenderJob:
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
        metadata=row.get("metadata") or {},
    )


def _register_job(
    code: str,
    scene_name: str,
    client_ip: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    job_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    metadata = metadata or {}
    if _use_supabase():
        row = supa_insert_job(
            job_id=job_id,
            code=code,
            scene_name=scene_name,
            client_ip=client_ip,
            metadata=metadata,
        )
        if row is None:
            raise RuntimeError("Failed to persist job to Supabase")
    job = RenderJob(
        job_id=job_id,
        status=JobStatus.PENDING,
        created_at=now,
        updated_at=now,
        code=code,
        scene_name=scene_name,
        metadata=metadata,
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
    metadata: dict[str, Any] | None = None,
) -> None:
    row: dict[str, Any] | None = None
    if _use_supabase():
        expected_status = None
        if status in {JobStatus.DONE, JobStatus.FAILED}:
            expected_status = [JobStatus.PENDING.value, JobStatus.RUNNING.value]
        row = supa_update_job(
            job_id=job_id,
            status=status.value if status else None,
            expected_status=expected_status,
            video_path=video_path,
            error_message=error_message,
            stderr=stderr,
            metadata=metadata,
        )
        if row is None:
            print(f"[update_job] Supabase update failed for {job_id[:8]}")
            return
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            if row and row.get("job_id"):
                job = _row_to_job(row)
                _jobs[job_id] = job
            elif _use_supabase():
                try:
                    fresh_row = supa_get_job(job_id)
                except SupabaseReadUnavailable:
                    fresh_row = None
                if fresh_row:
                    job = _row_to_job(fresh_row)
                    _jobs[job_id] = job
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
        if metadata is not None:
            job.metadata = metadata
        job.updated_at = datetime.now(UTC).isoformat()


def _get_job(job_id: str) -> RenderJob | None:
    if _use_supabase():
        try:
            row = supa_get_job(job_id)
        except SupabaseReadUnavailable:
            with _jobs_lock:
                return _jobs.get(job_id)
        if row:
            job = _row_to_job(row)
            with _jobs_lock:
                _jobs[job_id] = job
            return job
        with _jobs_lock:
            _jobs.pop(job_id, None)
        return None
    with _jobs_lock:
        return _jobs.get(job_id)


def _recover_jobs_from_supabase() -> None:
    if not _use_supabase():
        return
    rows = supa_list_jobs_by_status(["pending", "running"])
    recovered_jobs: list[RenderJob] = []
    with _jobs_lock:
        for row in rows:
            try:
                job = _row_to_job(row)
                _jobs[row["job_id"]] = job
                recovered_jobs.append(job)
            except (KeyError, ValueError) as exc:
                print(f"[recovery] Skipping invalid job row: {exc}")
    print(f"[recovery] Restored {len(rows)} jobs from Supabase")
    for job in recovered_jobs:
        render_mode = str((job.metadata or {}).get("render_mode") or "auto")
        _start_render_job_thread(job.job_id, job.code, job.scene_name, render_mode=render_mode)


def _parse_supabase_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _reap_orphan_jobs() -> None:
    if not _use_supabase():
        return
    now = datetime.now(UTC)
    rows = supa_list_jobs_by_status(["pending", "running"])
    for row in rows:
        try:
            updated_at = _parse_supabase_datetime(row["updated_at"])
        except (KeyError, ValueError):
            continue
        if (now - updated_at).total_seconds() <= ORPHAN_JOB_THRESHOLD_SECONDS:
            continue
        updated = supa_update_job(
            job_id=row["job_id"],
            status=JobStatus.FAILED.value,
            expected_status=row["status"],
            error_message=ORPHAN_JOB_MESSAGE,
        )
        if updated is None:
            continue
        with _jobs_lock:
            job = _jobs.get(row["job_id"])
            if job:
                job.status = JobStatus.FAILED
                job.error_message = ORPHAN_JOB_MESSAGE
                job.updated_at = datetime.now(UTC).isoformat()
        print(f"[reaper] Orphan job {row['job_id'][:8]} marked as failed")


def _start_orphan_reaper() -> None:
    global _orphan_reaper_started
    with _orphan_reaper_lock:
        if _orphan_reaper_started:
            return
        _orphan_reaper_started = True

    def loop() -> None:
        while True:
            time.sleep(ORPHAN_JOB_SCAN_SECONDS)
            try:
                _reap_orphan_jobs()
            except Exception as exc:
                print(f"[reaper] Error: {exc}")

    thread = threading.Thread(target=loop, daemon=True, name="orphan-job-reaper")
    thread.start()


# ---------------------------------------------------------------------------
# Rendering Logic
# ---------------------------------------------------------------------------

def _count_render_events(code: str) -> int:
    """Count self.play/self.wait calls in the first construct() method."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return 0

    for class_node in [node for node in tree.body if isinstance(node, ast.ClassDef)]:
        for item in class_node.body:
            if not isinstance(item, ast.FunctionDef) or item.name != "construct":
                continue
            count = 0
            for node in ast.walk(item):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr in {"play", "wait"}
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "self"
                ):
                    count += 1
            return count
    return 0


def _plan_render_segments(
    code: str,
    mode: str = "auto",
    threshold: int = SEGMENT_RENDER_THRESHOLD,
    segment_size: int = SEGMENT_RENDER_SIZE,
) -> list[RenderSegment]:
    event_count = _count_render_events(code)
    if mode == "single" or event_count <= 0:
        return []
    if mode == "auto" and event_count <= threshold:
        return []

    size = max(1, segment_size)
    return [
        RenderSegment(index=index + 1, start=start, end=min(start + size - 1, event_count - 1))
        for index, start in enumerate(range(0, event_count, size))
    ]


def _render_metadata(
    mode: str,
    stage: str,
    segments: list[RenderSegment],
    completed: int = 0,
    current: int | None = None,
) -> dict[str, Any]:
    return {
        "render_mode": mode,
        "stage": stage,
        "progress": {
            "completed": completed,
            "total": len(segments),
            "current": current,
        },
        "segments": [
            {
                "index": segment.index,
                "start": segment.start,
                "end": segment.end,
                "status": (
                    "done"
                    if segment.index <= completed
                    else "running"
                    if current == segment.index
                    else "pending"
                ),
            }
            for segment in segments
        ],
    }


def _build_manim_command(
    scene_file: Path,
    scene_name: str,
    workspace: Path,
    segment: RenderSegment | None = None,
) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "manim",
        MANIM_RENDER_QUALITY,
        "--media_dir",
        str(workspace),
        str(scene_file),
        scene_name,
    ]
    if segment is not None:
        cmd.extend(["-n", f"{segment.start},{segment.end}"])
    return cmd


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


def _run_process(
    cmd: list[str],
    workspace: Path,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(workspace),
            start_new_session=True,
        )
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except Exception:
            proc.kill()
        stdout, stderr = proc.communicate()
        return {
            "success": False,
            "video_path": None,
            "error": f"Rendering timed out after {timeout}s",
            "stderr": stderr or getattr(exc, "stderr", None),
        }
    except Exception as exc:
        return {
            "success": False,
            "video_path": None,
            "error": str(exc),
            "stderr": None,
        }

    if proc.returncode != 0:
        return {
            "success": False,
            "video_path": None,
            "error": "Manim rendering failed",
            "stderr": stderr,
        }

    return {"success": True, "stderr": stderr}


def _copy_render_output(video_path: Path, scene_name: str, job_id: str | None) -> Path:
    output_filename = f"{job_id or uuid.uuid4().hex}_{scene_name}.mp4"
    output_path = OUTPUT_DIR / output_filename
    shutil.copy(str(video_path), str(output_path))
    return output_path


def _write_concat_manifest(segment_paths: list[Path], manifest_path: Path) -> None:
    lines = []
    for path in segment_paths:
        safe_path = str(path.resolve()).replace("'", "'\\''")
        lines.append(f"file '{safe_path}'")
    manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _concat_segment_videos(segment_paths: list[Path], output_path: Path, workspace: Path) -> dict[str, Any]:
    manifest = workspace / "segments.txt"
    _write_concat_manifest(segment_paths, manifest)
    copy_cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(manifest),
        "-c",
        "copy",
        str(output_path),
    ]
    result = _run_process(copy_cmd, workspace, timeout=SEGMENT_RENDER_TIMEOUT)
    if result["success"] and output_path.exists():
        return result

    transcode_cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(manifest),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        str(output_path),
    ]
    return _run_process(transcode_cmd, workspace, timeout=SEGMENT_RENDER_TIMEOUT)


def _upload_or_keep_video(
    video_path: Path,
    scene_name: str,
    job_id: str | None,
    stderr: str | None,
) -> dict[str, Any]:
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
        else:
            return {
                "success": False,
                "video_path": None,
                "error": "Video rendered but failed to upload to persistent storage",
                "stderr": stderr,
            }

    output_path = _copy_render_output(video_path, scene_name, job_id)
    return {
        "success": True,
        "video_path": supa_video_url or str(output_path),
        "video_url": supa_video_url,
        "error": None,
        "stderr": stderr,
    }


def _run_single_manim_render(
    scene_file: Path,
    scene_name: str,
    workspace: Path,
    timeout: int,
    segment: RenderSegment | None = None,
) -> dict[str, Any]:
    result = _run_process(
        _build_manim_command(scene_file, scene_name, workspace, segment=segment),
        workspace,
        timeout=timeout,
    )
    if not result["success"]:
        return result

    video_path = _find_rendered_video(workspace, scene_name)
    if video_path is None or not video_path.exists():
        return {
            "success": False,
            "video_path": None,
            "error": "Video file not found after rendering",
            "stderr": result.get("stderr"),
        }
    return {"success": True, "video_path": str(video_path), "stderr": result.get("stderr")}


def _run_manim_render(
    code: str,
    scene_name: str,
    job_id: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    render_mode: str = "single",
) -> dict[str, Any]:
    """
    Execute manim render. Returns dict with keys:
    - success: bool
    - video_path: str | None
    - error: str | None
    - stderr: str | None
    """
    workspace = TEMP_DIR / f"render_{uuid.uuid4().hex}"
    workspace.mkdir(parents=True, exist_ok=True)

    scene_file = workspace / "scene.py"
    scene_file.write_text(code, encoding="utf-8")
    segments = _plan_render_segments(code, mode=render_mode)

    if job_id:
        _update_job(
            job_id,
            status=JobStatus.RUNNING,
            metadata=_render_metadata("segmented" if segments else "single", "rendering", segments),
        )

    try:
        if not segments:
            result = _run_single_manim_render(scene_file, scene_name, workspace, timeout)
            if not result["success"]:
                return result
            return _upload_or_keep_video(Path(result["video_path"]), scene_name, job_id, result.get("stderr"))

        segment_paths: list[Path] = []
        stderr_parts: list[str] = []
        for segment in segments:
            if job_id:
                _update_job(
                    job_id,
                    metadata=_render_metadata(
                        "segmented",
                        "rendering_segment",
                        segments,
                        completed=len(segment_paths),
                        current=segment.index,
                    ),
                )
            result = _run_single_manim_render(
                scene_file,
                scene_name,
                workspace,
                timeout=SEGMENT_RENDER_TIMEOUT,
                segment=segment,
            )
            if not result["success"]:
                return result
            stable_segment_path = workspace / f"segment_{segment.index}.mp4"
            shutil.copy(str(result["video_path"]), str(stable_segment_path))
            segment_paths.append(stable_segment_path)
            if result.get("stderr"):
                stderr_parts.append(result["stderr"])

        if job_id:
            _update_job(
                job_id,
                metadata=_render_metadata("segmented", "concatenating", segments, completed=len(segment_paths)),
            )
        final_path = workspace / f"{scene_name}_segmented.mp4"
        concat_result = _concat_segment_videos(segment_paths, final_path, workspace)
        if not concat_result["success"] or not final_path.exists():
            return {
                "success": False,
                "video_path": None,
                "error": concat_result.get("error") or "Segment concat failed",
                "stderr": concat_result.get("stderr"),
            }
        if concat_result.get("stderr"):
            stderr_parts.append(concat_result["stderr"])
        return _upload_or_keep_video(final_path, scene_name, job_id, "\n".join(stderr_parts) or None)
    finally:
        _cleanup_workspace(workspace)


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


def _start_render_job_thread(job_id: str, code: str, scene_name: str, render_mode: str = "auto") -> bool:
    with _active_render_threads_lock:
        if job_id in _active_render_threads:
            return False
        _active_render_threads.add(job_id)

    def _background_render() -> None:
        try:
            result = _run_manim_render(code, scene_name, job_id=job_id, render_mode=render_mode)
            current_job = _get_job(job_id)
            current_metadata = dict(current_job.metadata if current_job else {})
            if result["success"]:
                video_url = result.get("video_url")
                current_metadata["stage"] = "done"
                _update_job(
                    job_id,
                    status=JobStatus.DONE,
                    video_path=video_url or result["video_path"],
                    metadata=current_metadata,
                )
            else:
                current_metadata["stage"] = "failed"
                _update_job(
                    job_id,
                    status=JobStatus.FAILED,
                    error_message=result["error"],
                    stderr=result.get("stderr"),
                    metadata=current_metadata,
                )
                if _use_supabase():
                    supa_insert_log(
                        job_id=job_id,
                        level="error",
                        stage="render",
                        message="Rendering failed",
                        detail=result.get("error"),
                    )
        finally:
            with _active_render_threads_lock:
                _active_render_threads.discard(job_id)

    thread = threading.Thread(target=_background_render, daemon=True)
    thread.start()
    return True


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/health", methods=["GET"])
def health() -> tuple:
    payload = {"status": "ok", "timestamp": datetime.now(UTC).isoformat()}
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
    render_mode = str(data.get("render_mode", "auto")).strip().lower()
    if render_mode not in {"auto", "single", "segmented"}:
        return jsonify({"error": "Field 'render_mode' must be auto, single, or segmented"}), 400
    try:
        initial_segments = _plan_render_segments(code, mode=render_mode)
        initial_metadata = _render_metadata(
            "segmented" if initial_segments else "single",
            "pending",
            initial_segments,
        )
        job_id = _register_job(code, scene_name, client_ip=client_id, metadata=initial_metadata)
    except RuntimeError:
        return jsonify({"error": "Failed to persist render job. Please try again."}), 500

    _start_render_job_thread(job_id, code, scene_name, render_mode=render_mode)

    return (
        jsonify(
            {
                "job_id": job_id,
                "status": JobStatus.PENDING.value,
                "status_url": f"/status/{job_id}",
                "download_url": f"/download/{job_id}",
                "render_mode": initial_metadata["render_mode"],
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
    if job.metadata:
        resp["render_mode"] = job.metadata.get("render_mode")
        resp["stage"] = job.metadata.get("stage")
        resp["progress"] = job.metadata.get("progress")
        resp["segments"] = job.metadata.get("segments")
    if job.error_message:
        resp["error"] = job.error_message
    if job.stderr:
        resp["stderr"] = job.stderr
    if job.status == JobStatus.DONE and job.video_path:
        if job.video_path.startswith("http"):
            resp["video_url"] = job.video_path
        resp["download_url"] = f"/download/{job_id}"
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

def initialize_app() -> None:
    if _use_supabase():
        _recover_jobs_from_supabase()
        _start_orphan_reaper()
    else:
        print("[init] Supabase not configured, running in memory-only mode")


@app.before_request
def _initialize_once() -> None:
    if app.config.get("_PERSISTENCE_INITIALIZED"):
        return
    initialize_app()
    app.config["_PERSISTENCE_INITIALIZED"] = True


if __name__ == "__main__":
    initialize_app()
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)

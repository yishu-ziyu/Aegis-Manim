"""
Supabase client for render backend.

Uses raw REST API via requests to minimize dependencies.
No heavy supabase-py client needed.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

# Storage bucket name for rendered videos
STORAGE_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "manim-videos")


def _supabase_url() -> str:
    url = os.environ.get("SUPABASE_URL", "")
    if not url:
        url = "https://qrmmlolsslnxiamznicf.supabase.co"
    return url.rstrip("/")


def _supabase_service_key() -> str:
    return os.environ.get("SUPABASE_SERVICE_KEY", "")


# Headers for service-role requests (bypasses RLS)
_HEADERS_SR = lambda: {
    "apikey": _supabase_service_key(),
    "Authorization": f"Bearer {_supabase_service_key()}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


def _base_url() -> str:
    url = _supabase_url()
    if not url:
        raise RuntimeError("SUPABASE_URL is not configured")
    return url


def _postgrest_url(table: str) -> str:
    return f"{_base_url()}/rest/v1/{table}"


def _storage_url(path: str) -> str:
    return f"{_base_url()}/storage/v1/{path}"


# ---------------------------------------------------------------------------
# Render Jobs
# ---------------------------------------------------------------------------

def insert_job(
    job_id: str,
    code: str,
    scene_name: str,
    client_ip: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Insert a new render job into Supabase."""
    payload = {
        "job_id": job_id,
        "status": "pending",
        "code": code,
        "scene_name": scene_name,
        "client_ip": client_ip,
        "metadata": metadata or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    resp = requests.post(
        _postgrest_url("render_jobs"),
        headers=_HEADERS_SR(),
        json=payload,
    )
    if resp.status_code in (201, 200):
        data = resp.json()
        return data[0] if isinstance(data, list) else data
    print(f"[supabase] insert_job failed: {resp.status_code} {resp.text[:200]}")
    return None


def update_job(
    job_id: str,
    status: str | None = None,
    video_path: str | None = None,
    video_bucket: str | None = None,
    video_name: str | None = None,
    error_message: str | None = None,
    stderr: str | None = None,
) -> dict[str, Any] | None:
    """Update render job fields."""
    payload: dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if status is not None:
        payload["status"] = status
    if video_path is not None:
        payload["video_path"] = video_path
    if video_bucket is not None:
        payload["video_bucket"] = video_bucket
    if video_name is not None:
        payload["video_name"] = video_name
    if error_message is not None:
        payload["error_message"] = error_message
    if stderr is not None:
        payload["stderr"] = stderr

    resp = requests.patch(
        f"{_postgrest_url('render_jobs')}?job_id=eq.{job_id}",
        headers=_HEADERS_SR(),
        json=payload,
    )
    if resp.status_code in (200, 204):
        if resp.status_code == 200:
            data = resp.json()
            return data[0] if isinstance(data, list) else data
        return {"ok": True}
    print(f"[supabase] update_job failed: {resp.status_code} {resp.text[:200]}")
    return None


def get_job(job_id: str) -> dict[str, Any] | None:
    """Fetch a single render job by job_id."""
    resp = requests.get(
        f"{_postgrest_url('render_jobs')}?job_id=eq.{job_id}&limit=1",
        headers={"apikey": _supabase_service_key(), "Authorization": f"Bearer {_supabase_service_key()}"},
    )
    if resp.status_code == 200:
        data = resp.json()
        return data[0] if isinstance(data, list) and data else None
    print(f"[supabase] get_job failed: {resp.status_code} {resp.text[:200]}")
    return None


# ---------------------------------------------------------------------------
# Job Logs
# ---------------------------------------------------------------------------

def insert_log(
    job_id: str,
    message: str,
    level: str = "info",
    stage: str | None = None,
    detail: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Insert a log entry for a job."""
    payload = {
        "job_id": job_id,
        "level": level,
        "stage": stage,
        "message": message,
        "detail": detail,
        "metadata": metadata or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    resp = requests.post(
        _postgrest_url("job_logs"),
        headers=_HEADERS_SR(),
        json=payload,
    )
    if resp.status_code in (201, 200):
        data = resp.json()
        return data[0] if isinstance(data, list) else data
    return None


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def upload_video(
    job_id: str,
    file_path: str | Path,
    content_type: str = "video/mp4",
) -> str | None:
    """Upload a video file to Supabase Storage. Returns public URL or None."""
    file_path = Path(file_path)
    if not file_path.exists():
        print(f"[supabase] upload_video: file not found {file_path}")
        return None

    # Ensure bucket exists (Supabase default buckets: avatars, etc.)
    # We'll upload to the configured bucket
    storage_path = f"{job_id}/{file_path.name}"
    upload_url = _storage_url(f"object/{STORAGE_BUCKET}/{storage_path}")

    headers = {
        "apikey": _supabase_service_key(),
        "Authorization": f"Bearer {_supabase_service_key()}",
    }

    with open(file_path, "rb") as f:
        files = {"file": (file_path.name, f, content_type)}
        resp = requests.post(upload_url, headers=headers, files=files)

    if resp.status_code in (200, 201):
        # Build public URL
        public_url = f"{_base_url()}/storage/v1/object/public/{STORAGE_BUCKET}/{storage_path}"
        return public_url

    print(f"[supabase] upload_video failed: {resp.status_code} {resp.text[:300]}")
    return None


def get_public_video_url(video_path: str) -> str | None:
    """Get public URL for a video already uploaded."""
    if not video_path:
        return None
    if video_path.startswith("http"):
        return video_path
    return f"{_base_url()}/storage/v1/object/public/{STORAGE_BUCKET}/{video_path}"


# ---------------------------------------------------------------------------
# Health / Config checks
# ---------------------------------------------------------------------------

def is_configured() -> bool:
    return bool(_supabase_url() and _supabase_service_key())


def health_check() -> dict[str, Any]:
    """Quick health check against Supabase."""
    if not is_configured():
        return {"ok": False, "error": "Supabase not configured"}
    try:
        key = _supabase_service_key()
        resp = requests.get(
            f"{_base_url()}/rest/v1/",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            timeout=5,
        )
        return {"ok": resp.status_code < 400, "status": resp.status_code}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

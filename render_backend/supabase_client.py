"""
Supabase client for render backend.

Uses raw REST API via requests to minimize dependencies.
No heavy supabase-py client needed.
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

# Storage bucket name for rendered videos
STORAGE_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "manim-videos")
PUBLIC_COMMUNITY_STATUSES = ("published", "featured")
COMMUNITY_STATUS_VALUES = ("candidate", "published", "featured", "quarantine", "hidden", "rejected")
COMMUNITY_REVIEW_DECISIONS = {
    "approve": "published",
    "publish": "published",
    "feature": "featured",
    "quarantine": "quarantine",
    "hide": "hidden",
    "reject": "rejected",
}


class SupabaseReadUnavailable(RuntimeError):
    """Raised when Supabase cannot answer whether a job exists."""


def _supabase_url() -> str:
    return os.environ.get("SUPABASE_URL", "").strip().rstrip("/")


def _supabase_service_key() -> str:
    # Render env vars may contain newlines/spaces in the MIDDLE of the value
    return "".join(os.environ.get("SUPABASE_SERVICE_KEY", "").split())


def _headers_sr() -> dict[str, str]:
    """Headers for service-role requests that bypass RLS."""
    service_key = _supabase_service_key()
    return {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
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


def _request_with_retries(method: str, url: str, **kwargs) -> requests.Response | None:
    last_error: Exception | None = None
    timeout = kwargs.pop("timeout", 10)
    for attempt in range(3):
        try:
            return requests.request(method, url, timeout=timeout, **kwargs)
        except requests.RequestException as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(0.2 * (attempt + 1))
    print(f"[supabase] {method.upper()} failed after retries: {last_error}")
    return None


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
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    resp = _request_with_retries(
        "post",
        _postgrest_url("render_jobs"),
        headers=_headers_sr(),
        json=payload,
    )
    if resp is None:
        return None
    if resp.status_code in (201, 200):
        data = resp.json()
        return data[0] if isinstance(data, list) else data
    print(f"[supabase] insert_job failed: {resp.status_code} {resp.text[:200]}")
    return None


def update_job(
    job_id: str,
    status: str | None = None,
    expected_status: str | list[str] | tuple[str, ...] | None = None,
    video_path: str | None = None,
    video_bucket: str | None = None,
    video_name: str | None = None,
    error_message: str | None = None,
    stderr: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Update render job fields."""
    payload: dict[str, Any] = {"updated_at": datetime.now(UTC).isoformat()}
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
    if metadata is not None:
        payload["metadata"] = metadata

    filters = f"job_id=eq.{job_id}"
    if expected_status is not None:
        if isinstance(expected_status, str):
            filters = f"{filters}&status=eq.{expected_status}"
        else:
            status_filter = ",".join(expected_status)
            filters = f"{filters}&status=in.({status_filter})"

    resp = _request_with_retries(
        "patch",
        f"{_postgrest_url('render_jobs')}?{filters}",
        headers=_headers_sr(),
        json=payload,
    )
    if resp is None:
        return None
    if resp.status_code in (200, 204):
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                return data[0] if data else None
            return data
        return {"ok": True}
    print(f"[supabase] update_job failed: {resp.status_code} {resp.text[:200]}")
    return None


def get_job(job_id: str) -> dict[str, Any] | None:
    """Fetch a single render job by job_id."""
    resp = _request_with_retries(
        "get",
        f"{_postgrest_url('render_jobs')}?job_id=eq.{job_id}&limit=1",
        headers={"apikey": _supabase_service_key(), "Authorization": f"Bearer {_supabase_service_key()}"},
    )
    if resp is None:
        raise SupabaseReadUnavailable(f"Supabase read unavailable for job {job_id}")
    if resp.status_code == 200:
        data = resp.json()
        return data[0] if isinstance(data, list) and data else None
    print(f"[supabase] get_job failed: {resp.status_code} {resp.text[:200]}")
    raise SupabaseReadUnavailable(f"Supabase get_job failed with status {resp.status_code}")


def list_jobs_by_status(statuses: list[str]) -> list[dict[str, Any]]:
    """Fetch all render jobs with any of the given statuses."""
    if not statuses:
        return []
    status_filter = ",".join(statuses)
    resp = _request_with_retries(
        "get",
        f"{_postgrest_url('render_jobs')}?status=in.({status_filter})&order=updated_at.asc",
        headers={"apikey": _supabase_service_key(), "Authorization": f"Bearer {_supabase_service_key()}"},
    )
    if resp is None:
        return []
    if resp.status_code == 200:
        data = resp.json()
        return data if isinstance(data, list) else []
    print(f"[supabase] list_jobs_by_status failed: {resp.status_code} {resp.text[:200]}")
    return []


def job_exists(job_id: str) -> bool:
    """Return whether a render job exists without fetching its full payload."""
    resp = _request_with_retries(
        "get",
        f"{_postgrest_url('render_jobs')}?job_id=eq.{job_id}&select=job_id&limit=1",
        headers={"apikey": _supabase_service_key(), "Authorization": f"Bearer {_supabase_service_key()}"},
    )
    if resp is None or resp.status_code != 200:
        return False
    data = resp.json()
    return isinstance(data, list) and bool(data)


def update_job_heartbeat(job_id: str) -> bool:
    """Refresh updated_at for a running job."""
    return update_job(job_id=job_id) is not None


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
        "created_at": datetime.now(UTC).isoformat(),
    }
    resp = _request_with_retries(
        "post",
        _postgrest_url("job_logs"),
        headers=_headers_sr(),
        json=payload,
    )
    if resp is None:
        return None
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

    try:
        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f, content_type)}
            resp = requests.post(upload_url, headers=headers, files=files, timeout=60)
    except requests.RequestException as exc:
        print(f"[supabase] upload_video failed: {exc}")
        return None

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
# Community Works
# ---------------------------------------------------------------------------

def normalize_work_prompt(prompt: str) -> str:
    """Normalize prompt text for simple repository lookup."""
    return " ".join(str(prompt or "").strip().lower().split())


def _community_score(rating_avg: float = 0.0, rating_count: int = 0, reuse_count: int = 0) -> float:
    rating_signal = max(0.0, min(5.0, rating_avg)) / 5.0
    confidence = min(1.0, rating_count / 5.0)
    reuse_signal = min(1.0, reuse_count / 25.0)
    return round(rating_signal * 0.72 + confidence * 0.16 + reuse_signal * 0.12, 4)


def _normalize_community_status(status: str | None, default: str = "candidate") -> str:
    status = (status or default).strip().lower()
    return status if status in COMMUNITY_STATUS_VALUES else default


def _community_public_status_filter() -> str:
    return f"status=in.({','.join(PUBLIC_COMMUNITY_STATUSES)})"


def _repository_stage_for_status(status: str) -> str:
    return {
        "candidate": "candidate",
        "published": "public",
        "featured": "featured",
        "quarantine": "quarantine",
        "hidden": "hidden",
        "rejected": "rejected",
    }.get(status, "candidate")


def _status_after_quality_signals(
    current_status: str,
    rating_avg: float,
    rating_count: int,
    reuse_count: int,
) -> str:
    current_status = _normalize_community_status(current_status)
    if current_status in {"candidate", "hidden", "rejected"}:
        return current_status
    if rating_count >= 5 and rating_avg < 3.0:
        return "quarantine"
    if rating_count >= 5 and _community_score(rating_avg, rating_count, reuse_count) >= 0.86:
        return "featured"
    return current_status


def _merge_repository_metadata(
    metadata: dict[str, Any] | None,
    *,
    status: str,
    decision: str | None = None,
) -> dict[str, Any]:
    merged = dict(metadata or {})
    merged["review_status"] = _review_status_for_lifecycle(status)
    merged["review_stage"] = _repository_stage_for_status(status)
    merged["repository_decision"] = decision or ("pending_review" if status == "candidate" else "public")
    merged["lifecycle_status"] = status
    return merged


def _review_status_for_lifecycle(status: str) -> str:
    return {
        "candidate": "pending",
        "published": "approved",
        "featured": "approved",
        "quarantine": "needs_revision",
        "hidden": "hidden",
        "rejected": "rejected",
    }.get(status, "pending")


def _is_missing_table(resp: requests.Response | None) -> bool:
    if resp is None or resp.status_code != 404:
        return False
    return "could not find the table" in resp.text.lower() or "pgrst205" in resp.text.lower()


def _community_metadata(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata") or {}
    return metadata if isinstance(metadata, dict) else {}


def _fallback_work_from_render_job(row: dict[str, Any], *, public_only: bool = True) -> dict[str, Any] | None:
    metadata = _community_metadata(row)
    status = _normalize_community_status(metadata.get("community_status"))
    if public_only and status not in PUBLIC_COMMUNITY_STATUSES:
        return None
    job_id = row.get("job_id")
    if not job_id:
        return None
    rating_count = int(metadata.get("community_rating_count") or 0)
    rating_avg = float(metadata.get("community_rating_avg") or 0)
    reuse_count = int(metadata.get("community_reuse_count") or 0)
    return {
        "id": job_id,
        "title": metadata.get("community_title") or metadata.get("community_prompt") or "Aegis community work",
        "prompt": metadata.get("community_prompt") or "",
        "prompt_normalized": metadata.get("community_prompt_normalized") or "",
        "scene_name": row.get("scene_name") or "GeneratedScene",
        "code": row.get("code") or "",
        "video_url": row.get("video_path") or get_public_video_url(row.get("video_name") or ""),
        "render_job_id": job_id,
        "author_label": metadata.get("community_author_label"),
        "tags": metadata.get("community_tags") or [],
        "status": status,
        "rating_avg": rating_avg,
        "rating_count": rating_count,
        "reuse_count": reuse_count,
        "quality_score": float(metadata.get("community_quality_score") or _community_score(rating_avg, rating_count, reuse_count)),
        "created_at": metadata.get("community_published_at") or row.get("created_at"),
        "updated_at": metadata.get("community_updated_at") or row.get("updated_at"),
        "metadata": {
            "review_stage": metadata.get("community_review_stage"),
            "review_status": metadata.get("community_review_status"),
            "repository_decision": metadata.get("community_repository_decision"),
            "reviewer_label": metadata.get("community_reviewer_label"),
            "review_note": metadata.get("community_review_note"),
            "reviewed_at": metadata.get("community_reviewed_at"),
        },
    }


def _patch_render_job_metadata(job_id: str, metadata: dict[str, Any]) -> dict[str, Any] | None:
    payload = {
        "metadata": metadata,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    resp = _request_with_retries(
        "patch",
        f"{_postgrest_url('render_jobs')}?job_id=eq.{quote(job_id, safe='')}",
        headers=_headers_sr(),
        json=payload,
    )
    if resp is None or resp.status_code not in (200, 204):
        if resp is not None:
            print(f"[supabase] patch render_jobs metadata failed: {resp.status_code} {resp.text[:200]}")
        return None
    row = get_job(job_id)
    return _fallback_work_from_render_job(row, public_only=False) if row else None


def _search_community_works_from_render_jobs(query: str, limit: int) -> list[dict[str, Any]]:
    resp = _request_with_retries(
        "get",
        (
            f"{_postgrest_url('render_jobs')}?"
            "status=eq.done"
            "&metadata-%3E%3Ecommunity_status=in.(published,featured)"
            "&select=job_id,scene_name,code,video_path,video_name,metadata,created_at,updated_at"
            "&order=updated_at.desc"
            f"&limit={max(limit, 50)}"
        ),
        headers={"apikey": _supabase_service_key(), "Authorization": f"Bearer {_supabase_service_key()}"},
    )
    if resp is None or resp.status_code != 200:
        if resp is not None:
            print(f"[supabase] fallback community search failed: {resp.status_code} {resp.text[:200]}")
        return []
    normalized = normalize_work_prompt(query)
    rows = resp.json()
    works = [_fallback_work_from_render_job(row) for row in rows if isinstance(row, dict)]
    works = [work for work in works if work is not None]
    if normalized:
        works = [
            work
            for work in works
            if normalized in normalize_work_prompt(work.get("prompt", ""))
            or normalized in normalize_work_prompt(work.get("title", ""))
            or normalized in normalize_work_prompt(" ".join(work.get("tags") or []))
        ]
    works.sort(
        key=lambda work: (
            float(work.get("quality_score") or 0),
            float(work.get("rating_avg") or 0),
            int(work.get("reuse_count") or 0),
            str(work.get("updated_at") or ""),
        ),
        reverse=True,
    )
    return works[:limit]


def _list_review_queue_from_render_jobs(statuses: tuple[str, ...], limit: int) -> list[dict[str, Any]]:
    status_filter = ",".join(statuses)
    resp = _request_with_retries(
        "get",
        (
            f"{_postgrest_url('render_jobs')}?"
            "status=eq.done"
            f"&metadata-%3E%3Ecommunity_status=in.({status_filter})"
            "&select=job_id,scene_name,code,video_path,video_name,metadata,created_at,updated_at"
            "&order=updated_at.asc"
            f"&limit={limit}"
        ),
        headers={"apikey": _supabase_service_key(), "Authorization": f"Bearer {_supabase_service_key()}"},
    )
    if resp is None or resp.status_code != 200:
        if resp is not None:
            print(f"[supabase] fallback review queue failed: {resp.status_code} {resp.text[:200]}")
        return []
    rows = resp.json()
    works = [_fallback_work_from_render_job(row, public_only=False) for row in rows if isinstance(row, dict)]
    return [work for work in works if work is not None and work.get("status") in statuses][:limit]


def _insert_community_work_in_render_job(
    *,
    title: str,
    prompt: str,
    render_job_id: str | None,
    author_label: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    status: str = "candidate",
) -> dict[str, Any] | None:
    if not render_job_id:
        return None
    row = get_job(render_job_id)
    if not row:
        return None
    existing = _community_metadata(row)
    now = datetime.now(UTC).isoformat()
    status = _normalize_community_status(status)
    repository_metadata = _merge_repository_metadata(metadata, status=status)
    existing.update(
        {
            "community_status": status,
            "community_title": title.strip()[:120],
            "community_prompt": prompt.strip(),
            "community_prompt_normalized": normalize_work_prompt(prompt),
            "community_author_label": (author_label or "匿名用户").strip()[:80],
            "community_tags": tags or [],
            "community_source": repository_metadata.get("source", "aegis-web"),
            "community_review_stage": repository_metadata.get("review_stage"),
            "community_review_status": repository_metadata.get("review_status"),
            "community_repository_decision": repository_metadata.get("repository_decision"),
            "community_published_at": existing.get("community_published_at") or now,
            "community_updated_at": now,
            "community_rating_avg": float(existing.get("community_rating_avg") or 0),
            "community_rating_count": int(existing.get("community_rating_count") or 0),
            "community_reuse_count": int(existing.get("community_reuse_count") or 0),
        }
    )
    existing["community_quality_score"] = _community_score(
        float(existing.get("community_rating_avg") or 0),
        int(existing.get("community_rating_count") or 0),
        int(existing.get("community_reuse_count") or 0),
    )
    return _patch_render_job_metadata(render_job_id, existing)


def _get_fallback_community_work(work_id: str) -> dict[str, Any] | None:
    row = get_job(work_id)
    return _fallback_work_from_render_job(row, public_only=False) if row else None


def search_community_works(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Search published community works ordered by quality signals."""
    limit = max(1, min(int(limit or 5), 20))
    normalized = normalize_work_prompt(query)
    filters = [
        _community_public_status_filter(),
        "select=id,title,prompt,scene_name,code,video_url,render_job_id,tags,status,metadata,rating_avg,rating_count,reuse_count,quality_score,created_at,updated_at",
        "order=quality_score.desc,rating_avg.desc,reuse_count.desc,created_at.desc",
        f"limit={limit}",
    ]
    if normalized:
        pattern = quote(f"*{normalized}*", safe="")
        filters.append(f"or=(prompt_normalized.ilike.{pattern},prompt.ilike.{pattern},title.ilike.{pattern})")
    resp = _request_with_retries(
        "get",
        f"{_postgrest_url('community_works')}?{'&'.join(filters)}",
        headers={"apikey": _supabase_service_key(), "Authorization": f"Bearer {_supabase_service_key()}"},
    )
    if resp is None:
        return []
    if resp.status_code == 200:
        data = resp.json()
        return data if isinstance(data, list) else []
    if _is_missing_table(resp):
        return _search_community_works_from_render_jobs(query, limit)
    print(f"[supabase] search_community_works failed: {resp.status_code} {resp.text[:200]}")
    return []


def list_community_review_queue(status: str = "candidate", limit: int = 20) -> list[dict[str, Any]]:
    """List non-public works that need human review."""
    limit = max(1, min(int(limit or 20), 50))
    statuses = tuple(
        _normalize_community_status(item.strip())
        for item in str(status or "candidate").split(",")
        if item.strip()
    ) or ("candidate",)
    statuses = tuple(status for status in statuses if status not in PUBLIC_COMMUNITY_STATUSES)
    if not statuses:
        statuses = ("candidate",)
    status_filter = ",".join(statuses)
    filters = [
        f"status=in.({status_filter})",
        "select=id,title,prompt,scene_name,code,video_url,render_job_id,tags,status,metadata,rating_avg,rating_count,reuse_count,quality_score,created_at,updated_at",
        "order=created_at.asc",
        f"limit={limit}",
    ]
    resp = _request_with_retries(
        "get",
        f"{_postgrest_url('community_works')}?{'&'.join(filters)}",
        headers={"apikey": _supabase_service_key(), "Authorization": f"Bearer {_supabase_service_key()}"},
    )
    if resp is None:
        return []
    if resp.status_code == 200:
        data = resp.json()
        return data if isinstance(data, list) else []
    if _is_missing_table(resp):
        return _list_review_queue_from_render_jobs(statuses, limit)
    print(f"[supabase] list_community_review_queue failed: {resp.status_code} {resp.text[:200]}")
    return []


def insert_community_work(
    *,
    title: str,
    prompt: str,
    scene_name: str,
    code: str,
    video_url: str,
    render_job_id: str | None = None,
    author_label: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    status: str = "candidate",
) -> dict[str, Any] | None:
    status = _normalize_community_status(status)
    metadata = _merge_repository_metadata(metadata, status=status)
    payload = {
        "title": title.strip()[:120],
        "prompt": prompt.strip(),
        "prompt_normalized": normalize_work_prompt(prompt),
        "scene_name": scene_name.strip() or "GeneratedScene",
        "code": code,
        "video_url": video_url.strip(),
        "render_job_id": render_job_id,
        "author_label": (author_label or "匿名用户").strip()[:80],
        "tags": tags or [],
        "metadata": metadata,
        "status": status,
        "quality_score": _community_score(),
    }
    resp = _request_with_retries(
        "post",
        _postgrest_url("community_works"),
        headers=_headers_sr(),
        json=payload,
    )
    if resp is None:
        return None
    if resp.status_code in (200, 201):
        data = resp.json()
        return data[0] if isinstance(data, list) and data else data
    if _is_missing_table(resp):
        return _insert_community_work_in_render_job(
            title=title,
            prompt=prompt,
            render_job_id=render_job_id,
            author_label=author_label,
            tags=tags,
            metadata=metadata,
            status=status,
        )
    print(f"[supabase] insert_community_work failed: {resp.status_code} {resp.text[:200]}")
    return None


def _get_community_work(work_id: str) -> dict[str, Any] | None:
    resp = _request_with_retries(
        "get",
        f"{_postgrest_url('community_works')}?id=eq.{quote(work_id, safe='')}&limit=1",
        headers={"apikey": _supabase_service_key(), "Authorization": f"Bearer {_supabase_service_key()}"},
    )
    if resp is None or resp.status_code != 200:
        if _is_missing_table(resp):
            return _get_fallback_community_work(work_id)
        return None
    data = resp.json()
    return data[0] if isinstance(data, list) and data else None


def review_community_work(
    work_id: str,
    decision: str,
    *,
    reviewer_label: str | None = None,
    note: str | None = None,
) -> dict[str, Any] | None:
    """Move a candidate work through the repository review lifecycle."""
    work_id = str(work_id or "").strip()
    decision = str(decision or "").strip().lower()
    next_status = COMMUNITY_REVIEW_DECISIONS.get(decision)
    if not work_id or not next_status:
        return None
    work = _get_community_work(work_id)
    if not work:
        return None

    now = datetime.now(UTC).isoformat()
    metadata = _merge_repository_metadata(
        _community_metadata(work),
        status=next_status,
        decision=f"review_{decision}",
    )
    metadata.update(
        {
            "review_status": _review_status_for_lifecycle(next_status),
            "reviewed_at": now,
            "reviewer_label": (reviewer_label or "reviewer").strip()[:80],
            "review_note": (note or "").strip()[:500] or None,
        }
    )
    payload = {
        "status": next_status,
        "metadata": metadata,
        "updated_at": now,
    }

    if work.get("render_job_id") == work_id and work.get("id") == work_id:
        row = get_job(work_id)
        if not row:
            return None
        existing = _community_metadata(row)
        existing.update(
            {
                "community_status": next_status,
                "community_review_stage": metadata.get("review_stage"),
                "community_review_status": metadata.get("review_status"),
                "community_repository_decision": metadata.get("repository_decision"),
                "community_reviewer_label": metadata.get("reviewer_label"),
                "community_review_note": metadata.get("review_note"),
                "community_reviewed_at": metadata.get("reviewed_at"),
                "community_updated_at": now,
            }
        )
        return _patch_render_job_metadata(work_id, existing)

    resp = _request_with_retries(
        "patch",
        f"{_postgrest_url('community_works')}?id=eq.{quote(work_id, safe='')}",
        headers=_headers_sr(),
        json=payload,
    )
    if resp is None or resp.status_code not in (200, 204):
        if resp is not None:
            print(f"[supabase] review_community_work failed: {resp.status_code} {resp.text[:200]}")
        return None

    event_type = "promote" if next_status in PUBLIC_COMMUNITY_STATUSES else "demote"
    _request_with_retries(
        "post",
        _postgrest_url("community_work_events"),
        headers=_headers_sr(),
        json={
            "work_id": work_id,
            "event_type": event_type,
            "query": None,
            "metadata": {
                "decision": decision,
                "next_status": next_status,
                "reviewer_label": metadata.get("reviewer_label"),
                "note": metadata.get("review_note"),
            },
        },
    )
    data = resp.json() if resp.status_code == 200 else []
    return data[0] if isinstance(data, list) and data else {"id": work_id, **payload}


def _refresh_community_work_score(work_id: str) -> dict[str, Any] | None:
    ratings_resp = _request_with_retries(
        "get",
        f"{_postgrest_url('community_work_ratings')}?work_id=eq.{quote(work_id, safe='')}&select=rating",
        headers={"apikey": _supabase_service_key(), "Authorization": f"Bearer {_supabase_service_key()}"},
    )
    if ratings_resp is None or ratings_resp.status_code != 200:
        return None
    ratings = ratings_resp.json()
    rating_values = [
        float(row.get("rating", 0))
        for row in ratings
        if isinstance(row, dict) and row.get("rating") is not None
    ]
    rating_count = len(rating_values)
    rating_avg = round(sum(rating_values) / rating_count, 2) if rating_count else 0.0
    work = _get_community_work(work_id) or {}
    reuse_count = int(work.get("reuse_count") or 0)
    current_status = _normalize_community_status(work.get("status"), default="published")
    next_status = _status_after_quality_signals(current_status, rating_avg, rating_count, reuse_count)
    metadata = _merge_repository_metadata(
        _community_metadata(work),
        status=next_status,
        decision=("quality_featured" if next_status == "featured" else "low_score_quarantine" if next_status == "quarantine" else None),
    )
    payload = {
        "rating_avg": rating_avg,
        "rating_count": rating_count,
        "quality_score": _community_score(rating_avg, rating_count, reuse_count),
        "status": next_status,
        "metadata": metadata,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    resp = _request_with_retries(
        "patch",
        f"{_postgrest_url('community_works')}?id=eq.{quote(work_id, safe='')}",
        headers=_headers_sr(),
        json=payload,
    )
    if resp is None:
        return None
    if resp.status_code in (200, 204):
        data = resp.json() if resp.status_code == 200 else []
        return data[0] if isinstance(data, list) and data else {"id": work_id, **payload}
    return None


def rate_community_work(
    work_id: str,
    rating: int,
    rater_key: str | None = None,
    comment: str | None = None,
) -> dict[str, Any] | None:
    rating = max(1, min(int(rating), 5))
    payload = {
        "work_id": work_id,
        "rating": rating,
        "rater_key": (rater_key or "anonymous").strip()[:120],
        "comment": (comment or "").strip()[:500] or None,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    url = f"{_postgrest_url('community_work_ratings')}?on_conflict=work_id,rater_key"
    resp = _request_with_retries(
        "post",
        url,
        headers={**_headers_sr(), "Prefer": "resolution=merge-duplicates,return=representation"},
        json=payload,
    )
    if resp is None or resp.status_code not in (200, 201):
        if _is_missing_table(resp):
            work = _get_fallback_community_work(work_id)
            if not work:
                return None
            row = get_job(work_id)
            if not row:
                return None
            metadata = _community_metadata(row)
            ratings = metadata.get("community_ratings") if isinstance(metadata.get("community_ratings"), dict) else {}
            rater = (rater_key or "anonymous").strip()[:120]
            ratings[rater] = {
                "rating": rating,
                "comment": (comment or "").strip()[:500] or None,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            values = [float(item.get("rating", 0)) for item in ratings.values() if isinstance(item, dict)]
            rating_count = len(values)
            rating_avg = round(sum(values) / rating_count, 2) if rating_count else 0.0
            metadata["community_ratings"] = ratings
            metadata["community_rating_count"] = rating_count
            metadata["community_rating_avg"] = rating_avg
            metadata["community_quality_score"] = _community_score(
                rating_avg,
                rating_count,
                int(metadata.get("community_reuse_count") or 0),
            )
            metadata["community_updated_at"] = datetime.now(UTC).isoformat()
            return _patch_render_job_metadata(work_id, metadata)
        if resp is not None:
            print(f"[supabase] rate_community_work failed: {resp.status_code} {resp.text[:200]}")
        return None
    return _refresh_community_work_score(work_id)


def record_community_reuse(work_id: str, query: str | None = None) -> dict[str, Any] | None:
    work = _get_community_work(work_id)
    if not work:
        return None
    if work.get("render_job_id") == work_id and work.get("id") == work_id:
        row = get_job(work_id)
        if row:
            metadata = _community_metadata(row)
            reuse_count = int(metadata.get("community_reuse_count") or 0) + 1
            metadata["community_reuse_count"] = reuse_count
            metadata["community_quality_score"] = _community_score(
                float(metadata.get("community_rating_avg") or 0),
                int(metadata.get("community_rating_count") or 0),
                reuse_count,
            )
            metadata["community_last_reuse_query"] = (query or "").strip()[:1000] or None
            metadata["community_updated_at"] = datetime.now(UTC).isoformat()
            patched = _patch_render_job_metadata(work_id, metadata)
            if patched is not None:
                return patched
    reuse_count = int(work.get("reuse_count") or 0) + 1
    rating_avg = float(work.get("rating_avg") or 0)
    rating_count = int(work.get("rating_count") or 0)
    current_status = _normalize_community_status(work.get("status"), default="published")
    next_status = _status_after_quality_signals(current_status, rating_avg, rating_count, reuse_count)
    metadata = _merge_repository_metadata(
        _community_metadata(work),
        status=next_status,
        decision=("quality_featured" if next_status == "featured" else None),
    )
    payload = {
        "reuse_count": reuse_count,
        "quality_score": _community_score(rating_avg, rating_count, reuse_count),
        "status": next_status,
        "metadata": metadata,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    resp = _request_with_retries(
        "patch",
        f"{_postgrest_url('community_works')}?id=eq.{quote(work_id, safe='')}",
        headers=_headers_sr(),
        json=payload,
    )
    if resp is None or resp.status_code not in (200, 204):
        return None
    event_payload = {
        "work_id": work_id,
        "event_type": "reuse",
        "query": (query or "").strip()[:1000] or None,
        "metadata": {},
    }
    _request_with_retries(
        "post",
        _postgrest_url("community_work_events"),
        headers=_headers_sr(),
        json=event_payload,
    )
    data = resp.json() if resp.status_code == 200 else []
    return data[0] if isinstance(data, list) and data else {"id": work_id, **payload}


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

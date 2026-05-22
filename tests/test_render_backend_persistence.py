from __future__ import annotations

import importlib
import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

RENDER_BACKEND_DIR = Path(__file__).resolve().parents[1] / "render_backend"
if str(RENDER_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(RENDER_BACKEND_DIR))

HAS_BACKEND_DEPS = all(importlib.util.find_spec(name) for name in ("flask", "flask_cors"))
requires_backend = pytest.mark.skipif(
    not HAS_BACKEND_DEPS,
    reason="render backend tests require backend Flask dependencies",
)

supabase_client = importlib.import_module("supabase_client")
backend = importlib.import_module("app") if HAS_BACKEND_DEPS else None


def _row(
    job_id: str,
    status: str = "pending",
    updated_at: str | None = None,
    video_path: str | None = None,
    error_message: str | None = None,
) -> dict[str, str | None]:
    now = datetime.now(UTC).isoformat()
    return {
        "job_id": job_id,
        "status": status,
        "created_at": now,
        "updated_at": updated_at or now,
        "code": "from manim import *",
        "scene_name": "GeneratedScene",
        "video_path": video_path,
        "error_message": error_message,
        "stderr": None,
    }


class FakePopen:
    returncode = 0
    pid = 12345

    def communicate(self, timeout=None):
        return "", ""


@pytest.fixture(autouse=True)
def clear_backend_state(monkeypatch):
    if backend is None:
        yield
        return
    backend._jobs.clear()
    backend.app.config["_PERSISTENCE_INITIALIZED"] = False
    backend._orphan_reaper_started = False
    monkeypatch.setattr(backend, "_use_supabase", lambda: False)
    yield
    backend._jobs.clear()
    backend.app.config["_PERSISTENCE_INITIALIZED"] = False
    backend._orphan_reaper_started = False


@requires_backend
def test_register_job_requires_supabase_insert_before_memory_cache(monkeypatch):
    monkeypatch.setattr(backend, "_use_supabase", lambda: True)
    monkeypatch.setattr(backend, "supa_insert_job", lambda **_: None)

    with pytest.raises(RuntimeError, match="persist job"):
        backend._register_job("code", "GeneratedScene")

    assert backend._jobs == {}


@requires_backend
def test_get_job_reads_supabase_first_and_refreshes_memory_cache(monkeypatch):
    monkeypatch.setattr(backend, "_use_supabase", lambda: True)
    monkeypatch.setattr(
        backend,
        "supa_get_job",
        lambda job_id: _row(job_id, status="done", video_path="https://example.supabase.co/video.mp4"),
    )

    job = backend._get_job("job-1")

    assert job is not None
    assert job.status == backend.JobStatus.DONE
    assert backend._jobs["job-1"].video_path == "https://example.supabase.co/video.mp4"


@requires_backend
def test_recover_jobs_from_supabase_restores_pending_and_running_cache(monkeypatch):
    rows = [_row("pending-job"), _row("running-job", status="running")]
    monkeypatch.setattr(backend, "_use_supabase", lambda: True)
    monkeypatch.setattr(backend, "supa_list_jobs_by_status", lambda statuses: rows)

    backend._recover_jobs_from_supabase()

    assert set(backend._jobs) == {"pending-job", "running-job"}
    assert backend._jobs["running-job"].status == backend.JobStatus.RUNNING


@requires_backend
def test_reap_orphan_jobs_marks_stale_running_jobs_failed(monkeypatch):
    stale_time = (datetime.now(UTC) - timedelta(minutes=11)).isoformat()
    fresh_time = (datetime.now(UTC) - timedelta(minutes=2)).isoformat()
    updates: list[dict[str, str | None]] = []
    backend._jobs["stale"] = backend.RenderJob(
        job_id="stale",
        status=backend.JobStatus.RUNNING,
        created_at=stale_time,
        updated_at=stale_time,
        code="code",
        scene_name="GeneratedScene",
    )

    monkeypatch.setattr(backend, "_use_supabase", lambda: True)
    monkeypatch.setattr(
        backend,
        "supa_list_jobs_by_status",
        lambda statuses: [
            _row("stale", status="running", updated_at=stale_time),
            _row("fresh", status="running", updated_at=fresh_time),
        ],
    )
    monkeypatch.setattr(backend, "supa_update_job", lambda **kwargs: updates.append(kwargs) or _row("stale", status="failed"))

    backend._reap_orphan_jobs()

    assert [update["job_id"] for update in updates] == ["stale"]
    assert updates[0]["status"] == "failed"
    assert "Render instance restarted unexpectedly" in str(updates[0]["error_message"])
    assert backend._jobs["stale"].status == backend.JobStatus.FAILED


@requires_backend
def test_reap_orphan_jobs_also_fails_stale_pending_jobs(monkeypatch):
    stale_time = (datetime.now(UTC) - timedelta(minutes=11)).isoformat()
    updates: list[dict[str, str | None]] = []
    backend._jobs["pending-stale"] = backend.RenderJob(
        job_id="pending-stale",
        status=backend.JobStatus.PENDING,
        created_at=stale_time,
        updated_at=stale_time,
        code="code",
        scene_name="GeneratedScene",
    )

    monkeypatch.setattr(backend, "_use_supabase", lambda: True)
    monkeypatch.setattr(
        backend,
        "supa_list_jobs_by_status",
        lambda statuses: [_row("pending-stale", status="pending", updated_at=stale_time)],
    )
    monkeypatch.setattr(backend, "supa_update_job", lambda **kwargs: updates.append(kwargs) or _row("pending-stale", status="failed"))

    backend._reap_orphan_jobs()

    assert updates[0]["job_id"] == "pending-stale"
    assert updates[0]["expected_status"] == "pending"
    assert backend._jobs["pending-stale"].status == backend.JobStatus.FAILED


@requires_backend
def test_done_update_requires_pending_or_running_status_to_avoid_resurrecting_orphans(monkeypatch):
    calls: list[dict[str, str | None]] = []
    backend._jobs["job-1"] = backend.RenderJob(
        job_id="job-1",
        status=backend.JobStatus.FAILED,
        created_at=datetime.now(UTC).isoformat(),
        updated_at=datetime.now(UTC).isoformat(),
        code="code",
        scene_name="GeneratedScene",
        error_message=backend.ORPHAN_JOB_MESSAGE,
    )
    monkeypatch.setattr(backend, "_use_supabase", lambda: True)
    monkeypatch.setattr(backend, "supa_update_job", lambda **kwargs: calls.append(kwargs) or None)

    backend._update_job(
        "job-1",
        status=backend.JobStatus.DONE,
        video_path="https://example.supabase.co/video.mp4",
    )

    assert calls[0]["expected_status"] == ["pending", "running"]
    assert backend._jobs["job-1"].status == backend.JobStatus.FAILED


@requires_backend
def test_get_job_does_not_fallback_to_memory_on_supabase_miss(monkeypatch):
    backend._jobs["stale"] = backend.RenderJob(
        job_id="stale",
        status=backend.JobStatus.DONE,
        created_at=datetime.now(UTC).isoformat(),
        updated_at=datetime.now(UTC).isoformat(),
        code="code",
        scene_name="GeneratedScene",
    )
    monkeypatch.setattr(backend, "_use_supabase", lambda: True)
    monkeypatch.setattr(backend, "supa_get_job", lambda job_id: None)

    assert backend._get_job("stale") is None


@requires_backend
def test_get_job_falls_back_to_memory_when_supabase_read_is_unavailable(monkeypatch):
    backend._jobs["cached"] = backend.RenderJob(
        job_id="cached",
        status=backend.JobStatus.RUNNING,
        created_at=datetime.now(UTC).isoformat(),
        updated_at=datetime.now(UTC).isoformat(),
        code="code",
        scene_name="GeneratedScene",
    )

    def fail_read(job_id):
        raise supabase_client.SupabaseReadUnavailable("network down")

    monkeypatch.setattr(backend, "_use_supabase", lambda: True)
    monkeypatch.setattr(backend, "supa_get_job", fail_read)

    assert backend._get_job("cached").status == backend.JobStatus.RUNNING


@requires_backend
def test_download_completed_supabase_job_returns_storage_url(monkeypatch):
    storage_url = "https://example.supabase.co/storage/v1/object/public/manim-videos/job-1/scene.mp4"
    monkeypatch.setattr(backend, "_use_supabase", lambda: True)
    monkeypatch.setattr(
        backend,
        "supa_get_job",
        lambda job_id: _row(job_id, status="done", video_path=storage_url),
    )
    monkeypatch.setattr(backend, "initialize_app", lambda: None)
    backend.app.config["_PERSISTENCE_INITIALIZED"] = True

    client = backend.app.test_client()
    response = client.get("/download/job-1", headers={"X-API-Key": backend.API_KEY})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["video_url"] == storage_url
    assert "render_backend/outputs" not in payload["video_url"]


@requires_backend
def test_status_completed_supabase_job_exposes_playable_video_url(monkeypatch):
    storage_url = "https://example.supabase.co/storage/v1/object/public/manim-videos/job-1/scene.mp4"
    monkeypatch.setattr(backend, "_use_supabase", lambda: True)
    monkeypatch.setattr(
        backend,
        "supa_get_job",
        lambda job_id: _row(job_id, status="done", video_path=storage_url),
    )
    monkeypatch.setattr(backend, "initialize_app", lambda: None)
    backend.app.config["_PERSISTENCE_INITIALIZED"] = True

    client = backend.app.test_client()
    response = client.get("/status/job-1", headers={"X-API-Key": backend.API_KEY})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "done"
    assert payload["video_url"] == storage_url
    assert payload["download_url"] == "/download/job-1"


@requires_backend
def test_supabase_upload_failure_makes_render_fail_without_local_path(monkeypatch, tmp_path):
    source_video = tmp_path / "GeneratedScene.mp4"
    source_video.write_bytes(b"mp4")
    monkeypatch.setattr(backend, "_use_supabase", lambda: True)
    monkeypatch.setattr(backend, "_update_job", lambda *_, **__: None)
    monkeypatch.setattr(backend, "_find_rendered_video", lambda *_: source_video)
    monkeypatch.setattr(backend, "supa_upload_video", lambda *_: None)
    monkeypatch.setattr(
        backend.subprocess,
        "Popen",
        lambda *_, **__: FakePopen(),
    )

    result = backend._run_manim_render("code", "GeneratedScene", job_id="job-1")

    assert result["success"] is False
    assert result["video_path"] is None
    assert "persistent storage" in result["error"]


@requires_backend
def test_supabase_upload_success_returns_storage_url_as_video_path(monkeypatch, tmp_path):
    source_video = tmp_path / "GeneratedScene.mp4"
    source_video.write_bytes(b"mp4")
    storage_url = "https://example.supabase.co/storage/v1/object/public/manim-videos/job-1/GeneratedScene.mp4"
    monkeypatch.setattr(backend, "_use_supabase", lambda: True)
    monkeypatch.setattr(backend, "_update_job", lambda *_, **__: None)
    monkeypatch.setattr(backend, "_find_rendered_video", lambda *_: source_video)
    monkeypatch.setattr(backend, "supa_upload_video", lambda *_: storage_url)
    monkeypatch.setattr(backend, "supa_insert_log", lambda **_: None)
    monkeypatch.setattr(
        backend.subprocess,
        "Popen",
        lambda *_, **__: FakePopen(),
    )

    result = backend._run_manim_render("code", "GeneratedScene", job_id="job-1")

    assert result["success"] is True
    assert result["video_path"] == storage_url
    assert result["video_url"] == storage_url


@requires_backend
def test_memory_only_mode_keeps_existing_register_and_status_flow():
    job_id = backend._register_job("code", "GeneratedScene")

    backend._update_job(job_id, status=backend.JobStatus.DONE, video_path="/tmp/video.mp4")
    job = backend._get_job(job_id)

    assert job is not None
    assert job.status == backend.JobStatus.DONE
    assert job.video_path == "/tmp/video.mp4"


def test_supabase_list_jobs_by_status_uses_status_filter(monkeypatch):
    captured: dict[str, str] = {}

    def fake_request(method, url, headers, timeout=None):
        assert method == "get"
        captured["url"] = url
        return SimpleNamespace(status_code=200, json=lambda: [{"job_id": "job-1"}])

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-key")
    monkeypatch.setattr(supabase_client.requests, "request", fake_request)

    rows = supabase_client.list_jobs_by_status(["pending", "running"])

    assert rows == [{"job_id": "job-1"}]
    assert "status=in.(pending,running)" in captured["url"]


def test_supabase_is_not_configured_when_url_is_empty(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-key")

    assert supabase_client.is_configured() is False


def test_supabase_requests_retry_transient_failures(monkeypatch):
    calls = 0

    def fake_request(method, url, timeout=None, **kwargs):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise supabase_client.requests.RequestException("temporary outage")
        return SimpleNamespace(status_code=200, json=lambda: [{"job_id": "job-1"}])

    monkeypatch.setattr(supabase_client.requests, "request", fake_request)
    monkeypatch.setattr(supabase_client.time, "sleep", lambda *_: None)

    response = supabase_client._request_with_retries("get", "https://example.test")

    assert response is not None
    assert calls == 3


def test_supabase_upload_video_returns_none_on_network_error(monkeypatch, tmp_path):
    video = tmp_path / "scene.mp4"
    video.write_bytes(b"mp4")

    def fail_upload(*args, **kwargs):
        raise supabase_client.requests.RequestException("network down")

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-key")
    monkeypatch.setattr(supabase_client.requests, "post", fail_upload)

    assert supabase_client.upload_video("job-1", video) is None


def test_supabase_get_job_raises_only_when_read_unavailable(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-key")

    monkeypatch.setattr(
        supabase_client,
        "_request_with_retries",
        lambda *_, **__: SimpleNamespace(status_code=200, json=lambda: []),
    )
    assert supabase_client.get_job("missing") is None

    monkeypatch.setattr(supabase_client, "_request_with_retries", lambda *_, **__: None)
    with pytest.raises(supabase_client.SupabaseReadUnavailable):
        supabase_client.get_job("maybe-present")


def test_supabase_update_job_can_require_expected_current_status(monkeypatch):
    captured: dict[str, str] = {}

    def fake_request(method, url, timeout=None, **kwargs):
        captured["url"] = url
        return SimpleNamespace(status_code=200, json=lambda: [])

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-key")
    monkeypatch.setattr(supabase_client.requests, "request", fake_request)

    result = supabase_client.update_job("job-1", status="done", expected_status="running")

    assert result is None
    assert "status=eq.running" in captured["url"]


def test_supabase_update_job_can_require_any_expected_current_status(monkeypatch):
    captured: dict[str, str] = {}

    def fake_request(method, url, timeout=None, **kwargs):
        captured["url"] = url
        return SimpleNamespace(status_code=200, json=lambda: [])

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-key")
    monkeypatch.setattr(supabase_client.requests, "request", fake_request)

    result = supabase_client.update_job(
        "job-1",
        status="done",
        expected_status=["pending", "running"],
    )

    assert result is None
    assert "status=in.(pending,running)" in captured["url"]

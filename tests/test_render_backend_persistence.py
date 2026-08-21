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
cloud_run_executor = importlib.import_module("cloud_run_executor")
backend = importlib.import_module("app") if HAS_BACKEND_DEPS else None
cloud_run_worker = importlib.import_module("cloud_run_worker") if HAS_BACKEND_DEPS else None


def _row(
    job_id: str,
    status: str = "pending",
    updated_at: str | None = None,
    video_path: str | None = None,
    error_message: str | None = None,
    metadata: dict | None = None,
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
        "metadata": metadata or {},
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
    if not (backend.API_KEY or "").strip():
        monkeypatch.setattr(backend, "API_KEY", "test-render-key")
    yield
    backend._jobs.clear()
    backend.app.config["_PERSISTENCE_INITIALIZED"] = False
    backend._orphan_reaper_started = False


@requires_backend
def test_font_health_reports_noto_cjk_match(monkeypatch):
    monkeypatch.setattr(
        backend.subprocess,
        "run",
        lambda *_, **__: SimpleNamespace(
            returncode=0,
            stdout='NotoSansCJK-Regular.ttc: "Noto Sans CJK SC" "Regular"\n',
            stderr="",
        ),
    )

    payload = backend._font_health()

    assert payload["configured"] == "Noto Sans CJK SC"
    assert payload["ok"] is True
    assert "NotoSansCJK" in payload["matched"]


@requires_backend
def test_health_exposes_safe_render_font_diagnostics(monkeypatch):
    monkeypatch.setattr(backend, "_use_supabase", lambda: False)
    monkeypatch.setattr(
        backend,
        "_font_health",
        lambda: {"configured": "Noto Sans CJK SC", "matched": "NotoSansCJK-Regular.ttc", "ok": True},
    )

    response = backend.app.test_client().get("/health")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["render"]["quality"] == backend.MANIM_RENDER_QUALITY
    assert payload["render"]["cjk_font"]["ok"] is True
    assert "api" not in str(payload).lower()


@requires_backend
def test_health_exposes_cloud_run_executor_diagnostics_without_secrets(monkeypatch):
    monkeypatch.setattr(backend, "_use_supabase", lambda: False)
    monkeypatch.setattr(
        backend,
        "cloud_run_health_payload",
        lambda: {
            "configured": True,
            "project": "aegis-project",
            "region": "asia-east1",
            "job_name": "aegis-manim-render",
            "credentials_configured": True,
        },
    )
    monkeypatch.setattr(backend, "MANIM_EXECUTOR", "cloud_run")

    response = backend.app.test_client().get("/health")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["render"]["executor"]["selected"] == "cloud_run"
    assert payload["render"]["executor"]["cloud_run"]["configured"] is True
    assert "token" not in str(payload).lower()
    assert "service_key" not in str(payload).lower()


def test_root_render_dockerfile_installs_cjk_fonts():
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"
    content = dockerfile.read_text()

    assert "fontconfig" in content
    assert "fonts-noto-cjk" in content
    assert "fc-cache -f" in content
    assert 'MANIM_CJK_FONT="Noto Sans CJK SC"' in content


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
def test_recover_jobs_from_supabase_restarts_preexisting_jobs(monkeypatch):
    rows = [
        _row("pending-job", metadata={"render_mode": "auto"}),
        _row("running-job", status="running", metadata={"render_mode": "segmented"}),
    ]
    restarted: list[tuple[str, str]] = []
    updates: list[dict[str, object]] = []
    monkeypatch.setattr(backend, "_use_supabase", lambda: True)
    monkeypatch.setattr(backend, "supa_list_jobs_by_status", lambda statuses: rows)
    monkeypatch.setattr(backend, "supa_update_job", lambda **kwargs: updates.append(kwargs) or _row(str(kwargs["job_id"]), status="failed"))
    monkeypatch.setattr(
        backend,
        "_start_render_job_thread",
        lambda job_id, code, scene_name, render_mode="auto": restarted.append((job_id, render_mode)) or True,
    )

    backend._recover_jobs_from_supabase()

    assert set(backend._jobs) == {"pending-job", "running-job"}
    assert backend._jobs["pending-job"].status == backend.JobStatus.PENDING
    assert backend._jobs["running-job"].status == backend.JobStatus.PENDING
    assert backend._jobs["running-job"].error_message is None
    assert backend._jobs["running-job"].metadata["recovered_after_restart"] is True
    assert restarted == [("pending-job", "auto"), ("running-job", "segmented")]
    assert [update["job_id"] for update in updates] == ["pending-job", "running-job"]
    assert all(update["status"] == "pending" for update in updates)


@requires_backend
def test_recover_jobs_from_supabase_fails_after_recovery_limit(monkeypatch):
    rows = [
        _row(
            "looping-job",
            status="running",
            metadata={"render_mode": "segmented", "recovery_restart_attempts": backend.MAX_RECOVERY_RESTARTS},
        ),
    ]
    restarted: list[tuple[str, str]] = []
    updates: list[dict[str, object]] = []
    monkeypatch.setattr(backend, "_use_supabase", lambda: True)
    monkeypatch.setattr(backend, "supa_list_jobs_by_status", lambda statuses: rows)
    monkeypatch.setattr(backend, "supa_update_job", lambda **kwargs: updates.append(kwargs) or _row(str(kwargs["job_id"]), status="failed"))
    monkeypatch.setattr(
        backend,
        "_start_render_job_thread",
        lambda job_id, code, scene_name, render_mode="auto": restarted.append((job_id, render_mode)) or True,
    )

    backend._recover_jobs_from_supabase()

    assert backend._jobs["looping-job"].status == backend.JobStatus.FAILED
    assert "Render instance restarted unexpectedly" in str(backend._jobs["looping-job"].error_message)
    assert restarted == []
    assert updates[0]["job_id"] == "looping-job"
    assert updates[0]["status"] == "failed"


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
def test_plan_render_segments_splits_long_scene_by_render_events():
    code = """
from manim import *
class GeneratedScene(Scene):
    def construct(self):
        self.play(Write(Text("1")))
        self.wait(0.1)
        self.play(Write(Text("2")))
        self.wait(0.1)
        self.play(Write(Text("3")))
"""

    segments = backend._plan_render_segments(code, mode="segmented", segment_size=2)

    assert [(segment.index, segment.start, segment.end) for segment in segments] == [
        (1, 0, 1),
        (2, 2, 3),
        (3, 4, 4),
    ]


@requires_backend
def test_auto_render_mode_keeps_short_scene_single():
    code = """
from manim import *
class GeneratedScene(Scene):
    def construct(self):
        self.play(Write(Text("short")))
"""

    assert backend._plan_render_segments(code, mode="auto", threshold=8) == []


@requires_backend
def test_build_manim_command_adds_animation_range_for_segment(tmp_path):
    scene_file = tmp_path / "scene.py"
    segment = backend.RenderSegment(index=2, start=6, end=11)

    cmd = backend._build_manim_command(scene_file, "GeneratedScene", tmp_path, segment=segment)

    assert "-ql" in cmd
    assert "-n" in cmd
    assert cmd[cmd.index("-n") + 1] == "6,11"


@requires_backend
def test_write_concat_manifest_preserves_segment_order(tmp_path):
    segment_paths = [tmp_path / "part one.mp4", tmp_path / "part_two.mp4"]
    manifest = tmp_path / "segments.txt"

    backend._write_concat_manifest(segment_paths, manifest)

    assert manifest.read_text(encoding="utf-8").splitlines() == [
        f"file '{segment_paths[0].resolve()}'",
        f"file '{segment_paths[1].resolve()}'",
    ]


@requires_backend
def test_segmented_render_concats_then_uploads_only_final_video(monkeypatch, tmp_path):
    code = """
from manim import *
class GeneratedScene(Scene):
    def construct(self):
        self.play(Write(Text("1")))
        self.play(Write(Text("2")))
        self.play(Write(Text("3")))
        self.play(Write(Text("4")))
        self.play(Write(Text("5")))
        self.play(Write(Text("6")))
        self.play(Write(Text("7")))
"""
    segment_calls: list[tuple[int, int]] = []
    uploaded: list[Path] = []

    monkeypatch.setattr(backend, "TEMP_DIR", tmp_path / "temp")
    monkeypatch.setattr(backend, "OUTPUT_DIR", tmp_path / "outputs")
    backend.TEMP_DIR.mkdir(exist_ok=True)
    backend.OUTPUT_DIR.mkdir(exist_ok=True)
    monkeypatch.setattr(backend, "_use_supabase", lambda: True)
    monkeypatch.setattr(backend, "_update_job", lambda *_, **__: None)
    monkeypatch.setattr(backend, "supa_insert_log", lambda **_: None)

    def fake_single(scene_file, scene_name, workspace, timeout, segment=None):
        assert segment is not None
        segment_calls.append((segment.start, segment.end))
        video = workspace / f"rendered_segment_{segment.index}.mp4"
        video.write_bytes(b"segment")
        return {"success": True, "video_path": str(video), "stderr": ""}

    def fake_concat(segment_paths, output_path, workspace):
        assert [path.name for path in segment_paths] == [
            "segment_1.mp4",
            "segment_2.mp4",
        ]
        output_path.write_bytes(b"final")
        return {"success": True, "stderr": ""}

    def fake_upload(job_id, file_path):
        uploaded.append(Path(file_path))
        return "https://example.supabase.co/storage/v1/object/public/manim-videos/job-1/final.mp4"

    monkeypatch.setattr(backend, "_run_single_manim_render", fake_single)
    monkeypatch.setattr(backend, "_concat_segment_videos", fake_concat)
    monkeypatch.setattr(backend, "supa_upload_video", fake_upload)

    result = backend._run_manim_render(
        code,
        "GeneratedScene",
        job_id="job-1",
        render_mode="segmented",
    )

    assert result["success"] is True
    assert result["video_path"].startswith("https://example.supabase.co/")
    assert segment_calls == [(0, 5), (6, 6)]
    assert uploaded == [uploaded[0]]
    assert uploaded[0].name == "GeneratedScene_segmented.mp4"


@requires_backend
def test_rendered_video_finder_accepts_scene_name_suffixes_and_ignores_partials(tmp_path):
    videos_dir = tmp_path / "videos" / "scene" / "480p15"
    partial_dir = videos_dir / "partial_movie_files" / "ParetoOptimalScene"
    partial_dir.mkdir(parents=True)
    partial_video = partial_dir / "ParetoOptimalScene_partial.mp4"
    partial_video.write_bytes(b"partial")
    final_video = videos_dir / "ParetoOptimalScene_range_0_4.mp4"
    final_video.write_bytes(b"final")

    assert backend._find_rendered_video(tmp_path, "ParetoOptimalScene") == final_video


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
def test_supabase_upload_retries_before_failing_render(monkeypatch, tmp_path):
    source_video = tmp_path / "GeneratedScene.mp4"
    source_video.write_bytes(b"mp4")
    calls: list[str] = []
    monkeypatch.setattr(backend, "_use_supabase", lambda: True)
    monkeypatch.setattr(backend, "_update_job", lambda *_, **__: None)
    monkeypatch.setattr(backend, "_find_rendered_video", lambda *_: source_video)
    monkeypatch.setattr(backend, "supa_insert_log", lambda **_: None)
    monkeypatch.setattr(backend, "SUPABASE_UPLOAD_RETRIES", 3)
    monkeypatch.setattr(backend, "SUPABASE_UPLOAD_RETRY_DELAY_SECONDS", 0)
    monkeypatch.setattr(
        backend,
        "supa_upload_video",
        lambda job_id, path: calls.append(job_id) or (
            "https://example.supabase.co/storage/v1/object/public/manim-videos/job-1/final.mp4"
            if len(calls) == 3
            else None
        ),
    )
    monkeypatch.setattr(
        backend.subprocess,
        "Popen",
        lambda *_, **__: FakePopen(),
    )

    result = backend._run_manim_render("code", "GeneratedScene", job_id="job-1")

    assert result["success"] is True
    assert result["video_url"] == "https://example.supabase.co/storage/v1/object/public/manim-videos/job-1/final.mp4"
    assert calls == ["job-1", "job-1", "job-1"]


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


def test_cloud_run_dispatch_uses_job_id_env_overrides_without_code_or_secrets(monkeypatch):
    captured: dict[str, object] = {}

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return SimpleNamespace(
            status_code=200,
            json=lambda: {"name": "projects/p/locations/asia-east1/executions/ex-1", "uid": "uid-1"},
        )

    monkeypatch.setenv("CLOUD_RUN_PROJECT", "p")
    monkeypatch.setenv("CLOUD_RUN_REGION", "asia-east1")
    monkeypatch.setenv("CLOUD_RUN_JOB_NAME", "aegis-manim-render")
    monkeypatch.setenv("CLOUD_RUN_ACCESS_TOKEN", "access-token")
    monkeypatch.setattr(cloud_run_executor.requests, "post", fake_post)

    execution = cloud_run_executor.dispatch_cloud_run_render_job(
        "job-1",
        "segmented",
        timeout_seconds=600,
    )

    assert execution.name.endswith("/ex-1")
    assert captured["url"] == (
        "https://run.googleapis.com/v2/projects/p/locations/asia-east1/jobs/"
        "aegis-manim-render:run"
    )
    payload = captured["json"]
    assert payload["overrides"]["timeout"] == "600s"
    env = payload["overrides"]["containerOverrides"][0]["env"]
    assert {"name": "AEGIS_RENDER_JOB_ID", "value": "job-1"} in env
    assert {"name": "AEGIS_RENDER_MODE", "value": "segmented"} in env
    assert "from manim import" not in str(payload)
    assert "access-token" not in str(payload)


@requires_backend
def test_render_async_dispatches_to_cloud_run_executor(monkeypatch):
    updates: list[dict[str, object]] = []
    monkeypatch.setattr(backend, "MANIM_EXECUTOR", "cloud_run")
    monkeypatch.setattr(backend, "_use_supabase", lambda: True)
    monkeypatch.setattr(backend, "initialize_app", lambda: None)
    backend.app.config["_PERSISTENCE_INITIALIZED"] = True
    monkeypatch.setattr(
        backend,
        "supa_insert_job",
        lambda **kwargs: _row(str(kwargs["job_id"]), metadata=kwargs.get("metadata")),
    )
    monkeypatch.setattr(backend, "supa_update_job", lambda **kwargs: updates.append(kwargs) or _row(str(kwargs["job_id"])))
    monkeypatch.setattr(backend, "_get_job", lambda job_id: backend._jobs.get(job_id))
    monkeypatch.setattr(
        backend,
        "dispatch_cloud_run_render_job",
        lambda job_id, render_mode, timeout_seconds=None: SimpleNamespace(
            name="projects/p/locations/asia-east1/executions/ex-1",
            uid="uid-1",
        ),
    )

    response = backend.app.test_client().post(
        "/render-async",
        headers={"X-API-Key": backend.API_KEY},
        json={
            "code": "from manim import *\nclass GeneratedScene(Scene):\n    def construct(self):\n        self.wait(1)\n",
            "scene_name": "GeneratedScene",
            "render_mode": "auto",
        },
    )

    assert response.status_code == 202
    payload = response.get_json()
    assert payload["executor"] == "cloud_run"
    assert payload["status_url"].startswith("/status/")
    assert any(update.get("status") == "running" for update in updates)
    final_metadata = updates[-1]["metadata"]
    assert final_metadata["executor"] == "cloud_run"
    assert final_metadata["stage"] == "cloud_run_dispatched"
    assert final_metadata["cloud_run_execution"].endswith("/ex-1")


@requires_backend
def test_cloud_run_worker_executes_persisted_job_by_id(monkeypatch):
    job = backend.RenderJob(
        job_id="job-1",
        status=backend.JobStatus.PENDING,
        created_at=datetime.now(UTC).isoformat(),
        updated_at=datetime.now(UTC).isoformat(),
        code="from manim import *",
        scene_name="GeneratedScene",
        metadata={"render_mode": "segmented"},
    )
    updates: list[dict[str, object]] = []
    executed: list[tuple[str, str, str, str]] = []
    final_status = {"status": backend.JobStatus.DONE}
    monkeypatch.setenv("AEGIS_RENDER_JOB_ID", "job-1")
    monkeypatch.setenv("AEGIS_RENDER_MODE", "segmented")
    monkeypatch.setattr(cloud_run_worker, "_get_job", lambda job_id: job if not executed else SimpleNamespace(status=final_status["status"]))
    monkeypatch.setattr(cloud_run_worker, "_update_job", lambda *args, **kwargs: updates.append({"args": args, **kwargs}))
    monkeypatch.setattr(
        cloud_run_worker,
        "_execute_render_job",
        lambda job_id, code, scene_name, render_mode="auto": executed.append((job_id, code, scene_name, render_mode)),
    )

    exit_code = cloud_run_worker.main()

    assert exit_code == 0
    assert executed == [("job-1", "from manim import *", "GeneratedScene", "segmented")]
    assert updates[0]["status"] == backend.JobStatus.RUNNING
    assert updates[0]["metadata"]["executor"] == "cloud_run"
    assert updates[0]["metadata"]["stage"] == "cloud_run_worker_started"


@requires_backend
def test_memory_only_mode_keeps_existing_register_and_status_flow():
    job_id = backend._register_job("code", "GeneratedScene")

    backend._update_job(job_id, status=backend.JobStatus.DONE, video_path="/tmp/video.mp4")
    job = backend._get_job(job_id)

    assert job is not None
    assert job.status == backend.JobStatus.DONE
    assert job.video_path == "/tmp/video.mp4"


@requires_backend
def test_community_search_route_returns_best_published_work(monkeypatch):
    monkeypatch.setattr(backend, "_use_supabase", lambda: True)
    monkeypatch.setattr(backend, "supa_list_jobs_by_status", lambda statuses: [])
    monkeypatch.setattr(
        backend,
        "supa_search_community_works",
        lambda query, limit=5: [
            {
                "id": "work-1",
                "title": "帕累托最优",
                "prompt": "可视化帕累托最优过程",
                "scene_name": "ParetoScene",
                "code": "from manim import *",
                "video_url": "https://example.supabase.co/storage/v1/object/public/manim-videos/job/video.mp4",
                "rating_avg": 4.8,
                "rating_count": 7,
                "reuse_count": 12,
                "quality_score": 0.91,
            }
        ],
    )

    response = backend.app.test_client().get(
        "/community/search?q=%E5%B8%95%E7%B4%AF%E6%89%98&limit=1",
        headers={"X-API-Key": backend.API_KEY},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["hit"] is True
    assert payload["items"][0]["workId"] == "work-1"
    assert "service" not in str(payload).lower()


@requires_backend
def test_community_publish_rejects_external_video_urls(monkeypatch):
    monkeypatch.setattr(backend, "_use_supabase", lambda: True)
    monkeypatch.setattr(backend, "supa_list_jobs_by_status", lambda statuses: [])
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(
        backend,
        "_get_job",
        lambda job_id: backend.RenderJob(
            job_id=job_id,
            status=backend.JobStatus.DONE,
            created_at=datetime.now(UTC).isoformat(),
            updated_at=datetime.now(UTC).isoformat(),
            code="from manim import *",
            scene_name="GeneratedScene",
            video_path="https://evil.example/video.mp4",
        ),
    )

    response = backend.app.test_client().post(
        "/community/works",
        headers={"X-API-Key": backend.API_KEY},
        json={
            "title": "外链视频",
            "prompt": "可视化税收楔子",
            "sceneName": "GeneratedScene",
            "code": "from manim import *",
            "videoUrl": "https://evil.example/video.mp4",
            "renderJobId": "job-1",
        },
    )

    assert response.status_code == 400
    assert "videoUrl" in response.get_json()["error"]


@requires_backend
def test_community_publish_rate_and_reuse_routes_call_supabase_helpers(monkeypatch):
    calls: dict[str, object] = {}
    monkeypatch.setattr(backend, "_use_supabase", lambda: True)
    monkeypatch.setattr(backend, "supa_list_jobs_by_status", lambda statuses: [])
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(
        backend,
        "_get_job",
        lambda job_id: backend.RenderJob(
            job_id=job_id,
            status=backend.JobStatus.DONE,
            created_at=datetime.now(UTC).isoformat(),
            updated_at=datetime.now(UTC).isoformat(),
            code="from manim import *\n# from persisted job",
            scene_name="PersistedScene",
            video_path="https://example.supabase.co/storage/v1/object/public/manim-videos/job/video.mp4",
        ),
    )

    def fake_insert(**kwargs):
        calls["insert"] = kwargs
        return {"id": "work-1", **kwargs}

    def fake_rate(work_id, rating, rater_key=None, comment=None):
        calls["rate"] = (work_id, rating, rater_key, comment)
        return {"id": work_id, "rating_avg": 5, "rating_count": 1, "quality_score": 0.7}

    def fake_reuse(work_id, query=None):
        calls["reuse"] = (work_id, query)
        return {"id": work_id, "reuse_count": 1, "quality_score": 0.8}

    monkeypatch.setattr(backend, "supa_insert_community_work", fake_insert)
    monkeypatch.setattr(backend, "supa_rate_community_work", fake_rate)
    monkeypatch.setattr(backend, "supa_record_community_reuse", fake_reuse)

    client = backend.app.test_client()
    publish = client.post(
        "/community/works",
        headers={"X-API-Key": backend.API_KEY},
        json={
            "title": "帕累托最优",
            "prompt": "可视化帕累托最优",
            "sceneName": "ParetoScene",
            "code": "from manim import *",
            "videoUrl": "https://example.supabase.co/storage/v1/object/public/manim-videos/job/video.mp4",
            "renderJobId": "job-1",
        },
    )
    rating = client.post(
        "/community/works/work-1/rating",
        headers={"X-API-Key": backend.API_KEY},
        json={"rating": 5, "raterKey": "anon-1", "comment": "清楚"},
    )
    reuse = client.post(
        "/community/works/work-1/reuse",
        headers={"X-API-Key": backend.API_KEY},
        json={"query": "帕累托"},
    )

    assert publish.status_code == 201
    assert publish.get_json()["work"]["workId"] == "work-1"
    assert calls["insert"]["scene_name"] == "PersistedScene"
    assert calls["insert"]["code"].endswith("# from persisted job")
    assert calls["insert"]["status"] == "candidate"
    assert calls["insert"]["metadata"]["review_stage"] == "candidate"
    assert calls["insert"]["metadata"]["repository_decision"] == "pending_review"
    assert rating.status_code == 200
    assert calls["rate"] == ("work-1", 5, "anon-1", "清楚")
    assert reuse.status_code == 200
    assert calls["reuse"] == ("work-1", "帕累托")


@requires_backend
def test_community_review_routes_require_token_and_update_lifecycle(monkeypatch):
    calls: dict[str, object] = {}
    monkeypatch.setattr(backend, "_use_supabase", lambda: True)
    monkeypatch.setattr(backend, "COMMUNITY_REVIEW_TOKEN", "review-token")
    monkeypatch.setattr(backend, "supa_list_jobs_by_status", lambda statuses: [])

    def fake_list(status="candidate", limit=20):
        calls["queue"] = (status, limit)
        return [
            {
                "id": "work-1",
                "title": "Slutsky 分解",
                "prompt": "用动画解释 Slutsky 和 Hicks 补偿",
                "scene_name": "CompensationScene",
                "code": "from manim import *",
                "video_url": "https://example.supabase.co/storage/v1/object/public/manim-videos/job/video.mp4",
                "status": "candidate",
                "metadata": {"review_stage": "candidate", "review_status": "pending"},
            }
        ]

    def fake_review(work_id, decision, reviewer_label=None, note=None):
        calls["review"] = (work_id, decision, reviewer_label, note)
        return {
            "id": work_id,
            "title": "Slutsky 分解",
            "prompt": "用动画解释 Slutsky 和 Hicks 补偿",
            "scene_name": "CompensationScene",
            "code": "from manim import *",
            "video_url": "https://example.supabase.co/storage/v1/object/public/manim-videos/job/video.mp4",
            "status": "featured",
            "metadata": {
                "review_stage": "featured",
                "review_status": "approved",
                "repository_decision": "review_feature",
            },
        }

    monkeypatch.setattr(backend, "supa_list_community_review_queue", fake_list)
    monkeypatch.setattr(backend, "supa_review_community_work", fake_review)

    client = backend.app.test_client()
    unauthorized = client.get("/community/review/queue", headers={"X-API-Key": backend.API_KEY})
    queue = client.get(
        "/community/review/queue?status=candidate&limit=5&reviewToken=review-token",
        headers={"X-API-Key": backend.API_KEY},
    )
    reviewed = client.post(
        "/community/works/work-1/review",
        headers={"X-API-Key": backend.API_KEY},
        json={
            "decision": "feature",
            "reviewToken": "review-token",
            "reviewerLabel": "teacher",
            "note": "经济学解释清楚",
        },
    )

    assert unauthorized.status_code == 401
    assert queue.status_code == 200
    assert queue.get_json()["items"][0]["reviewStage"] == "candidate"
    assert calls["queue"] == ("candidate", 5)
    assert reviewed.status_code == 200
    assert reviewed.get_json()["work"]["status"] == "featured"
    assert reviewed.get_json()["work"]["reviewStage"] == "featured"
    assert calls["review"] == ("work-1", "feature", "teacher", "经济学解释清楚")


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


def test_supabase_search_community_works_orders_by_quality(monkeypatch):
    captured: dict[str, str] = {}

    def fake_request(method, url, headers, timeout=None):
        assert method == "get"
        captured["url"] = url
        return SimpleNamespace(status_code=200, json=lambda: [{"id": "work-1"}])

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-key")
    monkeypatch.setattr(supabase_client.requests, "request", fake_request)

    rows = supabase_client.search_community_works("帕累托 最优", limit=3)

    assert rows == [{"id": "work-1"}]
    assert "community_works" in captured["url"]
    assert "status=in.(published,featured)" in captured["url"]
    assert "order=quality_score.desc" in captured["url"]
    assert "limit=3" in captured["url"]


def test_supabase_search_community_works_falls_back_to_render_job_metadata(monkeypatch):
    calls: list[tuple[str, str]] = []

    def fake_request(method, url, headers, timeout=None):
        calls.append((method, url))
        if "community_works" in url:
            return SimpleNamespace(
                status_code=404,
                text="Could not find the table 'public.community_works'",
            )
        return SimpleNamespace(
            status_code=200,
            json=lambda: [
                {
                    "job_id": "job-1",
                    "scene_name": "ParetoScene",
                    "code": "from manim import *",
                    "video_path": "https://example.supabase.co/storage/v1/object/public/manim-videos/job/video.mp4",
                    "metadata": {
                        "community_status": "published",
                        "community_title": "帕累托最优",
                        "community_prompt": "可视化帕累托最优过程",
                        "community_prompt_normalized": "可视化帕累托最优过程",
                        "community_rating_avg": 5,
                        "community_rating_count": 2,
                        "community_reuse_count": 3,
                        "community_quality_score": 0.9,
                    },
                    "created_at": "2026-05-23T00:00:00Z",
                    "updated_at": "2026-05-23T00:00:00Z",
                }
            ],
        )

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-key")
    monkeypatch.setattr(supabase_client.requests, "request", fake_request)

    rows = supabase_client.search_community_works("帕累托", limit=1)

    assert rows[0]["id"] == "job-1"
    assert rows[0]["render_job_id"] == "job-1"
    assert rows[0]["title"] == "帕累托最优"
    assert any("metadata-%3E%3Ecommunity_status=in.(published,featured)" in call[1] for call in calls)


def test_supabase_list_community_review_queue_filters_non_public_statuses(monkeypatch):
    captured: dict[str, str] = {}

    def fake_request(method, url, headers, timeout=None):
        assert method == "get"
        captured["url"] = url
        return SimpleNamespace(status_code=200, json=lambda: [{"id": "work-1", "status": "candidate"}])

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-key")
    monkeypatch.setattr(supabase_client.requests, "request", fake_request)

    rows = supabase_client.list_community_review_queue("candidate,published,quarantine", limit=9)

    assert rows == [{"id": "work-1", "status": "candidate"}]
    assert "community_works" in captured["url"]
    assert "status=in.(candidate,quarantine)" in captured["url"]
    assert "order=created_at.asc" in captured["url"]
    assert "limit=9" in captured["url"]


def test_supabase_insert_community_work_falls_back_to_render_job_metadata(monkeypatch):
    calls: list[tuple[str, str, dict]] = []
    stored_metadata: dict[str, object] = {}

    def fake_request(method, url, timeout=None, **kwargs):
        calls.append((method, url, kwargs))
        if method == "post" and "community_works" in url:
            return SimpleNamespace(
                status_code=404,
                text="Could not find the table 'public.community_works'",
            )
        if method == "get" and "render_jobs" in url:
            return SimpleNamespace(
                status_code=200,
                json=lambda: [
                    {
                        "job_id": "job-1",
                        "scene_name": "GeneratedScene",
                        "code": "from manim import *",
                        "video_path": "https://example.supabase.co/storage/v1/object/public/manim-videos/job/video.mp4",
                        "metadata": stored_metadata,
                        "created_at": "2026-05-23T00:00:00Z",
                        "updated_at": "2026-05-23T00:00:00Z",
                    }
                ],
            )
        if method == "patch" and "render_jobs" in url:
            stored_metadata.update(kwargs["json"]["metadata"])
            return SimpleNamespace(status_code=200, json=lambda: [{"job_id": "job-1"}])
        raise AssertionError(f"unexpected request {method} {url}")

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-key")
    monkeypatch.setattr(supabase_client.requests, "request", fake_request)

    row = supabase_client.insert_community_work(
        title="帕累托最优",
        prompt="可视化帕累托最优",
        scene_name="GeneratedScene",
        code="ignored",
        video_url="ignored",
        render_job_id="job-1",
        tags=["经济学"],
    )

    assert row is not None
    assert row["id"] == "job-1"
    assert row["prompt"] == "可视化帕累托最优"
    assert stored_metadata["community_status"] == "candidate"
    assert stored_metadata["community_review_stage"] == "candidate"
    assert stored_metadata["community_repository_decision"] == "pending_review"
    assert stored_metadata["community_tags"] == ["经济学"]
    assert any(call[0] == "patch" and "render_jobs" in call[1] for call in calls)


def test_supabase_review_community_work_promotes_and_records_event(monkeypatch):
    calls: list[tuple[str, str, dict]] = []

    def fake_request(method, url, timeout=None, **kwargs):
        calls.append((method, url, kwargs))
        if method == "get" and "community_works" in url:
            return SimpleNamespace(
                status_code=200,
                json=lambda: [
                    {
                        "id": "work-1",
                        "status": "candidate",
                        "metadata": {
                            "review_stage": "candidate",
                            "review_status": "pending",
                            "repository_decision": "pending_review",
                        },
                    }
                ],
            )
        if method == "patch" and "community_works" in url:
            return SimpleNamespace(
                status_code=200,
                json=lambda: [{"id": "work-1", "status": kwargs["json"]["status"], "metadata": kwargs["json"]["metadata"]}],
            )
        if method == "post" and "community_work_events" in url:
            return SimpleNamespace(status_code=201, json=lambda: [{"id": "event-1"}])
        raise AssertionError(f"unexpected request {method} {url}")

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-key")
    monkeypatch.setattr(supabase_client.requests, "request", fake_request)

    result = supabase_client.review_community_work(
        "work-1",
        "approve",
        reviewer_label="teacher",
        note="可入库",
    )

    assert result is not None
    assert result["status"] == "published"
    patch_payload = next(call[2]["json"] for call in calls if call[0] == "patch" and "community_works" in call[1])
    assert patch_payload["status"] == "published"
    assert patch_payload["metadata"]["review_stage"] == "public"
    assert patch_payload["metadata"]["review_status"] == "approved"
    assert patch_payload["metadata"]["repository_decision"] == "review_approve"
    assert patch_payload["metadata"]["reviewer_label"] == "teacher"
    event_payload = next(call[2]["json"] for call in calls if call[0] == "post" and "community_work_events" in call[1])
    assert event_payload["event_type"] == "promote"
    assert event_payload["metadata"]["next_status"] == "published"


def test_supabase_rate_community_work_upserts_and_refreshes_score(monkeypatch):
    calls: list[tuple[str, str, dict]] = []

    def fake_request(method, url, timeout=None, **kwargs):
        calls.append((method, url, kwargs))
        if method == "post":
            return SimpleNamespace(status_code=201, json=lambda: [{"id": "rating-1"}])
        if "community_work_ratings" in url:
            return SimpleNamespace(status_code=200, json=lambda: [{"rating": 5}, {"rating": 4}])
        if "community_works" in url and method == "get":
            return SimpleNamespace(
                status_code=200,
                json=lambda: [{"status": "published", "metadata": {}, "reuse_count": 3}],
            )
        if method == "patch":
            return SimpleNamespace(
                status_code=200,
                json=lambda: [{"id": "work-1", "rating_avg": 4.5, "status": kwargs["json"]["status"]}],
            )
        raise AssertionError(f"unexpected request {method} {url}")

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-key")
    monkeypatch.setattr(supabase_client.requests, "request", fake_request)

    result = supabase_client.rate_community_work("work-1", 5, rater_key="anon-1", comment="好")

    assert result["rating_avg"] == 4.5
    assert calls[0][0] == "post"
    assert "on_conflict=work_id,rater_key" in calls[0][1]
    assert calls[0][2]["headers"]["Prefer"] == "resolution=merge-duplicates,return=representation"
    assert any(call[0] == "patch" and "community_works" in call[1] for call in calls)
    patch_payload = next(call[2]["json"] for call in calls if call[0] == "patch" and "community_works" in call[1])
    assert patch_payload["status"] == "published"
    assert patch_payload["metadata"]["review_stage"] == "public"


def test_supabase_rate_community_work_moves_low_public_score_to_quarantine(monkeypatch):
    calls: list[tuple[str, str, dict]] = []

    def fake_request(method, url, timeout=None, **kwargs):
        calls.append((method, url, kwargs))
        if method == "post":
            return SimpleNamespace(status_code=201, json=lambda: [{"id": "rating-1"}])
        if "community_work_ratings" in url:
            return SimpleNamespace(
                status_code=200,
                json=lambda: [{"rating": 2}, {"rating": 3}, {"rating": 2}, {"rating": 3}, {"rating": 2}],
            )
        if "community_works" in url and method == "get":
            return SimpleNamespace(
                status_code=200,
                json=lambda: [{"status": "published", "metadata": {}, "reuse_count": 1}],
            )
        if method == "patch":
            return SimpleNamespace(
                status_code=200,
                json=lambda: [{"id": "work-1", "status": kwargs["json"]["status"]}],
            )
        raise AssertionError(f"unexpected request {method} {url}")

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-key")
    monkeypatch.setattr(supabase_client.requests, "request", fake_request)

    result = supabase_client.rate_community_work("work-1", 2, rater_key="anon-1")

    assert result["status"] == "quarantine"
    patch_payload = next(call[2]["json"] for call in calls if call[0] == "patch" and "community_works" in call[1])
    assert patch_payload["status"] == "quarantine"
    assert patch_payload["metadata"]["review_stage"] == "quarantine"
    assert patch_payload["metadata"]["repository_decision"] == "low_score_quarantine"


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

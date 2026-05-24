"""Cloud Run Job entrypoint for executing one persisted Aegis-Manim render."""

from __future__ import annotations

import os
import sys

from app import JobStatus, _execute_render_job, _get_job, _update_job


def main() -> int:
    job_id = os.environ.get("AEGIS_RENDER_JOB_ID", "").strip()
    render_mode = os.environ.get("AEGIS_RENDER_MODE", "auto").strip().lower() or "auto"
    if render_mode not in {"auto", "single", "segmented"}:
        render_mode = "auto"
    if not job_id:
        print("[cloud_run_worker] Missing AEGIS_RENDER_JOB_ID", file=sys.stderr)
        return 2

    job = _get_job(job_id)
    if job is None:
        print(f"[cloud_run_worker] Job {job_id[:8]} not found", file=sys.stderr)
        return 3
    if job.status == JobStatus.DONE:
        print(f"[cloud_run_worker] Job {job_id[:8]} already done")
        return 0
    if job.status == JobStatus.FAILED:
        print(f"[cloud_run_worker] Job {job_id[:8]} already failed")
        return 0

    metadata = dict(job.metadata or {})
    metadata.update({"executor": "cloud_run", "stage": "cloud_run_worker_started"})
    _update_job(job_id, status=JobStatus.RUNNING, metadata=metadata)
    _execute_render_job(job_id, job.code, job.scene_name, render_mode=render_mode)

    final_job = _get_job(job_id)
    if final_job is None:
        print(f"[cloud_run_worker] Job {job_id[:8]} disappeared after render", file=sys.stderr)
        return 4
    return 0 if final_job.status == JobStatus.DONE else 1


if __name__ == "__main__":
    raise SystemExit(main())

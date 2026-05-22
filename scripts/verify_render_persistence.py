#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RENDER_BACKEND_DIR = PROJECT_ROOT / "render_backend"


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def _external_read_only(env_file: Path) -> dict[str, Any]:
    env_values = _load_env_file(env_file)
    supabase_url = env_values.get("SUPABASE_URL", os.environ.get("SUPABASE_URL", "")).rstrip("/")
    service_key = "".join(
        env_values.get("SUPABASE_SERVICE_KEY", os.environ.get("SUPABASE_SERVICE_KEY", "")).split()
    )
    bucket = env_values.get(
        "SUPABASE_STORAGE_BUCKET",
        os.environ.get("SUPABASE_STORAGE_BUCKET", "manim-videos"),
    )
    result: dict[str, Any] = {
        "supabase_url_configured": bool(supabase_url),
        "service_key_configured": bool(service_key),
        "bucket": bucket,
    }
    if not supabase_url or not service_key:
        result["ok"] = False
        result["error"] = "SUPABASE_URL or SUPABASE_SERVICE_KEY is missing"
        return result

    headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}
    checks = {
        "render_jobs_table": (
            f"{supabase_url}/rest/v1/render_jobs?select=job_id,status,video_path,updated_at&limit=1"
        ),
        "job_logs_table": (
            f"{supabase_url}/rest/v1/job_logs?select=job_id,level,stage,created_at&limit=1"
        ),
        "storage_bucket": f"{supabase_url}/storage/v1/bucket/{bucket}",
    }

    ok = True
    for name, url in checks.items():
        try:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=15) as resp:
                result[name] = {"status": resp.status}
                ok = ok and 200 <= resp.status < 300
        except urllib.error.HTTPError as exc:
            body = exc.read(120).decode("utf-8", "ignore")
            result[name] = {"status": exc.code, "body_prefix": body[:80]}
            ok = False
        except Exception as exc:
            result[name] = {"error": type(exc).__name__, "message": str(exc)[:80]}
            ok = False

    result["ok"] = ok
    return result


def _local_memory_smoke() -> dict[str, Any]:
    os.environ["SUPABASE_URL"] = ""
    os.environ["SUPABASE_SERVICE_KEY"] = ""
    os.environ["MANIM_API_KEY"] = os.environ.get("MANIM_API_KEY", "dev-key-change-in-production")
    if str(RENDER_BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(RENDER_BACKEND_DIR))

    try:
        import app as backend  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        return {"ok": False, "error": f"missing backend dependency: {exc.name}"}

    code = (
        "from manim import *\n"
        "class Test(Scene):\n"
        "    def construct(self):\n"
        "        self.play(Create(Circle()))\n"
        "        self.wait(0.1)\n"
    )
    with tempfile.TemporaryDirectory() as output_dir:
        backend.OUTPUT_DIR = backend.Path(output_dir)
        backend._jobs.clear()
        backend.app.config["_PERSISTENCE_INITIALIZED"] = False
        client = backend.app.test_client()
        submit = client.post(
            "/render-async",
            headers={"X-API-Key": backend.API_KEY},
            json={"code": code, "scene_name": "Test"},
        )
        submit_json = submit.get_json() or {}
        if submit.status_code != 202:
            return {"ok": False, "stage": "submit", "status": submit.status_code, "body": submit_json}

        job_id = submit_json["job_id"]
        status_payload: dict[str, Any] | None = None
        for _ in range(90):
            status_resp = client.get(f"/status/{job_id}", headers={"X-API-Key": backend.API_KEY})
            status_payload = status_resp.get_json() or {}
            if status_resp.status_code != 200:
                return {
                    "ok": False,
                    "stage": "status",
                    "status": status_resp.status_code,
                    "body": status_payload,
                }
            if status_payload.get("status") in {"done", "failed"}:
                break
            time.sleep(0.5)

        if not status_payload or status_payload.get("status") != "done":
            return {"ok": False, "stage": "render", "body": status_payload}

        download = client.get(f"/download/{job_id}", headers={"X-API-Key": backend.API_KEY})
        if download.status_code != 200 or not download.content_type.startswith("video/mp4"):
            return {
                "ok": False,
                "stage": "download",
                "status": download.status_code,
                "content_type": download.content_type,
            }

        return {
            "ok": True,
            "job_id_prefix": job_id[:8],
            "final_status": status_payload["status"],
            "download_content_type": download.content_type,
            "download_bytes": len(download.data),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify render backend persistence readiness.")
    parser.add_argument("--env-file", default=".env.local", help="env file for external read-only checks")
    parser.add_argument("--external-read-only", action="store_true", help="check Supabase tables and bucket")
    parser.add_argument("--local-memory-smoke", action="store_true", help="run local memory-mode API smoke")
    args = parser.parse_args()

    checks: dict[str, Any] = {}
    if args.external_read_only:
        checks["external_read_only"] = _external_read_only(PROJECT_ROOT / args.env_file)
    if args.local_memory_smoke:
        checks["local_memory_smoke"] = _local_memory_smoke()
    if not checks:
        parser.error("choose at least one check")

    ok = all(isinstance(value, dict) and value.get("ok") is True for value in checks.values())
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

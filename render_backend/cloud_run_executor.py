"""Cloud Run Jobs dispatch support for Aegis-Manim renders."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import requests


CLOUD_RUN_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


class CloudRunConfigError(RuntimeError):
    """Raised when Cloud Run executor configuration is incomplete."""


class CloudRunDispatchError(RuntimeError):
    """Raised when Cloud Run rejects a job execution request."""


@dataclass(frozen=True)
class CloudRunExecution:
    name: str | None
    uid: str | None
    response: dict[str, Any]


def cloud_run_executor_configured() -> bool:
    return all(
        os.environ.get(key, "").strip()
        for key in ("CLOUD_RUN_PROJECT", "CLOUD_RUN_REGION", "CLOUD_RUN_JOB_NAME")
    )


def cloud_run_health_payload() -> dict[str, Any]:
    return {
        "configured": cloud_run_executor_configured(),
        "project": os.environ.get("CLOUD_RUN_PROJECT", "").strip() or None,
        "region": os.environ.get("CLOUD_RUN_REGION", "").strip() or None,
        "job_name": os.environ.get("CLOUD_RUN_JOB_NAME", "").strip() or None,
        "credentials_configured": bool(
            os.environ.get("CLOUD_RUN_ACCESS_TOKEN", "").strip()
            or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
            or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON", "").strip()
        ),
    }


def _job_resource_name() -> str:
    project = os.environ.get("CLOUD_RUN_PROJECT", "").strip()
    region = os.environ.get("CLOUD_RUN_REGION", "").strip()
    job_name = os.environ.get("CLOUD_RUN_JOB_NAME", "").strip()
    if not project or not region or not job_name:
        raise CloudRunConfigError(
            "CLOUD_RUN_PROJECT, CLOUD_RUN_REGION, and CLOUD_RUN_JOB_NAME are required"
        )
    return f"projects/{project}/locations/{region}/jobs/{job_name}"


def _access_token() -> str:
    explicit_token = os.environ.get("CLOUD_RUN_ACCESS_TOKEN", "").strip()
    if explicit_token:
        return explicit_token

    try:
        import google.auth
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account
    except ImportError as exc:  # pragma: no cover - depends on optional deployment dependency
        raise CloudRunConfigError(
            "google-auth is required unless CLOUD_RUN_ACCESS_TOKEN is configured"
        ) from exc

    credentials_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON", "").strip()
    if credentials_json:
        try:
            info = json.loads(credentials_json)
        except json.JSONDecodeError as exc:
            raise CloudRunConfigError("GOOGLE_APPLICATION_CREDENTIALS_JSON is not valid JSON") from exc
        credentials = service_account.Credentials.from_service_account_info(
            info,
            scopes=[CLOUD_RUN_SCOPE],
        )
    else:
        credentials, _ = google.auth.default(scopes=[CLOUD_RUN_SCOPE])

    credentials.refresh(Request())
    if not credentials.token:
        raise CloudRunConfigError("Could not acquire a Cloud Run access token")
    return credentials.token


def dispatch_cloud_run_render_job(
    job_id: str,
    render_mode: str,
    timeout_seconds: int | None = None,
) -> CloudRunExecution:
    resource_name = _job_resource_name()
    url = f"https://run.googleapis.com/v2/{resource_name}:run"
    env = [
        {"name": "AEGIS_RENDER_JOB_ID", "value": job_id},
        {"name": "AEGIS_RENDER_MODE", "value": render_mode},
        {"name": "AEGIS_RENDER_EXECUTOR", "value": "cloud_run"},
    ]
    container_name = os.environ.get("CLOUD_RUN_CONTAINER_NAME", "").strip()
    container_override: dict[str, Any] = {"env": env}
    if container_name:
        container_override["name"] = container_name

    overrides: dict[str, Any] = {"containerOverrides": [container_override]}
    task_count = os.environ.get("CLOUD_RUN_TASK_COUNT", "").strip()
    if task_count:
        overrides["taskCount"] = int(task_count)
    effective_timeout = timeout_seconds or int(os.environ.get("CLOUD_RUN_JOB_TIMEOUT_SECONDS", "0") or "0")
    if effective_timeout > 0:
        overrides["timeout"] = f"{effective_timeout}s"

    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {_access_token()}",
            "Content-Type": "application/json",
        },
        json={"overrides": overrides},
        timeout=15,
    )
    if response.status_code not in (200, 201):
        raise CloudRunDispatchError(f"Cloud Run job dispatch failed with HTTP {response.status_code}")
    payload = response.json()
    return CloudRunExecution(
        name=payload.get("name"),
        uid=payload.get("uid"),
        response=payload,
    )

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from glob import glob
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from alignment import generate_alignment
from llm_providers import DEFAULT_PROVIDER, provider_presets_for_ui, resolve_provider
from manim_knowledge import (
    build_repair_feedback,
    classify_render_error,
    knowledge_sources_for_ui,
    precheck_manim_code,
    repair_recipes_for_ui,
    summarize_precheck_for_prompt,
)
from manim_agent import (
    DEFAULT_MODEL,
    DEFAULT_ZHIPU_ENDPOINT,
    PROJECT_ROOT,
    apply_runtime_compatibility_fixes,
    extract_python_only,
    generate_code_with_llm,
    is_placeholder_api_key,
    load_system_prompt,
)

SYSTEM_PROMPT = load_system_prompt()
GENERATED_DIR = PROJECT_ROOT / "generated"
RUNTIME_LOG_DIR = PROJECT_ROOT / "logs"
RUNTIME_LOG_PATH = RUNTIME_LOG_DIR / "web_runtime.log"
BUG_LOG_PATH = RUNTIME_LOG_DIR / "bug_trace.jsonl"
APP_VERSION = "web_app_v20260429_1"
MAX_RENDER_ATTEMPTS = 3
COMPLEX_PROMPT_MIN_LEN = 600
VIDEO_CACHE: dict[str, Path] = {}
VIDEO_CACHE_LOCK = threading.Lock()
JOB_STORE: dict[str, dict[str, Any]] = {}
JOB_STORE_LOCK = threading.Lock()

# Local trial plans (auto-detect env keys)
LOCAL_TRIAL_PLANS = {
    "trial-kimi-priority": {
        "name": "免费试用 · Kimi 优先",
        "description": "本地内测免费额度：优先使用 Kimi，额度或调用失败时自动切换 MiniMax。",
        "model_label": "Kimi 优先 / MiniMax 备用",
        "attempts": (
            {"provider_id": "kimi-code", "env": "KIMI_CODE_API_KEY", "model": "kimi-for-coding"},
            {"provider_id": "minimax-coding-cn", "env": "MINIMAX_API_KEY", "model": "MiniMax-M2.7"},
        ),
    },
    "trial-minimax-direct": {
        "name": "免费试用 · MiniMax 稳定",
        "description": "本地内测免费额度：直接使用 MiniMax，适合较长或更稳的教学脚本生成。",
        "model_label": "MiniMax 稳定试用",
        "attempts": (
            {"provider_id": "minimax-coding-cn", "env": "MINIMAX_API_KEY", "model": "MiniMax-M2.7"},
        ),
    },
}


def build_local_trial_config() -> dict[str, object]:
    """Build trial provider entries for local web app when env keys are present."""
    available: dict[str, object] = {}
    for provider_id, plan in LOCAL_TRIAL_PLANS.items():
        has_any_key = any(
            os.getenv(str(att["env"]), "").strip()
            for att in plan["attempts"]
        )
        if not has_any_key:
            continue
        available[provider_id] = {
            "id": provider_id,
            "name": plan["name"],
            "region": "trial",
            "defaultModel": plan["model_label"],
            "models": [plan["model_label"]],
            "requiresApiKey": False,
            "apiKeyPlaceholder": "内测免费试用，不需要填写 Key",
            "serverManaged": True,
            "hideApiKey": True,
            "hideBaseUrl": True,
            "lockModel": True,
            "displayProtocol": "免费试用",
            "description": plan["description"],
        }
    return available


def ensure_generated_dir() -> None:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)


def ensure_runtime_log_dir() -> None:
    RUNTIME_LOG_DIR.mkdir(parents=True, exist_ok=True)


def append_runtime_log(event: str, detail: str) -> None:
    ensure_runtime_log_dir()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    safe_detail = detail.replace("\n", " ").strip()
    line = f"[{timestamp}] {event} | {safe_detail}\n"
    with RUNTIME_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line)


def build_request_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]


def safe_short_text(value: str, max_len: int = 300) -> str:
    cleaned = value.replace("\n", " ").strip()
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 3] + "..."


def prompt_fingerprint(prompt: str) -> str:
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    return digest[:16]


def is_complex_learning_prompt(prompt: str) -> bool:
    markers = (
        "$",
        "\\",
        "forall",
        "exists",
        "argmax",
        "argmin",
        "均衡",
        "效用",
        "最优反应",
        "纳什",
        "证明",
        "定义",
    )
    return len(prompt) >= COMPLEX_PROMPT_MIN_LEN or any(marker in prompt for marker in markers)


def compact_prompt_for_brief(prompt: str, max_len: int = 520) -> str:
    without_formula = re.sub(r"\$[^$]*\$", " [公式略] ", prompt)
    without_formula = re.sub(r"\\[A-Za-z]+", " ", without_formula)
    normalized = re.sub(r"\s+", " ", without_formula).strip()
    if len(normalized) <= max_len:
        return normalized
    return normalized[: max_len - 3].rstrip() + "..."


def build_teaching_brief(prompt: str) -> str:
    core_question = compact_prompt_for_brief(prompt)
    return "\n".join(
        [
            "教学 brief：把复杂问题先转换成可动画化结构，再写 Manim 代码。",
            f"用户问题摘要：{core_question}",
            "教学目标：解释这个抽象概念的含义、成立条件、关键直觉和一个最小例子。",
            "画面段落：1. 给出直觉场景；2. 展示关键对象和符号含义；3. 用动态变化说明条件；4. 总结结论。",
            "视觉策略：优先用坐标轴、集合、点、箭头、表格和高亮关系；不要把原始公式整段塞进画面。",
            "讲解策略：公式只保留必要符号，复杂推导改写成短句和分步说明。",
            "语言策略：默认使用中文标题、中文标签、中文阶段说明和中文结论；变量符号可以保留英文缩写，但必须用中文解释含义。",
            "排版策略：所有 Text 都写 font_size；长解释拆成 VGroup 多行短句，先 FadeOut 或 ReplacementTransform 旧讲解再出现新讲解。",
            "Manim 约束：使用 Text，不使用 Tex/MathTex；避免依赖 LaTeX；代码必须能在本地 Manim 版本稳定渲染。",
        ]
    )


def model_for_attempt(provider: Any, requested_model: str, attempt: int) -> str:
    if attempt <= 1:
        return requested_model
    highspeed = f"{requested_model}-highspeed"
    models = tuple(getattr(provider, "models", ()) or ())
    if highspeed in models:
        return highspeed
    return requested_model


def append_bug_log(
    *,
    request_id: str,
    stage: str,
    severity: str,
    message: str,
    detail: str | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    ensure_runtime_log_dir()
    entry: dict[str, Any] = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "requestId": request_id,
        "stage": stage,
        "severity": severity,
        "message": safe_short_text(message, 200),
    }
    if detail:
        entry["detail"] = safe_short_text(detail, 3000)
    if context:
        entry["context"] = context
    with BUG_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_recent_bug_entries(limit: int, request_id: str | None = None) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    if not BUG_LOG_PATH.exists():
        return []

    lines = BUG_LOG_PATH.read_text(encoding="utf-8").splitlines()
    if not lines:
        return []

    records: list[dict[str, Any]] = []
    for raw in reversed(lines):
        text = raw.strip()
        if not text:
            continue
        try:
            item = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            if request_id and item.get("requestId") != request_id:
                continue
            records.append(item)
        if len(records) >= limit:
            break
    return records


def safe_scene_name(raw_name: str) -> str:
    candidate = re.sub(r"[^A-Za-z0-9_]", "", raw_name.strip())
    if not candidate:
        return "GeneratedScene"
    if not re.match(r"[A-Za-z_]", candidate[0]):
        candidate = f"Scene_{candidate}"
    return candidate


def detect_scene_name(code: str, fallback: str) -> str:
    match = re.search(r"class\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*Scene\s*\)", code)
    if match:
        return match.group(1)
    return fallback


def render_scene(scene_file: Path, scene_name: str) -> None:
    cmd = [
        sys.executable,
        "-m",
        "manim",
        "-ql",
        "--media_dir",
        "media",
        str(scene_file),
        scene_name,
    ]
    result = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        detail = stderr or stdout or "Unknown render error."
        if len(detail) > 2500:
            detail = detail[-2500:]
        raise RuntimeError(detail)


def find_latest_video(scene_file: Path, scene_name: str) -> Path | None:
    candidates: list[Path] = []
    file_stem = scene_file.stem

    first_pattern = PROJECT_ROOT / "media" / "videos" / file_stem / "**" / f"{scene_name}.mp4"
    for p in glob(str(first_pattern), recursive=True):
        if "partial_movie_files" in p:
            continue
        candidates.append(Path(p))

    if not candidates:
        second_pattern = PROJECT_ROOT / "media" / "videos" / "**" / f"{scene_name}.mp4"
        for p in glob(str(second_pattern), recursive=True):
            if "partial_movie_files" in p:
                continue
            candidates.append(Path(p))

    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def register_video(path: Path) -> str:
    video_id = uuid4().hex
    with VIDEO_CACHE_LOCK:
        VIDEO_CACHE[video_id] = path
    return video_id


def create_job(prompt: str) -> str:
    job_id = build_request_id()
    now = datetime.now().isoformat(timespec="seconds")
    with JOB_STORE_LOCK:
        JOB_STORE[job_id] = {
            "ok": True,
            "jobId": job_id,
            "requestId": job_id,
            "status": "queued",
            "stage": "queued",
            "currentStudentMessage": "任务已进入队列，正在准备拆解你的学习问题。",
            "events": [],
            "technicalEvents": [],
            "result": None,
            "error": None,
            "promptHash": prompt_fingerprint(prompt) if prompt else None,
            "createdAt": now,
            "updatedAt": now,
        }
    return job_id


def emit_job_event(
    job_id: str,
    *,
    stage: str,
    student_message: str,
    technical_message: str = "",
    status: str | None = None,
    severity: str = "info",
    attempt: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    event: dict[str, Any] = {
        "time": now,
        "stage": stage,
        "severity": severity,
        "studentMessage": student_message,
    }
    if attempt is not None:
        event["attempt"] = attempt
    if metadata:
        event["metadata"] = metadata
    technical_event = {
        **event,
        "technicalMessage": technical_message or student_message,
    }
    with JOB_STORE_LOCK:
        job = JOB_STORE.get(job_id)
        if not job:
            return
        job["stage"] = stage
        if status:
            job["status"] = status
        job["currentStudentMessage"] = student_message
        job["events"].append(event)
        job["technicalEvents"].append(technical_event)
        job["updatedAt"] = now


def finish_job(job_id: str, result: dict[str, Any]) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    with JOB_STORE_LOCK:
        job = JOB_STORE.get(job_id)
        if not job:
            return
        job["status"] = "succeeded"
        job["stage"] = "complete"
        job["currentStudentMessage"] = "教学视频已经生成完成，讲稿段落也准备好了。"
        job["result"] = result
        job["updatedAt"] = now


def fail_job(job_id: str, error_payload: dict[str, Any], student_message: str) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    with JOB_STORE_LOCK:
        job = JOB_STORE.get(job_id)
        if not job:
            return
        job["status"] = "failed"
        job["stage"] = "failed"
        job["currentStudentMessage"] = student_message
        job["error"] = error_payload
        job["updatedAt"] = now


def job_snapshot(job_id: str) -> dict[str, Any] | None:
    with JOB_STORE_LOCK:
        job = JOB_STORE.get(job_id)
        if not job:
            return None
        return json.loads(json.dumps(job, ensure_ascii=False))


def probe_video_duration(path: Path) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None

    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if result.returncode != 0:
        return None
    return optional_positive_float((result.stdout or "").strip())


def json_error(
    message: str,
    status: int = 400,
    detail: str | None = None,
    request_id: str | None = None,
) -> tuple[int, dict[str, Any]]:
    payload: dict[str, Any] = {"ok": False, "error": message}
    if detail:
        payload["detail"] = detail
    if request_id:
        payload["requestId"] = request_id
    return status, payload


def optional_positive_float(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def run_generate_job(job_id: str, payload: dict[str, Any]) -> None:
    prompt = str(payload.get("prompt", "")).strip()
    provider_id = str(payload.get("provider", DEFAULT_PROVIDER)).strip() or DEFAULT_PROVIDER
    provider = resolve_provider(provider_id)
    api_key = str(payload.get("apiKey", "")).strip()
    model = str(payload.get("model", "")).strip() or provider.default_model or DEFAULT_MODEL
    base_url = str(payload.get("baseUrl", "")).strip()
    endpoint = str(payload.get("endpoint", "")).strip()
    scene_name = safe_scene_name(str(payload.get("sceneName", "GeneratedScene")))
    no_render = bool(payload.get("noRender", False))

    try:
        temperature = float(payload.get("temperature", 0.2))
    except (TypeError, ValueError):
        temperature = 0.2
    temperature = max(0.0, min(1.0, temperature))

    # Resolve local trial plans (server-managed keys from env)
    trial_plan = LOCAL_TRIAL_PLANS.get(provider_id)
    if trial_plan:
        resolved_trial = None
        for attempt in trial_plan["attempts"]:
            env_key = os.getenv(str(attempt["env"]), "").strip()
            if env_key:
                resolved_trial = attempt
                resolved_trial_api_key = env_key
                break
        if resolved_trial:
            provider_id = str(resolved_trial["provider_id"])
            provider = resolve_provider(provider_id)
            api_key = resolved_trial_api_key
            model = str(resolved_trial["model"]) or provider.default_model or DEFAULT_MODEL
            base_url = ""
            endpoint = ""
        else:
            emit_job_event(
                job_id,
                status="failed",
                stage="validation",
                student_message="本地试用模型未配置：请设置 KIMI_CODE_API_KEY 或 MINIMAX_API_KEY 环境变量。",
                technical_message="LOCAL_TRIAL_NO_KEYS_CONFIGURED",
            )
            fail_job(
                job_id,
                {
                    "ok": False,
                    "error": "Local trial keys not configured.",
                    "detail": "Please set KIMI_CODE_API_KEY or MINIMAX_API_KEY env var.",
                    "requestId": job_id,
                },
                "本地试用模型未配置：请设置 KIMI_CODE_API_KEY 或 MINIMAX_API_KEY 环境变量。",
            )
            return

    request_context = {
        "provider": provider.id,
        "providerName": provider.name,
        "apiType": provider.api_type,
        "model": model,
        "baseUrl": base_url or provider.base_url,
        "endpoint": endpoint or provider.base_url,
        "sceneNameInput": scene_name,
        "temperature": temperature,
        "noRender": no_render,
        "promptLen": len(prompt),
        "promptHash": prompt_fingerprint(prompt) if prompt else None,
    }

    emit_job_event(
        job_id,
        status="running",
        stage="validation",
        student_message="正在确认你的问题足够清楚，并准备拆成教学动画。",
        technical_message=f"provider={provider.id} model={model}",
    )

    if len(prompt) < 6:
        detail = "Please provide a clearer learning question."
        append_bug_log(
            request_id=job_id,
            stage="validation",
            severity="warn",
            message="Prompt is too short",
            detail=detail,
            context=request_context,
        )
        fail_job(
            job_id,
            {"ok": False, "error": "Prompt is too short.", "detail": detail, "requestId": job_id},
            "这个问题还不够明确，需要补充你想理解的概念或例子。",
        )
        return

    if provider.requires_api_key and not api_key:
        detail = f"Please paste your own {provider.name} API key in the form."
        append_bug_log(
            request_id=job_id,
            stage="validation",
            severity="warn",
            message="Missing API key",
            detail=detail,
            context=request_context,
        )
        fail_job(
            job_id,
            {"ok": False, "error": "Missing API key.", "detail": detail, "requestId": job_id},
            "模型服务还没有可用凭证，暂时不能开始生成动画。",
        )
        return

    if is_placeholder_api_key(api_key):
        detail = "Please use a real key generated in your own account."
        append_bug_log(
            request_id=job_id,
            stage="validation",
            severity="warn",
            message="Placeholder API key detected",
            detail=detail,
            context=request_context,
        )
        fail_job(
            job_id,
            {"ok": False, "error": "Placeholder API key detected.", "detail": detail, "requestId": job_id},
            "检测到示例 Key，暂时不能调用真实模型生成动画。",
        )
        return

    ensure_generated_dir()
    resolved_endpoint = endpoint or provider.base_url
    provider_name = provider.name
    max_attempts = MAX_RENDER_ATTEMPTS
    retry_feedback = ""
    last_code = ""
    last_scene_file: Path | None = None
    last_scene_name = scene_name
    last_notes: list[str] = []
    last_precheck: list[Any] = []
    teaching_brief = build_teaching_brief(prompt) if is_complex_learning_prompt(prompt) else ""

    if teaching_brief:
        emit_job_event(
            job_id,
            stage="brief",
            student_message="这个问题比较复杂，先把它拆成教学目标、画面段落和可动画化结构。",
            technical_message="TEACHING_BRIEF_CREATED",
            metadata={"briefLength": len(teaching_brief), "promptLength": len(prompt)},
        )

    for attempt in range(1, max_attempts + 1):
        active_model = model_for_attempt(provider, model, attempt)
        effective_prompt = teaching_brief or prompt
        if retry_feedback:
            effective_prompt = f"{effective_prompt}\n\n{retry_feedback}"

        try:
            emit_job_event(
                job_id,
                stage="model",
                student_message=f"正在生成第 {attempt} 版 Manim 教学脚本，把问题转换成可播放的动画结构。",
                technical_message=f"MODEL_REQUEST_START attempt={attempt}/{max_attempts} provider={provider.id} model={active_model}",
                attempt=attempt,
            )
            append_runtime_log(
                "MODEL_REQUEST_START",
                f"request_id={job_id} attempt={attempt}/{max_attempts} provider={provider.id} model={active_model} endpoint={resolved_endpoint}",
            )
            raw_code, provider_name, resolved_endpoint = generate_code_with_llm(
                provider_id=provider.id,
                api_key=api_key,
                base_url=base_url or None,
                endpoint=(endpoint or DEFAULT_ZHIPU_ENDPOINT) if provider.id == "zhipu" else None,
                model=active_model,
                system_prompt=SYSTEM_PROMPT,
                user_prompt=effective_prompt,
                temperature=temperature,
            )
            request_context["endpoint"] = resolved_endpoint
            code = extract_python_only(raw_code)
            code, notes = apply_runtime_compatibility_fixes(code)
            precheck_issues = precheck_manim_code(code, scene_name)
            last_precheck = precheck_issues
            if notes:
                append_runtime_log(
                    "COMPATIBILITY_FIX",
                    f"request_id={job_id} attempt={attempt}/{max_attempts} {'; '.join(notes)}",
                )
            emit_job_event(
                job_id,
                stage="precheck",
                student_message="正在用 Manim 规则库检查场景结构、文字、坐标轴和常见不稳定写法。",
                technical_message=f"precheck issues={len(precheck_issues)} compatibility_notes={len(notes)}",
                attempt=attempt,
                metadata={
                    "precheckIssues": [
                        {
                            "category": issue.category,
                            "severity": issue.severity,
                            "studentMessage": issue.student_message,
                            "technicalMessage": issue.technical_message,
                            "repairHint": issue.repair_hint,
                            "sourceIds": list(issue.source_ids),
                        }
                        for issue in precheck_issues
                    ],
                    "compatibilityNotes": notes,
                },
            )
            append_runtime_log(
                "MODEL_REQUEST_OK",
                f"request_id={job_id} attempt={attempt}/{max_attempts} provider={provider.id} model={active_model} chars={len(code)}",
            )
        except Exception as exc:
            detail = str(exc)
            append_runtime_log(
                "MODEL_REQUEST_FAIL",
                f"request_id={job_id} attempt={attempt}/{max_attempts} provider={provider.id} model={active_model} endpoint={resolved_endpoint} error={detail}",
            )
            append_bug_log(
                request_id=job_id,
                stage="model",
                severity="error",
                message="Model request failed",
                detail=detail,
                context={**request_context, "attempt": attempt, "maxAttempts": max_attempts, "model": active_model},
            )
            if attempt < max_attempts:
                retry_feedback = (
                    "# Model request failed\n"
                    "The previous model call did not return a script. Keep the answer shorter, use the teaching brief, "
                    "avoid long formulas, and output only complete Manim Python code.\n"
                    f"Failure detail: {detail[-800:]}"
                )
                emit_job_event(
                    job_id,
                    stage="repair",
                    student_message="模型这次没有及时返回，正在压缩教学 brief 并换更快的生成方式重试。",
                    technical_message=f"MODEL_REQUEST_RETRY detail={detail}",
                    severity="warn",
                    attempt=attempt,
                )
                continue
            fail_job(
                job_id,
                {"ok": False, "error": "Model request failed.", "detail": detail, "requestId": job_id},
                "模型生成阶段连续失败，暂时还没有形成可用动画脚本。",
            )
            return

        blocking_precheck = [issue for issue in precheck_issues if issue.severity == "error"]
        if blocking_precheck and attempt < max_attempts:
            retry_feedback = summarize_precheck_for_prompt(blocking_precheck)
            emit_job_event(
                job_id,
                stage="repair",
                student_message="规则库发现这版脚本还不能稳定播放，正在先修好场景结构再渲染。",
                technical_message=retry_feedback,
                severity="warn",
                attempt=attempt,
            )
            append_bug_log(
                request_id=job_id,
                stage="precheck",
                severity="warn",
                message="Pre-render rule check requested repair",
                detail=retry_feedback,
                context={**request_context, "attempt": attempt, "maxAttempts": max_attempts},
            )
            continue

        detected_scene_name = detect_scene_name(code, scene_name)
        filename = f"scene_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}.py"
        scene_file = GENERATED_DIR / filename
        scene_file.write_text(code.strip() + "\n", encoding="utf-8")
        last_code = code
        last_scene_file = scene_file
        last_scene_name = detected_scene_name
        last_notes = notes

        response: dict[str, Any] = {
            "ok": True,
            "requestId": job_id,
            "provider": provider.id,
            "providerName": provider_name,
            "endpoint": resolved_endpoint,
            "sceneName": detected_scene_name,
            "code": code,
            "codeFile": str(scene_file.relative_to(PROJECT_ROOT)),
            "attempt": attempt,
            "maxAttempts": max_attempts,
            "teachingBrief": teaching_brief or None,
            "knowledgeSources": knowledge_sources_for_ui(),
            "repairRecipes": repair_recipes_for_ui(),
        }
        if notes:
            response["warnings"] = notes
        if precheck_issues:
            response["precheckIssues"] = [
                {
                    "category": issue.category,
                    "severity": issue.severity,
                    "studentMessage": issue.student_message,
                    "technicalMessage": issue.technical_message,
                    "repairHint": issue.repair_hint,
                    "sourceIds": list(issue.source_ids),
                }
                for issue in precheck_issues
            ]

        if no_render:
            response["message"] = "Code generated successfully. Render skipped."
            append_runtime_log("GENERATE_SKIP_RENDER", f"request_id={job_id} file={scene_file.name} scene={detected_scene_name}")
            emit_job_event(
                job_id,
                stage="complete",
                student_message="脚本已经生成完成，这次按你的选择跳过了视频渲染。",
                technical_message=f"GENERATE_SKIP_RENDER file={scene_file.name}",
                attempt=attempt,
            )
            finish_job(job_id, response)
            return

        try:
            emit_job_event(
                job_id,
                stage="render",
                student_message="正在渲染动画，检查画面能否清楚表达这个概念。",
                technical_message=f"RENDER_START file={scene_file.name} scene={detected_scene_name}",
                attempt=attempt,
            )
            render_scene(scene_file, detected_scene_name)
            video_path = find_latest_video(scene_file, detected_scene_name)
            if video_path is None:
                raise RuntimeError("Render completed but output video was not found.")
            video_duration = probe_video_duration(video_path)
            response["videoId"] = register_video(video_path)
            if video_duration is not None:
                response["videoDuration"] = video_duration
            emit_job_event(
                job_id,
                stage="alignment",
                student_message="视频已经出来，正在把讲稿段落和画面时间对应起来。",
                technical_message="ALIGNMENT_FALLBACK initial metadata alignment",
                attempt=attempt,
            )
            response["alignment"] = generate_alignment(
                prompt=prompt,
                code=code,
                scene_name=detected_scene_name,
                video_duration=video_duration,
                llm_call=None,
            )
            append_runtime_log(
                "ALIGNMENT_FALLBACK",
                f"request_id={job_id} scene={detected_scene_name} reason=initial_response_uses_fast_metadata_alignment",
            )
            response["message"] = "Code generated and video rendered successfully."
            if attempt > 1:
                response["message"] += f" Auto-retry succeeded on attempt {attempt}."
            append_runtime_log(
                "RENDER_OK",
                f"request_id={job_id} attempt={attempt}/{max_attempts} file={scene_file.name} scene={detected_scene_name} video={video_path}",
            )
            finish_job(job_id, response)
            return
        except Exception as exc:
            detail = str(exc)
            classification = classify_render_error(detail)
            append_runtime_log(
                "RENDER_FAIL",
                f"request_id={job_id} attempt={attempt}/{max_attempts} file={scene_file.name} scene={detected_scene_name} category={classification.category} error={detail}",
            )
            append_bug_log(
                request_id=job_id,
                stage="render",
                severity="error",
                message="Render failed",
                detail=detail,
                context={
                    **request_context,
                    "attempt": attempt,
                    "maxAttempts": max_attempts,
                    "sceneNameDetected": detected_scene_name,
                    "codeFile": str(scene_file.relative_to(PROJECT_ROOT)),
                    "warnings": notes,
                    "errorCategory": classification.category,
                    "repairRecipes": list(classification.recipe_ids),
                },
            )
            emit_job_event(
                job_id,
                stage="repair",
                student_message=classification.student_message,
                technical_message=f"{classification.technical_message} Error: {detail[-800:]}",
                severity="warn",
                attempt=attempt,
                metadata={
                    "errorCategory": classification.category,
                    "repairRecipes": list(classification.recipe_ids),
                },
            )
            if attempt < max_attempts:
                retry_feedback = build_repair_feedback(
                    original_prompt=prompt,
                    render_error=detail,
                    classification=classification,
                    precheck_issues=precheck_issues,
                    attempt=attempt + 1,
                )
                append_runtime_log("RENDER_RETRY", f"request_id={job_id} next_attempt={attempt + 1}/{max_attempts}")
                continue

            err = {
                "ok": False,
                "error": f"Render failed after {max_attempts} attempts.",
                "detail": detail,
                "requestId": job_id,
                "attempt": attempt,
                "maxAttempts": max_attempts,
                "code": last_code,
                "sceneName": last_scene_name,
                "errorCategory": classification.category,
                "studentMessage": classification.student_message,
                "repairRecipes": list(classification.recipe_ids),
            }
            if last_scene_file is not None:
                err["codeFile"] = str(last_scene_file.relative_to(PROJECT_ROOT))
            if last_notes:
                err["warnings"] = last_notes
            if last_precheck:
                err["precheckIssues"] = [
                    {
                        "category": issue.category,
                        "severity": issue.severity,
                        "studentMessage": issue.student_message,
                        "technicalMessage": issue.technical_message,
                        "repairHint": issue.repair_hint,
                        "sourceIds": list(issue.source_ids),
                    }
                    for issue in last_precheck
                ]
            fail_job(
                job_id,
                err,
                "系统已经尝试多次重写这段动画，但这次还没有生成清晰稳定的视频。",
            )
            return


def make_index_html() -> str:
    provider_config = provider_presets_for_ui()
    local_trial = build_local_trial_config()
    if local_trial:
        provider_config["providers"] = {**local_trial, **provider_config["providers"]}
        provider_config["regionLabels"] = {
            "trial": "内测免费试用",
            **provider_config.get("regionLabels", {}),
        }
        if "trial-kimi-priority" in local_trial:
            provider_config["defaultProvider"] = "trial-kimi-priority"
    provider_config_json = json.dumps(provider_config, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Aegis Studio Web</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet" />
  <script>
    window.MathJax = {{
      startup: {{ typeset: false }},
      tex: {{ inlineMath: [["\\\\(", "\\\\)"], ["$", "$"]], displayMath: [["\\\\[", "\\\\]"], ["$$", "$$"]] }},
      options: {{ skipHtmlTags: ["script", "noscript", "style", "textarea", "pre", "code"] }}
    }};
  </script>
  <script async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
  <style>
    :root {{
      --bg: #0f0f0f;
      --bg-2: #161616;
      --bg-3: #1c1c1c;
      --fg: #d8d4cf;
      --fg-bright: #e8e4df;
      --muted: #6b6560;
      --muted-2: #4a4540;
      --accent: #5a8a7a;
      --accent-2: #7a7a6a;
      --accent-3: #6a7a8a;
      --danger: #8a5a5a;
      --ok: #5a7a6a;
      --code-bg: #13181f;
      --border: #252525;
      --border-light: #2e2e2e;
      --pixel: #d8d4cf;
      --radius: 4px;
      --speed: 200ms;
    }}

    * {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      background: var(--bg);
      color: var(--fg);
      font-family: 'Inter', -apple-system, sans-serif;
      font-size: 14px;
      line-height: 1.55;
      min-height: 100vh;
      overflow-x: hidden;
    }}

    /* subtle pixel grid */
    body::before {{
      content: '';
      position: fixed;
      inset: 0;
      pointer-events: none;
      opacity: 0.25;
      background-image:
        linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px);
      background-size: 8px 8px;
      z-index: 0;
    }}

    /* ── Shell ── */
    .shell {{
      position: relative;
      z-index: 1;
      width: min(1280px, 95vw);
      margin: 28px auto 40px;
      display: grid;
      gap: 20px;
      grid-template-columns: 1.05fr 0.95fr;
      animation: shell-in 420ms ease-out both;
    }}

    body.learning-mode .shell {{
      width: min(1500px, 96vw);
      grid-template-columns: minmax(320px, 0.52fr) minmax(780px, 1.48fr);
      align-items: start;
    }}

    /* ── Panel ── */
    .panel {{
      background: var(--bg-2);
      border: 1px solid var(--border);
      overflow: hidden;
      position: relative;
    }}

    .panel::after {{
      content: '';
      position: absolute;
      inset: 0;
      pointer-events: none;
      box-shadow: inset 0 0 0 1px rgba(255,255,255,0.03);
    }}

    /* ── Hero ── */
    .hero {{
      padding: 16px 22px 12px;
      border-bottom: 1px solid var(--border);
      background: linear-gradient(180deg, rgba(255,255,255,0.02), transparent);
      position: relative;
    }}

    .hero h1 {{
      margin: 0 0 4px;
      font-size: 1.25rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      color: var(--fg-bright);
    }}

    .hero p {{
      margin: 0;
      color: var(--muted);
      font-size: 0.84rem;
      max-width: 42ch;
      line-height: 1.4;
    }}

    .hero small {{
      display: inline-flex;
      margin-top: 6px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.68rem;
      padding: 3px 6px;
      color: var(--muted);
      background: var(--bg-3);
      border: 1px dashed var(--border-light);
    }}

    /* ── Form ── */
    .form-wrap {{
      padding: 16px 22px 18px;
      display: grid;
      gap: 10px;
    }}

    .field {{
      display: grid;
      gap: 4px;
      animation: field-in var(--speed) ease-out both;
    }}
    .field:nth-child(1) {{ animation-delay: 30ms; }}
    .field:nth-child(2) {{ animation-delay: 70ms; }}
    .field:nth-child(3) {{ animation-delay: 110ms; }}

    label {{
      font-size: 0.8rem;
      font-family: 'JetBrains Mono', monospace;
      color: var(--muted);
      letter-spacing: 0.3px;
      text-transform: uppercase;
    }}

    .help {{
      margin-top: -2px;
      color: var(--muted-2);
      font-size: 0.78rem;
    }}

    input, select, textarea {{
      width: 100%;
      border: 1px solid var(--border);
      border-radius: var(--radius);
      font: inherit;
      background: var(--bg);
      color: var(--fg-bright);
      padding: 8px 10px;
      transition: border-color var(--speed);
      outline: none;
    }}

    textarea {{
      min-height: 72px;
      resize: vertical;
      line-height: 1.45;
    }}

    input:focus, select:focus, textarea:focus {{
      border-color: var(--accent);
    }}

    .prompt-preview {{
      display: none;
      border: 1px dashed var(--border-light);
      border-radius: var(--radius);
      background: var(--bg);
      padding: 10px 12px;
      color: var(--fg);
      font-size: 0.84rem;
      line-height: 1.5;
    }}
    .prompt-preview.visible {{ display: block; }}
    .prompt-preview-label {{
      display: block;
      margin-bottom: 6px;
      color: var(--accent);
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.7rem;
      text-transform: uppercase;
    }}

    .rich-text strong {{ font-weight: 700; color: var(--fg-bright); }}
    .rich-text code {{
      font-family: 'JetBrains Mono', monospace;
      color: var(--accent-3);
      background: rgba(106,122,138,0.1);
      border: 1px solid rgba(106,122,138,0.15);
      border-radius: 3px;
      padding: 1px 4px;
      font-size: 0.88em;
    }}

    .row {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }}

    .key-row {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 8px;
    }}

    .provider-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      color: var(--muted);
      font-size: 0.78rem;
    }}

    .provider-pill {{
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      border: 1px dashed var(--border-light);
      padding: 3px 8px;
      background: var(--bg);
      font-family: 'JetBrains Mono', monospace;
      color: var(--muted);
      font-size: 0.72rem;
    }}

    .provider-doc {{
      color: var(--accent-3);
      text-decoration: none;
      border-bottom: 1px solid rgba(106,122,138,0.3);
    }}
    .provider-doc.hidden {{ display: none; }}

    /* ── Buttons ── */
    .tiny-btn, .btn, .ghost-btn {{
      font-family: 'JetBrains Mono', monospace;
      font-weight: 600;
      border-radius: var(--radius);
      cursor: pointer;
      border: none;
      transition: opacity var(--speed), transform var(--speed);
    }}

    .tiny-btn {{
      padding: 0 12px;
      color: var(--fg-bright);
      background: var(--accent);
      min-width: 56px;
      font-size: 0.78rem;
      height: 36px;
    }}
    .tiny-btn:hover {{ opacity: 0.85; }}

    .btn {{
      margin-top: 2px;
      padding: 10px 14px;
      color: var(--bg);
      background: var(--fg-bright);
      letter-spacing: 0.3px;
      font-size: 0.84rem;
      text-transform: uppercase;
    }}
    .btn:hover {{ opacity: 0.9; transform: translateY(-1px); }}
    .btn[disabled] {{ opacity: 0.45; cursor: wait; transform: none; }}

    .ghost-btn {{
      padding: 6px 10px;
      border: 1px solid var(--border-light);
      background: transparent;
      color: var(--muted);
      font-size: 0.74rem;
    }}
    .ghost-btn:hover {{ color: var(--fg); border-color: var(--muted); }}

    .check-row {{
      display: flex;
      align-items: center;
      gap: 10px;
      color: var(--muted);
      font-size: 0.86rem;
    }}
    .check-row input {{
      width: 16px;
      height: 16px;
      accent-color: var(--accent);
      padding: 0;
    }}

    /* ── Status ── */
    .status-box {{
      padding: 10px 12px;
      border-radius: var(--radius);
      border: 1px solid var(--border);
      background: var(--bg);
      color: var(--muted);
      min-height: 44px;
      display: flex;
      align-items: center;
      line-height: 1.45;
      font-size: 0.86rem;
    }}
    .status-box.error {{ border-color: rgba(138,90,90,0.4); background: rgba(138,90,90,0.08); color: #a07070; }}
    .status-box.success {{ border-color: rgba(90,122,106,0.4); background: rgba(90,122,106,0.08); color: #7a9a8a; }}

    /* ── Process Panel ── */
    .process-panel {{
      display: none;
      border: 1px solid var(--border-light);
      background: var(--bg);
      padding: 12px;
      gap: 10px;
    }}
    .process-panel.visible {{ display: grid; animation: field-in 240ms ease-out; }}

    .process-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      color: var(--muted);
      font-size: 0.82rem;
    }}
    .process-time {{
      flex: 0 0 auto;
      color: var(--accent);
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.74rem;
    }}

    .process-steps {{ display: grid; gap: 8px; }}
    .process-feed {{
      display: grid;
      gap: 6px;
      max-height: 170px;
      overflow: auto;
      padding-right: 3px;
    }}
    .process-feed-item {{
      border-left: 2px solid var(--accent);
      padding: 5px 0 5px 9px;
      color: var(--muted);
      font-size: 0.78rem;
      line-height: 1.35;
      background: rgba(255,255,255,0.02);
    }}
    .process-feed-item.warn {{ border-left-color: var(--danger); }}

    .tech-details {{
      border-top: 1px dashed var(--border);
      padding-top: 8px;
      color: var(--muted-2);
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.72rem;
    }}
    .tech-details summary {{ cursor: pointer; color: var(--muted); }}
    .tech-log {{
      white-space: pre-wrap;
      margin: 6px 0 0;
      max-height: 150px;
      overflow: auto;
    }}

    .process-step {{
      display: grid;
      grid-template-columns: auto 1fr;
      align-items: center;
      gap: 9px;
      color: var(--muted-2);
      font-size: 0.8rem;
    }}
    .process-dot {{
      width: 8px;
      height: 8px;
      border: 1px solid var(--border-light);
      background: var(--bg-3);
    }}
    .process-step.active {{ color: var(--fg); font-weight: 600; }}
    .process-step.active .process-dot {{
      border-color: var(--accent);
      background: var(--accent);
      animation: pulse-dot 1.4s ease-in-out infinite;
    }}
    .process-step.done {{ color: var(--ok); }}
    .process-step.done .process-dot {{
      border-color: var(--ok);
      background: var(--ok);
    }}

    /* ── Result Panel ── */
    .result-head {{
      padding: 24px 26px 18px;
      border-bottom: 1px solid var(--border);
      background: linear-gradient(180deg, rgba(255,255,255,0.015), transparent);
    }}
    .result-head h2 {{
      margin: 0 0 8px;
      font-size: 1.35rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      color: var(--fg-bright);
    }}
    .result-head p {{ margin: 0; color: var(--muted); font-size: 0.92rem; }}

    .result-title-row {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 16px;
    }}
    .result-actions {{
      display: none;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }}
    body.learning-mode .result-actions {{ display: flex; }}

    .result-wrap {{
      padding: 20px 26px 24px;
      display: grid;
      gap: 14px;
    }}

    .tag-wrap {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .tag {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border-radius: 999px;
      border: 1px solid var(--border);
      padding: 4px 10px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.72rem;
      color: var(--muted);
      background: var(--bg);
    }}

    .warning-box {{
      display: none;
      padding: 10px 12px;
      border-radius: var(--radius);
      border: 1px dashed rgba(138,90,90,0.4);
      color: #907070;
      background: rgba(138,90,90,0.05);
      font-size: 0.84rem;
      line-height: 1.45;
    }}
    .warning-box.visible {{ display: block; animation: field-in 240ms ease-out; }}

    .code-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
    }}
    .code-header span {{
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.72rem;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}

    .code-section {{
      display: grid;
      gap: 10px;
    }}
    body.learning-mode .code-section {{ display: none; }}
    body.learning-mode.show-code .code-section {{ display: grid; }}

    pre {{
      margin: 0;
      padding: 14px;
      border-radius: var(--radius);
      background: var(--code-bg);
      border: 1px solid var(--border);
      color: #b8c8d8;
      font: 12px/1.6 'JetBrains Mono', monospace;
      max-height: 320px;
      overflow: auto;
    }}

    .lesson-pair {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 14px;
      align-items: stretch;
    }}
    body.learning-mode .lesson-pair {{
      grid-template-columns: 1fr;
      gap: 16px;
    }}

    .video-card {{
      display: none;
      border: 1px solid var(--border);
      background: var(--code-bg);
      padding: 10px;
    }}
    .video-card.visible {{
      display: block;
      animation: panel-up 260ms ease-out;
    }}
    .lesson-pair .video-card.visible {{
      display: flex;
      align-items: center;
    }}

    video {{
      width: 100%;
      border-radius: var(--radius);
      max-height: 520px;
      background: var(--bg);
    }}
    body.learning-mode video {{ max-height: 640px; }}

    /* ── Alignment / Script Panel ── */
    .alignment-panel {{
      display: none;
      border: 1px solid var(--border-light);
      background: linear-gradient(180deg, var(--bg-3), var(--bg-2));
      padding: 14px;
      gap: 12px;
    }}
    .alignment-panel.visible {{
      display: grid;
      grid-template-rows: auto auto minmax(0, 1fr);
      animation: panel-up 260ms ease-out;
    }}

    .alignment-head {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
    }}
    .alignment-head h3 {{
      margin: 0 0 4px;
      font-size: 0.95rem;
      color: var(--fg-bright);
    }}
    .alignment-summary {{
      margin: 0;
      color: var(--muted);
      font-size: 0.82rem;
      line-height: 1.45;
    }}
    .alignment-warning {{
      display: none;
      border-radius: var(--radius);
      border: 1px dashed rgba(140,120,80,0.4);
      color: #908060;
      background: rgba(140,120,80,0.06);
      padding: 9px 11px;
      font-size: 0.8rem;
      line-height: 1.45;
    }}
    .alignment-warning.visible {{ display: block; }}

    .alignment-list {{
      display: grid;
      gap: 10px;
      max-height: 360px;
      overflow: auto;
      padding-right: 2px;
    }}
    body.learning-mode .alignment-list {{ max-height: 480px; }}

    .segment-card {{
      text-align: left;
      width: 100%;
      border: 1px solid var(--border);
      background: var(--bg);
      padding: 11px 12px;
      color: var(--fg);
      cursor: pointer;
      transition: border-color var(--speed), background var(--speed);
    }}
    .segment-card:hover {{ border-color: var(--accent); }}
    .segment-card.active {{
      background: rgba(90,138,122,0.08);
      border-color: var(--accent);
    }}
    .segment-card.low-confidence {{ border-style: dashed; border-color: var(--muted-2); }}

    .segment-top {{
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: baseline;
      margin-bottom: 5px;
    }}
    .segment-title {{ font-weight: 600; color: var(--fg-bright); font-size: 0.88rem; }}
    .segment-time {{
      flex: 0 0 auto;
      color: var(--muted);
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.7rem;
    }}
    .segment-script {{
      margin: 0;
      color: var(--muted);
      line-height: 1.5;
      font-size: 0.85rem;
    }}
    .segment-intent {{
      margin-top: 6px;
      color: var(--muted-2);
      font-size: 0.76rem;
      line-height: 1.4;
    }}

    .foot {{
      margin-top: 2px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.72rem;
      color: var(--muted-2);
      text-align: right;
    }}
    .foot b {{ color: var(--accent-3); }}

    /* ── 8x8 pixel icon (CSS grid) ── */
    .pixel-icon {{
      width: 20px;
      height: 20px;
      display: grid;
      grid-template-columns: repeat(8, 1fr);
      grid-template-rows: repeat(8, 1fr);
      gap: 0;
      flex-shrink: 0;
    }}
    .pixel-icon .p {{ background: var(--fg); }}

    /* ── Header bar ── */
    .top-bar {{
      position: relative;
      z-index: 1;
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 16px 32px;
      border-bottom: 1px solid var(--border);
    }}
    .top-bar h1 {{
      font-size: 1.1rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      color: var(--fg-bright);
    }}
    .top-bar .status {{
      margin-left: auto;
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 0.78rem;
      color: var(--muted);
    }}
    .status-dot {{
      width: 7px;
      height: 7px;
      background: var(--accent);
      box-shadow: 0 0 3px var(--accent);
    }}

    /* ── Responsive ── */
    @media (max-width: 1020px) {{
      .shell {{
        grid-template-columns: 1fr;
        width: min(720px, 94vw);
      }}
      body.learning-mode .shell {{
        grid-template-columns: 1fr;
        width: min(860px, 94vw);
      }}
      .lesson-pair {{ grid-template-columns: 1fr; }}
      body.learning-mode .lesson-pair {{ grid-template-columns: 1fr; }}
      .alignment-list {{ max-height: none; }}
    }}

    @media (max-width: 720px) {{
      .row {{ grid-template-columns: 1fr; }}
      .shell {{ margin: 16px auto 24px; }}
      .hero, .form-wrap, .result-head, .result-wrap {{ padding-left: 16px; padding-right: 16px; }}
      .result-title-row {{ display: grid; }}
      .result-actions {{ justify-content: flex-start; }}
      .top-bar {{ padding: 12px 16px; }}
    }}

    @keyframes shell-in {{
      from {{ opacity: 0; transform: translateY(14px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}
    @keyframes field-in {{
      from {{ opacity: 0; transform: translateY(6px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}
    @keyframes panel-up {{
      from {{ opacity: 0; transform: translateY(6px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}
    @keyframes pulse-dot {{
      0%, 100% {{ opacity: 0.6; }}
      50% {{ opacity: 1; }}
    }}

  </style>
</head>
<body>
  <main class="shell">
    <section class="panel">
      <header class="hero">
        <h1>Aegis Studio Web</h1>
        <p>用你的 Key + 自然语言问题，把抽象知识直接变成动态可视化视频。</p>
        <small>Secure by design: API Key 仅用于本次请求，不落盘到仓库。</small>
      </header>

      <form id="generate-form" class="form-wrap">
        <div class="field">
          <label for="provider">模型服务</label>
          <select id="provider" name="provider"></select>
          <div class="provider-meta">
            <span id="providerRegion" class="provider-pill">-</span>
            <span id="providerProtocol" class="provider-pill">-</span>
            <a id="providerDoc" class="provider-doc hidden" href="#" target="_blank" rel="noreferrer">文档</a>
          </div>
          <div id="providerHelp" class="help">支持智谱、OpenAI-Compatible、本地 Codex 代理、MiniMax Token/Coding Plan。</div>
        </div>

        <div id="apiKeyField" class="field">
          <label id="apiKeyLabel" for="apiKey">API Key</label>
          <div class="key-row">
            <input id="apiKey" name="apiKey" type="password" placeholder="输入你自己的 API Key" />
            <button id="toggleKey" class="tiny-btn" type="button">显示</button>
          </div>
          <div id="apiKeyHelp" class="help">Key 仅用于本次请求，不写入仓库；本地代理如果不需要鉴权可以留空。</div>
        </div>

        <div class="field">
          <label for="prompt">你要讲清楚的问题</label>
          <textarea id="prompt" name="prompt" placeholder="例如：我不理解税收楔子如何导致无谓损失，请做动态演示并给出关键结论。" required></textarea>
          <div id="promptPreview" class="prompt-preview">
            <span class="prompt-preview-label">公式预览</span>
            <div id="promptPreviewContent" class="rich-text"></div>
          </div>
        </div>

        <div class="row">
          <div class="field">
            <label for="model">模型</label>
            <input id="model" name="model" value="{DEFAULT_MODEL}" />
          </div>
          <div class="field">
            <label for="sceneName">场景类名</label>
            <input id="sceneName" name="sceneName" value="GeneratedScene" />
          </div>
        </div>

        <div class="row">
          <div class="field">
            <label for="temperature">Temperature (0-1)</label>
            <input id="temperature" name="temperature" type="number" min="0" max="1" step="0.1" value="0.2" />
          </div>
          <div id="baseUrlField" class="field">
            <label for="baseUrl">Base URL</label>
            <input id="baseUrl" name="baseUrl" value="{DEFAULT_ZHIPU_ENDPOINT}" />
            <div class="help">填根地址即可；如果粘贴 /chat/completions 或 /messages，后端会自动规范化。</div>
          </div>
        </div>

        <label class="check-row" for="noRender">
          <input id="noRender" name="noRender" type="checkbox" />
          只生成代码，不渲染视频（调试模式）
        </label>

        <button id="submitBtn" class="btn" type="submit">Generate & Render</button>
        <div id="processPanel" class="process-panel">
          <div class="process-head">
            <span id="processMessage">正在准备任务...</span>
            <span id="processTime" class="process-time">0s</span>
          </div>
          <div class="process-steps">
            <div class="process-step" data-stage="0"><span class="process-dot"></span><span>生成 Manim 教学代码</span></div>
            <div class="process-step" data-stage="1"><span class="process-dot"></span><span>渲染动画并检查兼容性</span></div>
            <div class="process-step" data-stage="2"><span class="process-dot"></span><span>失败时自动带错误重写代码</span></div>
            <div class="process-step" data-stage="3"><span class="process-dot"></span><span>生成同步讲稿，可在视频完成后增强对齐</span></div>
          </div>
          <div id="processFeed" class="process-feed"></div>
          <details id="techDetails" class="tech-details">
            <summary>技术细节</summary>
            <pre id="techLog" class="tech-log"></pre>
          </details>
        </div>
        <div id="statusBox" class="status-box">等待输入...</div>
      </form>
    </section>

    <section class="panel">
      <header class="result-head">
        <div class="result-title-row">
          <div>
            <h2>结果面板</h2>
            <p>生成后自动切换为视频与讲稿优先的学习视图。</p>
          </div>
          <div class="result-actions">
            <button id="editAgainBtn" class="ghost-btn" type="button">返回编辑</button>
            <button id="toggleCodeBtn" class="ghost-btn" type="button">查看代码</button>
          </div>
        </div>
      </header>

      <div class="result-wrap">
        <div class="tag-wrap">
          <span id="sceneTag" class="tag">Scene: -</span>
          <span id="fileTag" class="tag">File: -</span>
          <span id="requestTag" class="tag">Req: -</span>
          <span class="tag">Version: {APP_VERSION}</span>
        </div>

        <div id="warningBox" class="warning-box"></div>

        <section class="code-section">
          <div class="code-header">
            <span>Generated Python</span>
            <button id="copyCodeBtn" class="ghost-btn" type="button">复制代码</button>
          </div>

          <pre id="codeOutput"># 生成的 Manim 代码会显示在这里</pre>
        </section>

        <div class="lesson-pair">
          <div id="videoCard" class="video-card">
            <video id="videoPlayer" controls preload="metadata"></video>
          </div>

          <section id="alignmentPanel" class="alignment-panel">
            <div class="alignment-head">
              <div>
                <h3>同步讲稿</h3>
                <div id="alignmentSummary" class="alignment-summary">等待渲染完成后生成段落对齐。</div>
              </div>
              <button id="realignBtn" class="ghost-btn" type="button" disabled>重新对齐讲稿</button>
            </div>
            <div id="alignmentWarning" class="alignment-warning"></div>
            <div id="alignmentList" class="alignment-list"></div>
          </section>
        </div>

        <div class="foot">诊断入口：<b>/api/health</b> 与 <b>/api/bugs/recent?limit=20</b></div>
      </div>
    </section>
  </main>

  <script>
    const PROVIDER_CONFIG = {provider_config_json};
    const PROVIDERS = PROVIDER_CONFIG.providers || {{}};
    const REGION_LABELS = PROVIDER_CONFIG.regionLabels || {{}};
    const form = document.getElementById("generate-form");
    const submitBtn = document.getElementById("submitBtn");
    const statusBox = document.getElementById("statusBox");
    const codeOutput = document.getElementById("codeOutput");
    const sceneTag = document.getElementById("sceneTag");
    const fileTag = document.getElementById("fileTag");
    const requestTag = document.getElementById("requestTag");
    const videoCard = document.getElementById("videoCard");
    const videoPlayer = document.getElementById("videoPlayer");
    const toggleKey = document.getElementById("toggleKey");
    const apiKeyInput = document.getElementById("apiKey");
    const apiKeyField = document.getElementById("apiKeyField");
    const warningBox = document.getElementById("warningBox");
    const copyCodeBtn = document.getElementById("copyCodeBtn");
    const editAgainBtn = document.getElementById("editAgainBtn");
    const toggleCodeBtn = document.getElementById("toggleCodeBtn");
    const providerSelect = document.getElementById("provider");
    const providerRegion = document.getElementById("providerRegion");
    const providerProtocol = document.getElementById("providerProtocol");
    const providerDoc = document.getElementById("providerDoc");
    const providerHelp = document.getElementById("providerHelp");
    const apiKeyLabel = document.getElementById("apiKeyLabel");
    const apiKeyHelp = document.getElementById("apiKeyHelp");
    const modelInput = document.getElementById("model");
    const baseUrlInput = document.getElementById("baseUrl");
    const baseUrlField = document.getElementById("baseUrlField");
    const processPanel = document.getElementById("processPanel");
    const processMessage = document.getElementById("processMessage");
    const processTime = document.getElementById("processTime");
    const processSteps = Array.from(document.querySelectorAll(".process-step"));
    const processFeed = document.getElementById("processFeed");
    const techLog = document.getElementById("techLog");
    const alignmentPanel = document.getElementById("alignmentPanel");
    const alignmentSummary = document.getElementById("alignmentSummary");
    const alignmentWarning = document.getElementById("alignmentWarning");
    const alignmentList = document.getElementById("alignmentList");
    const realignBtn = document.getElementById("realignBtn");
    const promptInput = document.getElementById("prompt");
    const promptPreview = document.getElementById("promptPreview");
    const promptPreviewContent = document.getElementById("promptPreviewContent");

    let currentAlignment = null;
    let latestPrompt = "";
    let latestCode = "";
    let latestSceneName = "GeneratedScene";
    let latestProviderPayload = null;
    let processStartedAt = 0;
    let processTimer = null;

    function groupProviderIds() {{
      const groups = {{}};
      Object.entries(PROVIDERS).forEach(([id, preset]) => {{
        const region = preset.region || "custom";
        if (!groups[region]) groups[region] = [];
        groups[region].push(id);
      }});
      return groups;
    }}

    function renderProviderOptions() {{
      providerSelect.replaceChildren();
      const groups = groupProviderIds();
      ["trial", "global", "cn", "coding", "local", "custom"].forEach((region) => {{
        const ids = groups[region] || [];
        if (!ids.length) return;
        const optgroup = document.createElement("optgroup");
        optgroup.label = REGION_LABELS[region] || region;
        ids.forEach((id) => {{
          const option = document.createElement("option");
          option.value = id;
          option.textContent = PROVIDERS[id].name || id;
          optgroup.appendChild(option);
        }});
        providerSelect.appendChild(optgroup);
      }});
      const providerStorageKey = PROVIDER_CONFIG.providerStorageKey || "aegis.provider";
      providerSelect.value = localStorage.getItem(providerStorageKey) || PROVIDER_CONFIG.defaultProvider || "{DEFAULT_PROVIDER}";
      if (!PROVIDERS[providerSelect.value]) {{
        providerSelect.value = PROVIDER_CONFIG.defaultProvider || "{DEFAULT_PROVIDER}";
      }}
    }}

    function activePreset() {{
      return PROVIDERS[providerSelect.value] || PROVIDERS[PROVIDER_CONFIG.defaultProvider] || {{}};
    }}

    function updateProviderUI(keepModel = false) {{
      const preset = activePreset();
      providerRegion.textContent = REGION_LABELS[preset.region] || preset.region || "Provider";
      providerProtocol.textContent = preset.displayProtocol || preset.apiType || "-";
      providerDoc.href = preset.doc || "#";
      providerDoc.classList.toggle("hidden", !preset.doc);
      providerHelp.textContent = preset.description || `${{preset.name || providerSelect.value}} · ${{preset.apiType || "compatible"}} · 模型 ID 可手动改写。`;
      apiKeyLabel.textContent = `${{preset.name || "Provider"}} API Key`;
      apiKeyInput.placeholder = preset.apiKeyPlaceholder || "API Key...";
      apiKeyInput.required = Boolean(preset.requiresApiKey);
      const usesCodexCli = preset.apiType === "codex-cli";
      const serverManaged = Boolean(preset.serverManaged);
      const cloudUnavailable = Boolean(preset.cloudUnavailable);
      apiKeyField.style.display = (usesCodexCli || serverManaged || preset.hideApiKey) ? "none" : "";
      baseUrlField.style.display = (usesCodexCli || serverManaged || preset.hideBaseUrl) ? "none" : "";
      modelInput.readOnly = Boolean(preset.lockModel);
      if (cloudUnavailable) {{
        providerHelp.textContent = `${{preset.name || providerSelect.value}} · 仅本地可执行 · 下载项目后可用。`;
        apiKeyHelp.textContent = "这个 Provider 是下载项目后在本地 Aegis Web 使用的选项；Vercel 云端只展示能力入口。";
      }} else if (serverManaged) {{
        apiKeyHelp.textContent = "内测阶段由 Aegis 承担模型调用额度；页面不会接收或保存你的模型 Key。";
      }} else {{
        apiKeyHelp.textContent = preset.requiresApiKey
          ? "Key 仅用于本次请求，不落盘；如果报 401，请确认 Key 未过期且有可用额度。"
          : usesCodexCli
            ? "使用本机 codex login 登录态，不需要在页面粘贴 API Key。"
            : "这个 Provider 允许无 Key，例如本地代理；如网关要求鉴权，也可以填写。";
      }}

      const savedBaseUrl = localStorage.getItem(`aegis.baseUrl.${{providerSelect.value}}`);
      baseUrlInput.value = (usesCodexCli || serverManaged) ? "" : savedBaseUrl || preset.baseURL || "";
      baseUrlInput.placeholder = preset.baseURL || "https://api.example.com/v1";

      const savedModel = localStorage.getItem(`aegis.model.${{providerSelect.value}}`);
      if (!keepModel || !modelInput.value.trim()) {{
        modelInput.value = serverManaged ? preset.defaultModel || "" : savedModel || preset.defaultModel || "";
      }}
    }}

    providerSelect.addEventListener("change", () => {{
      const providerStorageKey = PROVIDER_CONFIG.providerStorageKey || "aegis.provider";
      localStorage.setItem(providerStorageKey, providerSelect.value);
      updateProviderUI(false);
    }});

    function setStatus(message, type = "") {{
      statusBox.className = "status-box" + (type ? " " + type : "");
      statusBox.textContent = message;
    }}

    function textHasRichSyntax(text) {{
      return /(\\$\\$[\\s\\S]+?\\$\\$|\\\\\\[[\\s\\S]+?\\\\\\]|\\\\\\([\\s\\S]+?\\\\\\)|\\$[^$\\n]+\\$|\\*\\*[^*]+\\*\\*|`[^`]+`|^\\s*#{{1,4}}\\s+)/m.test(text || "");
    }}

    function isDisplayMath(token) {{
      return token.startsWith("$$") || token.startsWith("\\\\[");
    }}

    function appendMarkdownInline(target, text) {{
      const pattern = /(\\*\\*[^*]+\\*\\*|`[^`]+`)/g;
      let cursor = 0;
      let match;
      while ((match = pattern.exec(text)) !== null) {{
        if (match.index > cursor) {{
          target.appendChild(document.createTextNode(text.slice(cursor, match.index)));
        }}
        const token = match[0];
        const node = document.createElement(token.startsWith("`") ? "code" : "strong");
        node.textContent = token.slice(token.startsWith("`") ? 1 : 2, token.startsWith("`") ? -1 : -2);
        target.appendChild(node);
        cursor = pattern.lastIndex;
      }}
      if (cursor < text.length) {{
        target.appendChild(document.createTextNode(text.slice(cursor)));
      }}
    }}

    function appendRichLine(target, line) {{
      const cleaned = line.replace(/^\\s*#{{1,4}}\\s+/, "").replace(/^\\s*[-*]\\s+/, "• ");
      const mathPattern = /(\\$\\$[\\s\\S]+?\\$\\$|\\\\\\[[\\s\\S]+?\\\\\\]|\\\\\\([\\s\\S]+?\\\\\\)|\\$[^$\\n]+\\$)/g;
      let cursor = 0;
      let match;
      while ((match = mathPattern.exec(cleaned)) !== null) {{
        if (match.index > cursor) {{
          appendMarkdownInline(target, cleaned.slice(cursor, match.index));
        }}
        const token = match[0];
        const math = document.createElement(isDisplayMath(token) ? "div" : "span");
        math.className = isDisplayMath(token) ? "math-block" : "math-inline";
        math.textContent = token;
        target.appendChild(math);
        cursor = mathPattern.lastIndex;
      }}
      if (cursor < cleaned.length) {{
        appendMarkdownInline(target, cleaned.slice(cursor));
      }}
    }}

    function renderRichText(target, rawText, fallback = "") {{
      target.replaceChildren();
      target.classList.add("rich-text");
      const text = String(rawText || fallback || "").trim();
      if (!text) return;
      const lines = text.split(/\\n+/);
      lines.forEach((line, index) => {{
        if (index > 0) target.appendChild(document.createElement("br"));
        appendRichLine(target, line);
      }});
      if (window.MathJax && window.MathJax.typesetPromise) {{
        window.MathJax.typesetPromise([target]).catch(() => undefined);
      }}
    }}

    function updatePromptPreview() {{
      const text = promptInput.value || "";
      if (!textHasRichSyntax(text)) {{
        promptPreview.classList.remove("visible");
        promptPreviewContent.replaceChildren();
        return;
      }}
      promptPreview.classList.add("visible");
      renderRichText(promptPreviewContent, text);
    }}

    function setProcessStage(stageIndex) {{
      processSteps.forEach((step, index) => {{
        step.classList.toggle("done", index < stageIndex);
        step.classList.toggle("active", index === stageIndex);
      }});
    }}

    function updateProcess() {{
      if (!processStartedAt) return;
      const elapsed = Math.floor((Date.now() - processStartedAt) / 1000);
      processTime.textContent = `${{elapsed}}s`;
      if (elapsed < 45) {{
        setProcessStage(0);
        processMessage.textContent = "模型正在把你的问题转成 Manim 场景代码。";
      }} else if (elapsed < 150) {{
        setProcessStage(1);
        processMessage.textContent = "代码已进入渲染阶段；复杂图形可能需要几分钟。";
      }} else if (elapsed < 260) {{
        setProcessStage(2);
        processMessage.textContent = "如果渲染失败，后端会把错误反馈给模型并自动重写。";
      }} else {{
        setProcessStage(3);
        processMessage.textContent = "仍在处理长任务；页面会在后端完成后更新结果。";
      }}
    }}

    function startProcess() {{
      processStartedAt = Date.now();
      processPanel.classList.add("visible");
      updateProcess();
      if (processTimer) window.clearInterval(processTimer);
      processTimer = window.setInterval(updateProcess, 1000);
    }}

    function stopProcess() {{
      if (processTimer) {{
        window.clearInterval(processTimer);
        processTimer = null;
      }}
      processStartedAt = 0;
      processPanel.classList.remove("visible");
      processSteps.forEach((step) => step.classList.remove("active", "done"));
    }}

    function resetProcessDetails() {{
      processFeed.replaceChildren();
      techLog.textContent = "";
    }}

    function enterLearningMode() {{
      document.body.classList.add("learning-mode");
      document.body.classList.remove("show-code");
      toggleCodeBtn.textContent = "查看代码";
    }}

    function exitLearningMode() {{
      document.body.classList.remove("learning-mode", "show-code");
      toggleCodeBtn.textContent = "查看代码";
      form.scrollIntoView({{ behavior: "smooth", block: "start" }});
    }}

    function stageIndexFor(stage) {{
      if (stage === "brief" || stage === "model" || stage === "precheck" || stage === "validation" || stage === "queued") return 0;
      if (stage === "render") return 1;
      if (stage === "repair" || stage === "failed") return 2;
      if (stage === "alignment" || stage === "complete") return 3;
      return 0;
    }}

    function renderJobSnapshot(job) {{
      if (!job) return;
      processPanel.classList.add("visible");
      setProcessStage(stageIndexFor(job.stage));
      if (job.currentStudentMessage) {{
        processMessage.textContent = job.currentStudentMessage;
      }}
      const events = Array.isArray(job.events) ? job.events.slice(-8) : [];
      processFeed.replaceChildren();
      events.forEach((event) => {{
        const item = document.createElement("div");
        item.className = "process-feed-item" + (event.severity === "warn" || event.severity === "error" ? " warn" : "");
        const attempt = event.attempt ? `第 ${{event.attempt}} 次 · ` : "";
        item.textContent = attempt + (event.studentMessage || event.stage || "处理中");
        processFeed.appendChild(item);
      }});
      const technical = Array.isArray(job.technicalEvents) ? job.technicalEvents.slice(-12) : [];
      techLog.textContent = technical.map((event) => {{
        const attempt = event.attempt ? ` attempt=${{event.attempt}}` : "";
        return `[${{event.time || ""}}] ${{event.stage || "event"}}${{attempt}} ${{event.technicalMessage || ""}}`;
      }}).join("\\n");
    }}

    // Auto-render configuration
    const RENDER_BACKEND_URL = "{os.environ.get('RENDER_BACKEND_URL', 'http://localhost:5001')}";

    async function startAutoRender(code, sceneName) {{
      if (!code) return;
      setStatus("代码已生成，正在提交渲染任务...", "");
      const renderPayload = {{ code, scene_name: sceneName }};
      let renderResponse = null;
      let renderData = null;

      // Try local render backend first
      try {{
        const localResp = await fetch(`${{RENDER_BACKEND_URL}}/render-async`, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json", "X-API-Key": "dev-key-change-in-production" }},
          body: JSON.stringify(renderPayload)
        }});
        if (localResp.ok) {{
          renderResponse = localResp;
          renderData = await localResp.json();
        }}
      }} catch (e) {{
        // Local backend not available, try via current API proxy
      }}

      // Fallback to /api/render (Vercel proxy or local web_app proxy)
      if (!renderResponse) {{
        try {{
          const proxyResp = await fetch("/api/render", {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{ code, sceneName }})
          }});
          renderResponse = proxyResp;
          renderData = await proxyResp.json();
        }} catch (e) {{
          setStatus("渲染后端连接失败，已生成代码但无法渲染视频。", "warn");
          return;
        }}
      }}

      if (!renderResponse.ok || !renderData || renderData.error) {{
        const err = (renderData && renderData.error) || "渲染任务提交失败";
        setStatus("渲染提交失败: " + err, "error");
        return;
      }}

      const jobId = renderData.job_id;
      const statusUrl = renderData.status_url || `/status/${{jobId}}`;
      const downloadUrl = renderData.download_url || `/download/${{jobId}}`;
      setStatus(`渲染任务已创建 (ID: ${{jobId.slice(0,8)}})，正在渲染视频...`, "");

      // Poll render status
      for (let i = 0; i < 300; i++) {{
        await new Promise(r => setTimeout(r, 2000));
        let statusResp;
        try {{
          statusResp = await fetch(`${{RENDER_BACKEND_URL}}${{statusUrl}}`, {{
            headers: {{ "X-API-Key": "dev-key-change-in-production" }}
          }});
        }} catch (e) {{
          try {{
            statusResp = await fetch(`/api/render/status/${{jobId}}`);
          }} catch (e2) {{
            continue;
          }}
        }}
        if (!statusResp.ok) continue;
        const statusData = await statusResp.json();
        if (statusData.status === "done" || statusData.status === "completed") {{
          // Try to get video URL
          let videoUrl = null;
          if (statusData.video_url) {{
            videoUrl = statusData.video_url;
          }} else if (statusData.download_url) {{
            videoUrl = `/api/render/download/${{jobId}}`;
          }} else {{
            // Fallback: try gateway download endpoint directly
            try {{
              const dlResp = await fetch(`/api/render/download/${{jobId}}`);
              if (dlResp.ok) {{
                videoUrl = `/api/render/download/${{jobId}}`;
              }}
            }} catch (e) {{}}
          }}
          if (videoUrl) {{
            videoPlayer.src = videoUrl;
            videoCard.classList.add("visible");
            enterLearningMode();
            setStatus("视频渲染完成！", "success");
          }} else {{
            setStatus("渲染完成，但无法获取视频地址。", "warn");
          }}
          return;
        }}
        if (statusData.status === "failed" || statusData.status === "error") {{
          const errMsg = statusData.error || statusData.error_message || "渲染失败";
          setStatus("渲染失败: " + errMsg, "error");
          if (statusData.stderr) {{
            console.error("Render stderr:", statusData.stderr);
          }}
          return;
        }}
      }}
      setStatus("渲染超时，请稍后手动刷新检查。", "warn");
    }}

    function applyGenerateResult(data, payload, requestId) {{
      codeOutput.textContent = data.code || "# 未返回代码";
      latestCode = data.code || "";
      latestSceneName = data.sceneName || payload.sceneName || "GeneratedScene";
      sceneTag.textContent = "Scene: " + (data.sceneName || "-");
      fileTag.textContent = "File: " + (data.codeFile || "-");
      if (data.providerName) {{
        sceneTag.textContent += " · " + data.providerName;
      }}
      setWarnings(data.warnings || []);

      if (data.videoId) {{
        videoPlayer.src = "/api/video/" + data.videoId;
        videoCard.classList.add("visible");
        enterLearningMode();
        if (data.alignment) {{
          setAlignment(data.alignment);
        }} else {{
          clearAlignment();
        }}
      }} else {{
        clearAlignment();
      }}

      const warningText = Array.isArray(data.warnings) && data.warnings.length
        ? " | 已自动做兼容修复"
        : "";
      const reqText = requestId && requestId !== "-" ? " | 诊断ID: " + requestId : "";
      setStatus((data.message || "处理完成") + warningText + reqText, "success");

      // Auto-trigger render if code was generated and noRender is not checked
      if (latestCode && !payload.noRender && !data.videoId) {{
        startAutoRender(latestCode, latestSceneName);
      }}
    }}

    async function waitForJob(statusUrl, payload) {{
      while (true) {{
        const response = await fetch(statusUrl, {{ cache: "no-store" }});
        const job = await response.json();
        if (!response.ok || !job.ok) {{
          throw new Error(job.error || "无法读取任务状态");
        }}
        renderJobSnapshot(job);
        requestTag.textContent = "Req: " + (job.requestId || job.jobId || "-");
        if (job.status === "succeeded") {{
          applyGenerateResult(job.result || {{}}, payload, job.requestId || job.jobId || "-");
          return;
        }}
        if (job.status === "failed") {{
          const err = job.error || {{}};
          codeOutput.textContent = err.code || codeOutput.textContent || "# 这次没有可用代码";
          if (err.code) latestCode = err.code;
          if (err.sceneName) latestSceneName = err.sceneName;
          setWarnings(err.warnings || []);
          const detail = err.studentMessage || job.currentStudentMessage || err.detail || err.error || "任务失败";
          throw new Error(detail + " | 诊断ID: " + (job.requestId || job.jobId || "-"));
        }}
        await new Promise((resolve) => setTimeout(resolve, 1200));
      }}
    }}

    function setWarnings(warnings) {{
      if (Array.isArray(warnings) && warnings.length) {{
        warningBox.textContent = "自动兼容修复: " + warnings.join(" ; ");
        warningBox.classList.add("visible");
      }} else {{
        warningBox.textContent = "";
        warningBox.classList.remove("visible");
      }}
    }}

    function formatTime(value) {{
      const seconds = Number(value || 0);
      const minutes = Math.floor(seconds / 60);
      const rest = Math.max(0, seconds - minutes * 60);
      return `${{minutes}}:${{rest.toFixed(1).padStart(4, "0")}}`;
    }}

    function clearAlignment() {{
      currentAlignment = null;
      alignmentPanel.classList.remove("visible");
      alignmentSummary.textContent = "等待渲染完成后生成段落对齐。";
      alignmentWarning.textContent = "";
      alignmentWarning.classList.remove("visible");
      alignmentList.replaceChildren();
      realignBtn.disabled = !latestCode;
    }}

    function findActiveSegment(currentTime) {{
      if (!currentAlignment || !Array.isArray(currentAlignment.segments)) return null;
      return currentAlignment.segments.find((segment) => {{
        return Number(segment.startTime) <= currentTime && currentTime < Number(segment.endTime);
      }}) || currentAlignment.segments[currentAlignment.segments.length - 1] || null;
    }}

    function updateActiveSegment() {{
      const active = findActiveSegment(videoPlayer.currentTime || 0);
      Array.from(alignmentList.children).forEach((node) => {{
        node.classList.toggle("active", Boolean(active) && node.dataset.segmentId === active.id);
      }});
    }}

    function seekToSegment(segment) {{
      if (!segment) return;
      videoPlayer.currentTime = Math.max(0, Number(segment.startTime) || 0);
      updateActiveSegment();
    }}

    function renderAlignment() {{
      alignmentList.replaceChildren();
      const segments = Array.isArray(currentAlignment && currentAlignment.segments)
        ? currentAlignment.segments
        : [];
      segments.forEach((segment) => {{
        const card = document.createElement("button");
        card.type = "button";
        card.className = "segment-card";
        card.dataset.segmentId = segment.id;
        if (segment.confidence === "low") {{
          card.classList.add("low-confidence");
        }}

        const top = document.createElement("div");
        top.className = "segment-top";
        const title = document.createElement("span");
        title.className = "segment-title";
        title.textContent = segment.title || "教学段落";
        const time = document.createElement("span");
        time.className = "segment-time";
        time.textContent = `${{formatTime(segment.startTime)}} - ${{formatTime(segment.endTime)}}`;
        top.append(title, time);

        const script = document.createElement("p");
        script.className = "segment-script";
        renderRichText(script, segment.script, "这一段解释当前画面背后的概念含义。");

        const intent = document.createElement("div");
        intent.className = "segment-intent";
        if (segment.visualIntent) {{
          intent.appendChild(document.createTextNode("视觉对应："));
          const intentText = document.createElement("span");
          renderRichText(intentText, segment.visualIntent);
          intent.appendChild(intentText);
        }}

        card.append(top, script, intent);
        card.addEventListener("click", () => seekToSegment(segment));
        alignmentList.appendChild(card);
      }});
      updateActiveSegment();
    }}

    function setAlignment(alignment) {{
      currentAlignment = alignment || null;
      if (!currentAlignment) {{
        clearAlignment();
        return;
      }}

      const segments = Array.isArray(currentAlignment.segments) ? currentAlignment.segments : [];
      const confidence = currentAlignment.confidence || "medium";
      alignmentPanel.classList.add("visible");
      alignmentSummary.textContent = `段落数：${{segments.length}} · 置信度：${{confidence}} · 点击段落可跳转视频`;
      const warnings = Array.isArray(currentAlignment.warnings) ? currentAlignment.warnings.filter(Boolean) : [];
      if (warnings.length) {{
        alignmentWarning.textContent = warnings.join(" ; ");
        alignmentWarning.classList.add("visible");
      }} else {{
        alignmentWarning.textContent = "";
        alignmentWarning.classList.remove("visible");
      }}
      realignBtn.disabled = !latestCode;
      renderAlignment();
    }}

    toggleKey.addEventListener("click", () => {{
      apiKeyInput.type = apiKeyInput.type === "password" ? "text" : "password";
      toggleKey.textContent = apiKeyInput.type === "password" ? "显示" : "隐藏";
    }});

    copyCodeBtn.addEventListener("click", async () => {{
      try {{
        await navigator.clipboard.writeText(codeOutput.textContent || "");
        copyCodeBtn.textContent = "已复制";
        setTimeout(() => (copyCodeBtn.textContent = "复制代码"), 1200);
      }} catch (_e) {{
        copyCodeBtn.textContent = "复制失败";
        setTimeout(() => (copyCodeBtn.textContent = "复制代码"), 1200);
      }}
    }});

    editAgainBtn.addEventListener("click", exitLearningMode);

    toggleCodeBtn.addEventListener("click", () => {{
      const showing = document.body.classList.toggle("show-code");
      toggleCodeBtn.textContent = showing ? "隐藏代码" : "查看代码";
    }});

    form.addEventListener("submit", async (event) => {{
      event.preventDefault();
      const preset = activePreset();
      if (preset.cloudUnavailable) {{
        setStatus("这个 Provider 需要下载项目后在本地运行；Vercel 云端无法访问你的本机 Codex 或 127.0.0.1 服务。", "error");
        return;
      }}
      submitBtn.disabled = true;
      document.body.classList.remove("learning-mode", "show-code");
      toggleCodeBtn.textContent = "查看代码";
      setStatus("请求已发送，正在生成代码...", "");
      startProcess();
      resetProcessDetails();
      setWarnings([]);
      latestPrompt = "";
      latestCode = "";
      latestSceneName = "GeneratedScene";
      latestProviderPayload = null;
      requestTag.textContent = "Req: -";
      videoCard.classList.remove("visible");
      videoPlayer.removeAttribute("src");
      videoPlayer.load();
      clearAlignment();

      const payload = {{
        provider: providerSelect.value,
        apiKey: preset.serverManaged ? "" : apiKeyInput.value.trim(),
        prompt: promptInput.value.trim(),
        model: modelInput.value.trim() || activePreset().defaultModel || "{DEFAULT_MODEL}",
        baseUrl: preset.serverManaged ? "" : baseUrlInput.value.trim(),
        endpoint: preset.serverManaged ? "" : baseUrlInput.value.trim(),
        sceneName: document.getElementById("sceneName").value.trim() || "GeneratedScene",
        temperature: Number(document.getElementById("temperature").value || 0.2),
        noRender: document.getElementById("noRender").checked
      }};
      latestPrompt = payload.prompt;
      latestSceneName = payload.sceneName;
      latestProviderPayload = {{ ...payload }};
      if (!preset.serverManaged) {{
        localStorage.setItem(`aegis.model.${{payload.provider}}`, payload.model);
        localStorage.setItem(`aegis.baseUrl.${{payload.provider}}`, payload.baseUrl);
      }}

      try {{
        const response = await fetch("/api/generate/start", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify(payload)
        }});
        const data = await response.json();
        if (!response.ok || !data.ok) {{
          const detail = data.detail ? " | " + data.detail : "";
          const reqText = data.requestId ? " | 诊断ID: " + data.requestId : "";
          throw new Error((data.error || "请求失败") + detail + reqText);
        }}
        requestTag.textContent = "Req: " + (data.requestId || data.jobId || "-");
        await waitForJob(data.statusUrl, payload);
      }} catch (err) {{
        setStatus(err && err.message ? err.message : "请求异常", "error");
      }} finally {{
        submitBtn.disabled = false;
      }}
    }});

    videoPlayer.addEventListener("timeupdate", updateActiveSegment);
    videoPlayer.addEventListener("loadedmetadata", updateActiveSegment);
    promptInput.addEventListener("input", updatePromptPreview);

    realignBtn.addEventListener("click", async () => {{
      if (!latestPrompt || !latestCode || !latestProviderPayload) return;
      realignBtn.disabled = true;
      const previousText = realignBtn.textContent;
      realignBtn.textContent = "对齐中...";
      try {{
        const payload = {{
          ...latestProviderPayload,
          prompt: latestPrompt,
          code: latestCode,
          sceneName: latestSceneName,
          videoDuration: Number.isFinite(videoPlayer.duration) ? videoPlayer.duration : null
        }};
        const response = await fetch("/api/align", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify(payload)
        }});
        const data = await response.json();
        if (!response.ok || !data.ok) {{
          throw new Error(data.error || "重新对齐失败");
        }}
        setAlignment(data.alignment);
        setStatus("讲稿已重新对齐。", "success");
      }} catch (err) {{
        setStatus(err && err.message ? err.message : "重新对齐失败", "error");
      }} finally {{
        realignBtn.textContent = previousText;
        realignBtn.disabled = !latestCode;
      }}
    }});

    renderProviderOptions();
    updateProviderUI(false);
    updatePromptPreview();
  </script>
</body>
</html>
"""


class AegisWebHandler(BaseHTTPRequestHandler):
    server_version = "AegisWeb/0.1"

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError) as exc:
            append_runtime_log("CLIENT_DISCONNECT", f"json_response status={status} error={exc}")

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict[str, Any]:
        raw_len = self.headers.get("Content-Length", "0")
        try:
            body_len = int(raw_len)
        except ValueError as exc:
            raise ValueError("Invalid Content-Length.") from exc
        if body_len <= 0:
            raise ValueError("Empty request body.")
        raw = self.rfile.read(body_len)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("Body must be valid JSON.") from exc

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path

        if route == "/":
            self._send_html(make_index_html())
            return

        if route == "/api/health":
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "time": datetime.now().isoformat(timespec="seconds"),
                    "version": APP_VERSION,
                },
            )
            return

        if route.startswith("/api/jobs/"):
            job_id = route.rsplit("/", 1)[-1]
            snapshot = job_snapshot(job_id)
            if snapshot is None:
                self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Job not found."})
                return
            self._send_json(HTTPStatus.OK, snapshot)
            return

        if route == "/api/bugs/recent":
            query = parse_qs(parsed.query)
            limit_raw = query.get("limit", ["20"])[0]
            request_id = query.get("requestId", [""])[0].strip()
            try:
                limit = int(limit_raw)
            except ValueError:
                limit = 20
            limit = max(1, min(200, limit))
            items = read_recent_bug_entries(limit, request_id=request_id or None)
            self._send_json(HTTPStatus.OK, {"ok": True, "count": len(items), "items": items})
            return

        if route.startswith("/api/video/"):
            video_id = route.rsplit("/", 1)[-1]
            with VIDEO_CACHE_LOCK:
                video_path = VIDEO_CACHE.get(video_id)
            if not video_path or not video_path.exists():
                self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Video not found."})
                return

            content = video_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content)
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found."})

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/api/align":
            self._handle_align()
            return

        if self.path == "/api/generate/start":
            self._handle_generate_start()
            return

        if self.path != "/api/generate":
            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found."})
            return

        request_id = build_request_id()
        try:
            payload = self._read_json_body()
        except ValueError as exc:
            append_bug_log(
                request_id=request_id,
                stage="request",
                severity="error",
                message="Invalid request payload",
                detail=str(exc),
            )
            status, err = json_error(
                str(exc),
                status=HTTPStatus.BAD_REQUEST,
                request_id=request_id,
            )
            self._send_json(status, err)
            return

        prompt = str(payload.get("prompt", "")).strip()
        provider_id = str(payload.get("provider", DEFAULT_PROVIDER)).strip() or DEFAULT_PROVIDER
        provider = resolve_provider(provider_id)
        api_key = str(payload.get("apiKey", "")).strip()
        model = str(payload.get("model", "")).strip() or provider.default_model or DEFAULT_MODEL
        base_url = str(payload.get("baseUrl", "")).strip()
        endpoint = str(payload.get("endpoint", "")).strip()
        scene_name = safe_scene_name(str(payload.get("sceneName", "GeneratedScene")))
        no_render = bool(payload.get("noRender", False))

        try:
            temperature = float(payload.get("temperature", 0.2))
        except (TypeError, ValueError):
            temperature = 0.2
        temperature = max(0.0, min(1.0, temperature))

        request_context = {
            "provider": provider.id,
            "providerName": provider.name,
            "apiType": provider.api_type,
            "model": model,
            "baseUrl": base_url or provider.base_url,
            "endpoint": endpoint or provider.base_url,
            "sceneNameInput": scene_name,
            "temperature": temperature,
            "noRender": no_render,
            "promptLen": len(prompt),
            "promptHash": prompt_fingerprint(prompt) if prompt else None,
        }

        if len(prompt) < 6:
            detail = "Please provide a clearer learning question."
            append_bug_log(
                request_id=request_id,
                stage="validation",
                severity="warn",
                message="Prompt is too short",
                detail=detail,
                context=request_context,
            )
            status, err = json_error(
                "Prompt is too short.",
                status=HTTPStatus.BAD_REQUEST,
                detail=detail,
                request_id=request_id,
            )
            self._send_json(status, err)
            return

        if provider.requires_api_key and not api_key:
            detail = f"Please paste your own {provider.name} API key in the form."
            append_bug_log(
                request_id=request_id,
                stage="validation",
                severity="warn",
                message="Missing API key",
                detail=detail,
                context=request_context,
            )
            status, err = json_error(
                "Missing API key.",
                status=HTTPStatus.BAD_REQUEST,
                detail=detail,
                request_id=request_id,
            )
            self._send_json(status, err)
            return

        if is_placeholder_api_key(api_key):
            detail = "Please use a real key generated in your own account."
            append_bug_log(
                request_id=request_id,
                stage="validation",
                severity="warn",
                message="Placeholder API key detected",
                detail=detail,
                context=request_context,
            )
            status, err = json_error(
                "Placeholder API key detected.",
                status=HTTPStatus.BAD_REQUEST,
                detail=detail,
                request_id=request_id,
            )
            self._send_json(status, err)
            return

        ensure_generated_dir()
        resolved_endpoint = endpoint or provider.base_url
        provider_name = provider.name
        max_attempts = 1 if no_render else MAX_RENDER_ATTEMPTS
        retry_feedback = ""
        last_code = ""
        last_scene_file: Path | None = None
        last_scene_name = scene_name
        last_notes: list[str] = []

        for attempt in range(1, max_attempts + 1):
            effective_prompt = prompt
            if retry_feedback:
                effective_prompt = (
                    f"{prompt}\n\n"
                    "# Previous render failed\n"
                    "Regenerate the complete Manim scene. Avoid LaTeX-dependent classes and hidden LaTeX helpers. "
                    "Use Text instead of Tex/MathTex and set BraceLabel(label_constructor=Text) when using labels. "
                    "Avoid unsupported Manim APIs from the error below.\n"
                    f"{retry_feedback[-1800:]}"
                )

            try:
                append_runtime_log(
                    "MODEL_REQUEST_START",
                    (
                        f"request_id={request_id} attempt={attempt}/{max_attempts} "
                        f"provider={provider.id} model={model} endpoint={resolved_endpoint}"
                    ),
                )
                raw_code, provider_name, resolved_endpoint = generate_code_with_llm(
                    provider_id=provider.id,
                    api_key=api_key,
                    base_url=base_url or None,
                    endpoint=(endpoint or DEFAULT_ZHIPU_ENDPOINT) if provider.id == "zhipu" else None,
                    model=model,
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=effective_prompt,
                    temperature=temperature,
                )
                request_context["endpoint"] = resolved_endpoint
                code = extract_python_only(raw_code)
                code, notes = apply_runtime_compatibility_fixes(code)
                if notes:
                    append_runtime_log(
                        "COMPATIBILITY_FIX",
                        f"request_id={request_id} attempt={attempt}/{max_attempts} {'; '.join(notes)}",
                    )
                append_runtime_log(
                    "MODEL_REQUEST_OK",
                    (
                        f"request_id={request_id} attempt={attempt}/{max_attempts} "
                        f"provider={provider.id} model={model} chars={len(code)}"
                    ),
                )
            except Exception as exc:
                detail = str(exc)
                append_runtime_log(
                    "MODEL_REQUEST_FAIL",
                    (
                        f"request_id={request_id} attempt={attempt}/{max_attempts} "
                        f"provider={provider.id} model={model} endpoint={resolved_endpoint} error={detail}"
                    ),
                )
                append_bug_log(
                    request_id=request_id,
                    stage="model",
                    severity="error",
                    message="Model request failed",
                    detail=detail,
                    context={**request_context, "attempt": attempt, "maxAttempts": max_attempts},
                )
                status, err = json_error(
                    "Model request failed.",
                    status=HTTPStatus.BAD_GATEWAY,
                    detail=detail,
                    request_id=request_id,
                )
                self._send_json(status, err)
                return

            detected_scene_name = detect_scene_name(code, scene_name)
            filename = f"scene_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}.py"
            scene_file = GENERATED_DIR / filename
            scene_file.write_text(code.strip() + "\n", encoding="utf-8")
            last_code = code
            last_scene_file = scene_file
            last_scene_name = detected_scene_name
            last_notes = notes

            response: dict[str, Any] = {
                "ok": True,
                "requestId": request_id,
                "provider": provider.id,
                "providerName": provider_name,
                "endpoint": resolved_endpoint,
                "sceneName": detected_scene_name,
                "code": code,
                "codeFile": str(scene_file.relative_to(PROJECT_ROOT)),
                "attempt": attempt,
                "maxAttempts": max_attempts,
            }
            if notes:
                response["warnings"] = notes

            if no_render:
                response["message"] = "Code generated successfully. Render skipped."
                append_runtime_log(
                    "GENERATE_SKIP_RENDER",
                    f"request_id={request_id} file={scene_file.name} scene={detected_scene_name}",
                )
                self._send_json(HTTPStatus.OK, response)
                return

            try:
                render_scene(scene_file, detected_scene_name)
                video_path = find_latest_video(scene_file, detected_scene_name)
                if video_path is None:
                    raise RuntimeError("Render completed but output video was not found.")
                video_duration = probe_video_duration(video_path)
                response["videoId"] = register_video(video_path)
                if video_duration is not None:
                    response["videoDuration"] = video_duration
                response["alignment"] = generate_alignment(
                    prompt=prompt,
                    code=code,
                    scene_name=detected_scene_name,
                    video_duration=video_duration,
                    llm_call=None,
                )
                append_runtime_log(
                    "ALIGNMENT_FALLBACK",
                    (
                        f"request_id={request_id} scene={detected_scene_name} "
                        "reason=initial_response_uses_fast_metadata_alignment"
                    ),
                )
                response["message"] = "Code generated and video rendered successfully."
                if attempt > 1:
                    response["message"] += f" Auto-retry succeeded on attempt {attempt}."
                append_runtime_log(
                    "RENDER_OK",
                    (
                        f"request_id={request_id} attempt={attempt}/{max_attempts} "
                        f"file={scene_file.name} scene={detected_scene_name} video={video_path}"
                    ),
                )
                self._send_json(HTTPStatus.OK, response)
                return
            except Exception as exc:
                detail = str(exc)
                append_runtime_log(
                    "RENDER_FAIL",
                    (
                        f"request_id={request_id} attempt={attempt}/{max_attempts} "
                        f"file={scene_file.name} scene={detected_scene_name} error={detail}"
                    ),
                )
                append_bug_log(
                    request_id=request_id,
                    stage="render",
                    severity="error",
                    message="Render failed",
                    detail=detail,
                    context={
                        **request_context,
                        "attempt": attempt,
                        "maxAttempts": max_attempts,
                        "sceneNameDetected": detected_scene_name,
                        "codeFile": str(scene_file.relative_to(PROJECT_ROOT)),
                        "warnings": notes,
                    },
                )
                if attempt < max_attempts:
                    retry_feedback = detail
                    append_runtime_log(
                        "RENDER_RETRY",
                        f"request_id={request_id} next_attempt={attempt + 1}/{max_attempts}",
                    )
                    continue

                status, err = json_error(
                    f"Render failed after {max_attempts} attempts.",
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                    detail=detail,
                    request_id=request_id,
                )
                err["attempt"] = attempt
                err["maxAttempts"] = max_attempts
                err["code"] = last_code
                if last_scene_file is not None:
                    err["codeFile"] = str(last_scene_file.relative_to(PROJECT_ROOT))
                err["sceneName"] = last_scene_name
                if last_notes:
                    err["warnings"] = last_notes
                self._send_json(status, err)
                return

    def _handle_generate_start(self) -> None:
        try:
            payload = self._read_json_body()
        except ValueError as exc:
            request_id = build_request_id()
            append_bug_log(
                request_id=request_id,
                stage="request",
                severity="error",
                message="Invalid request payload",
                detail=str(exc),
            )
            status, err = json_error(
                str(exc),
                status=HTTPStatus.BAD_REQUEST,
                request_id=request_id,
            )
            self._send_json(status, err)
            return

        prompt = str(payload.get("prompt", "")).strip()
        job_id = create_job(prompt)
        emit_job_event(
            job_id,
            status="queued",
            stage="queued",
            student_message="任务已创建，正在准备把问题变成教学动画。",
            technical_message="GENERATE_JOB_CREATED",
        )
        thread = threading.Thread(target=run_generate_job, args=(job_id, payload), daemon=True)
        thread.start()
        self._send_json(
            HTTPStatus.ACCEPTED,
            {
                "ok": True,
                "jobId": job_id,
                "requestId": job_id,
                "statusUrl": f"/api/jobs/{job_id}",
            },
        )
        return

    def _build_alignment_response(
        self,
        *,
        request_id: str,
        prompt: str,
        code: str,
        scene_name: str,
        video_duration: float | None,
        provider_id: str,
        api_key: str,
        base_url: str | None,
        endpoint: str | None,
        model: str,
        temperature: float,
    ) -> dict[str, Any]:
        def call_alignment_model(system_prompt: str, user_prompt: str) -> str:
            raw_text, _provider_name, _resolved_endpoint = generate_code_with_llm(
                provider_id=provider_id,
                api_key=api_key,
                base_url=base_url,
                endpoint=endpoint,
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=min(0.4, temperature),
            )
            return raw_text

        alignment = generate_alignment(
            prompt=prompt,
            code=code,
            scene_name=scene_name,
            video_duration=video_duration,
            llm_call=call_alignment_model,
        )
        event_name = "ALIGNMENT_FALLBACK" if alignment.get("confidence") == "low" else "ALIGNMENT_OK"
        append_runtime_log(
            event_name,
            (
                f"request_id={request_id} scene={scene_name} "
                f"segments={len(alignment.get('segments', []))} confidence={alignment.get('confidence')}"
            ),
        )
        return alignment

    def _handle_align(self) -> None:
        request_id = build_request_id()
        try:
            payload = self._read_json_body()
        except ValueError as exc:
            status, err = json_error(
                str(exc),
                status=HTTPStatus.BAD_REQUEST,
                request_id=request_id,
            )
            self._send_json(status, err)
            return

        prompt = str(payload.get("prompt", "")).strip()
        code = str(payload.get("code", "")).strip()
        scene_name = safe_scene_name(str(payload.get("sceneName", "GeneratedScene")))
        provider_id = str(payload.get("provider", DEFAULT_PROVIDER)).strip() or DEFAULT_PROVIDER
        provider = resolve_provider(provider_id)
        api_key = str(payload.get("apiKey", "")).strip()
        model = str(payload.get("model", "")).strip() or provider.default_model or DEFAULT_MODEL
        base_url = str(payload.get("baseUrl", "")).strip()
        endpoint = str(payload.get("endpoint", "")).strip()
        video_duration = optional_positive_float(payload.get("videoDuration"))

        try:
            temperature = float(payload.get("temperature", 0.2))
        except (TypeError, ValueError):
            temperature = 0.2
        temperature = max(0.0, min(1.0, temperature))

        if len(prompt) < 6 or not code:
            status, err = json_error(
                "Prompt and code are required for alignment.",
                status=HTTPStatus.BAD_REQUEST,
                request_id=request_id,
            )
            self._send_json(status, err)
            return

        if provider.requires_api_key and not api_key:
            status, err = json_error(
                "Missing API key.",
                status=HTTPStatus.BAD_REQUEST,
                detail=f"Please paste your own {provider.name} API key in the form.",
                request_id=request_id,
            )
            self._send_json(status, err)
            return

        alignment = self._build_alignment_response(
            request_id=request_id,
            prompt=prompt,
            code=code,
            scene_name=scene_name,
            video_duration=video_duration,
            provider_id=provider.id,
            api_key=api_key,
            base_url=base_url or None,
            endpoint=(endpoint or DEFAULT_ZHIPU_ENDPOINT) if provider.id == "zhipu" else None,
            model=model,
            temperature=temperature,
        )
        self._send_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "requestId": request_id,
                "alignment": alignment,
            },
        )

    def log_message(self, fmt: str, *args: Any) -> None:
        # Keep server logs concise and avoid accidentally printing user payloads.
        msg = fmt % args
        print(f"[web] {self.address_string()} - {msg}")
        append_runtime_log("HTTP", msg)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aegis web server")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=8000, help="Bind port")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ensure_generated_dir()
    ensure_runtime_log_dir()
    server = ThreadingHTTPServer((args.host, args.port), AegisWebHandler)
    print(f"Aegis Web running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

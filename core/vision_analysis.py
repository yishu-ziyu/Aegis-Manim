from __future__ import annotations

import base64
import json
import os
import re
import shlex
import subprocess
import tempfile
import time
from http import HTTPStatus
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

ACCEPTED_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
MAX_IMAGE_BYTES = int(os.getenv("AEGIS_VISION_MAX_IMAGE_BYTES", str(5 * 1024 * 1024)))
MAX_VISION_REQUEST_BYTES = int(os.getenv("AEGIS_VISION_MAX_REQUEST_BYTES", str(7 * 1024 * 1024)))
_TRUE_VALUES = {"1", "true", "yes", "on"}
_RETRYABLE_HTTP_STATUS = {429, 500, 502, 503, 504}
_MIME_SUFFIX = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}


def _env_int(name: str, default: str) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return int(default)


def _env_float(name: str, default: str) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return float(default)


def _read_http_error_detail(exc: urllib_error.HTTPError) -> str:
    return exc.read().decode("utf-8", errors="replace")[:1000]


def _error(status: HTTPStatus, code: str, message: str, *, detail: str | None = None) -> tuple[int, dict[str, object]]:
    payload: dict[str, object] = {
        "ok": False,
        "error": message,
        "code": code,
    }
    if detail:
        payload["detail"] = detail
    return int(status), payload


def is_vision_provider_configured() -> bool:
    return bool(
        os.getenv("VISION_BACKEND_URL", "").strip()
        or os.getenv("KIMI_VISION_CLI_COMMAND", "").strip()
        or os.getenv("GEMINI_API_KEY", "").strip()
        or os.getenv("GOOGLE_API_KEY", "").strip()
        or os.getenv("VISION_API_KEY", "").strip()
        or os.getenv("VISION_OCR_COMMAND", "").strip()
        or os.getenv("KIMI_VISION_API_KEY", "").strip()
        or os.getenv("MOONSHOT_API_KEY", "").strip()
    )


def is_vision_public_enabled() -> bool:
    return (
        os.getenv("AEGIS_VISION_PUBLIC_ENABLED", "").strip().lower() in _TRUE_VALUES
        and is_vision_provider_configured()
    )


def disabled_vision_response() -> tuple[int, dict[str, object]]:
    return _error(
        HTTPStatus.SERVICE_UNAVAILABLE,
        "vision_feature_disabled",
        "图片理解功能仍在服务器 CLI 验收中，暂未公开。",
        detail=(
            "Set AEGIS_VISION_PUBLIC_ENABLED=1 and configure VISION_BACKEND_URL "
            "or KIMI_VISION_CLI_COMMAND after real CLI image tests pass. "
            "Fallback options: GEMINI_API_KEY, VISION_API_KEY, or VISION_OCR_COMMAND."
        ),
    )


def _parse_image_data(payload: dict[str, object]) -> tuple[str, str, bytes] | tuple[None, None, None]:
    image_data = str(payload.get("imageData", "")).strip()
    mime_type = str(payload.get("mimeType", "")).strip().lower()
    if not image_data:
        return None, None, None

    if image_data.startswith("data:"):
        match = re.match(r"^data:([^;,]+);base64,(.+)$", image_data, flags=re.DOTALL)
        if not match:
            raise ValueError("图片 data URL 格式不正确。")
        mime_type = match.group(1).strip().lower()
        image_base64 = match.group(2).strip()
    else:
        image_base64 = image_data

    if mime_type == "image/jpg":
        mime_type = "image/jpeg"
    if mime_type not in ACCEPTED_IMAGE_MIME_TYPES:
        raise ValueError("仅支持 PNG、JPG/JPEG、WebP 图片。")

    try:
        raw = base64.b64decode(image_base64, validate=True)
    except Exception as exc:
        raise ValueError("图片不是有效的 base64 数据。") from exc
    if not raw:
        raise ValueError("图片内容为空。")
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("图片超过 5MB，请压缩后再上传。")
    return image_base64, mime_type, raw


def _extract_openai_text(response_json: dict[str, object]) -> str:
    choices = response_json.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content
            text = first.get("text")
            if isinstance(text, str):
                return text
    raise RuntimeError("视觉模型返回格式不符合 OpenAI-compatible 响应。")


def _extract_json_object(text: str) -> dict[str, object]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
    if match:
        parsed = json.loads(match.group(0))
        if isinstance(parsed, dict):
            return parsed
    return {
        "image_type": "unknown",
        "recognized_content": stripped,
        "key_elements": [],
        "uncertainties": ["模型没有返回结构化 JSON，已保留原始中文分析。"],
        "visualization_plan": stripped,
        "recommended_prompt": stripped,
    }


def _vision_prompt(user_hint: str) -> str:
    hint = user_hint.strip() or "用户没有补充方向，请先按经济学考研教学可视化来理解图片。"
    return "\n".join(
        [
            "你是 Aegis Manim 的图片理解助手。请用中文理解用户上传的图片，并准备把它转成 Manim 动画。",
            "输出必须是 JSON，不要 Markdown，不要代码。",
            "字段：image_type, recognized_content, key_elements, uncertainties, visualization_plan, recommended_prompt, auditable_analysis。",
            "规则：",
            "1. recognized_content 用中文说明图片中题目、图表、公式或关键文字。",
            "2. visualization_plan 说明适合怎样做成动态教学图。",
            "3. recommended_prompt 是下一步交给代码生成模型的中文提示词，必须可直接用于生成 Manim。",
            "4. 如果图片信息不够清楚，在 uncertainties 中说明，并在 auditable_analysis 中给出可展开的判断依据。",
            "5. 不要编造看不清的数字或题干。",
            "",
            f"用户补充方向：{hint}",
        ]
    )


def _run_cli_vision_provider(
    *,
    command_template: str,
    image_bytes: bytes,
    mime_type: str,
    user_hint: str,
) -> tuple[int, dict[str, object]]:
    timeout = int(os.getenv("KIMI_VISION_CLI_TIMEOUT_SECONDS", "180"))
    with tempfile.TemporaryDirectory(prefix="aegis-vision-") as temp_dir:
        temp_path = Path(temp_dir)
        image_path = temp_path / f"upload{_MIME_SUFFIX.get(mime_type, '.img')}"
        prompt_path = temp_path / "prompt.txt"
        output_path = temp_path / "analysis.json"
        image_path.write_bytes(image_bytes)
        prompt_path.write_text(_vision_prompt(user_hint), encoding="utf-8")

        replacements = {
            "{image_path}": str(image_path),
            "{prompt_path}": str(prompt_path),
            "{output_path}": str(output_path),
        }
        command = command_template
        for key, value in replacements.items():
            command = command.replace(key, shlex.quote(value))
        args = shlex.split(command)
        result = subprocess.run(
            args,
            cwd=temp_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            return _error(
                HTTPStatus.BAD_GATEWAY,
                "vision_cli_error",
                "服务器图片理解 CLI 调用失败。",
                detail=detail[:1000] or f"exit {result.returncode}",
            )
        raw_text = output_path.read_text(encoding="utf-8").strip() if output_path.exists() else ""
        if not raw_text:
            raw_text = (result.stdout or "").strip()
        if not raw_text:
            return _error(HTTPStatus.BAD_GATEWAY, "vision_cli_empty", "服务器图片理解 CLI 没有返回内容。")
        analysis = _extract_json_object(raw_text)
        recommended_prompt = str(analysis.get("recommended_prompt") or analysis.get("visualization_plan") or raw_text).strip()
        return int(HTTPStatus.OK), {
            "ok": True,
            "analysis": analysis,
            "suggestedPrompt": recommended_prompt,
            "visionMeta": {
                "mimeType": mime_type,
                "imageBytes": len(image_bytes),
                "provider": "kimi-vision-cli",
                "command": args[0] if args else "",
            },
        }


def _run_remote_vision_provider(payload: dict[str, object]) -> tuple[int, dict[str, object]]:
    backend_url = os.getenv("VISION_BACKEND_URL", "").strip().rstrip("/")
    if not backend_url:
        return _error(HTTPStatus.SERVICE_UNAVAILABLE, "vision_backend_unconfigured", "图片理解后端未配置。")

    api_key = os.getenv("VISION_BACKEND_API_KEY", os.getenv("AEGIS_VISION_BACKEND_API_KEY", "")).strip()
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Aegis-Manim-Vision-Gateway/1.0",
    }
    if api_key:
        headers["X-API-Key"] = api_key

    req = urllib_request.Request(
        f"{backend_url}/api/vision/analyze",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=int(os.getenv("VISION_BACKEND_TIMEOUT_SECONDS", "360"))) as resp:
            body = resp.read().decode("utf-8")
            parsed = json.loads(body) if body else {}
            if isinstance(parsed, dict):
                return int(resp.status), parsed
            return _error(HTTPStatus.BAD_GATEWAY, "vision_backend_bad_response", "图片理解后端返回格式不正确。")
    except urllib_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        try:
            parsed = json.loads(detail)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return int(exc.code), parsed
        return _error(HTTPStatus.BAD_GATEWAY, "vision_backend_error", "图片理解后端调用失败。", detail=detail)
    except Exception as exc:
        return _error(HTTPStatus.BAD_GATEWAY, "vision_backend_error", "图片理解后端连接失败。", detail=str(exc))


def _run_ocr_command_provider(
    *,
    command_template: str,
    image_bytes: bytes,
    mime_type: str,
    user_hint: str,
) -> tuple[int, dict[str, object]]:
    timeout = int(os.getenv("VISION_OCR_TIMEOUT_SECONDS", "90"))
    with tempfile.TemporaryDirectory(prefix="aegis-vision-ocr-") as temp_dir:
        temp_path = Path(temp_dir)
        image_path = temp_path / f"upload{_MIME_SUFFIX.get(mime_type, '.img')}"
        output_path = temp_path / "ocr.txt"
        image_path.write_bytes(image_bytes)

        replacements = {
            "{image_path}": str(image_path),
            "{output_path}": str(output_path),
        }
        command = command_template
        for key, value in replacements.items():
            command = command.replace(key, shlex.quote(value))
        args = shlex.split(command)
        result = subprocess.run(
            args,
            cwd=temp_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            return _error(
                HTTPStatus.BAD_GATEWAY,
                "vision_ocr_error",
                "OCR 命令调用失败。",
                detail=detail[:1000] or f"exit {result.returncode}",
            )

        ocr_text = output_path.read_text(encoding="utf-8").strip() if output_path.exists() else ""
        if not ocr_text:
            ocr_text = (result.stdout or "").strip()
        if not ocr_text:
            return _error(HTTPStatus.BAD_GATEWAY, "vision_ocr_empty", "OCR 命令没有返回可识别文字。")

    hint = user_hint.strip() or "请按经济学考研教学可视化方向处理。"
    key_lines = [line.strip() for line in ocr_text.splitlines() if line.strip()][:8]
    recommended_prompt = "\n".join(
        [
            "请基于 OCR 识别出的中文题干，生成一段 Manim 教学动画。",
            "要求：中文讲解，先复原题意，再动态画出核心经济学图形或公式推导，最后给出考研答题要点。",
            f"用户补充方向：{hint}",
            "OCR 识别文字：",
            ocr_text,
            "注意：如果题目依赖图片中的曲线、阴影或坐标关系，请先用合理假设标注，并提示用户确认。不要编造看不清的数字。",
        ]
    )
    analysis = {
        "image_type": "ocr_text_image",
        "recognized_content": f"OCR 识别到以下文字：{ocr_text}",
        "key_elements": key_lines,
        "uncertainties": ["OCR 只能稳定读取文字；曲线位置、阴影区域、手写标注和图形关系需要用户确认。"],
        "visualization_plan": "先展示 OCR 题干，再把可确认的经济学变量、公式或图形关系转成中文动态教学图。",
        "recommended_prompt": recommended_prompt,
        "auditable_analysis": "该结果来自用户配置的 OCR 命令，不包含多模态图形语义判断。",
    }
    return int(HTTPStatus.OK), {
        "ok": True,
        "analysis": analysis,
        "suggestedPrompt": recommended_prompt,
        "visionMeta": {
            "mimeType": mime_type,
            "imageBytes": len(image_bytes),
            "provider": "ocr-command",
            "command": args[0] if args else "",
        },
    }


def _run_gemini_vision_provider(
    *,
    api_key: str,
    image_base64: str,
    image_bytes: bytes,
    mime_type: str,
    user_hint: str,
) -> tuple[int, dict[str, object]]:
    model = os.getenv("GEMINI_VISION_MODEL", "gemini-flash-lite-latest").strip() or "gemini-flash-lite-latest"
    base_url = os.getenv("GEMINI_VISION_BASE_URL", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
    request_payload = {
        "contents": [
            {
                "parts": [
                    {"inline_data": {"mime_type": mime_type, "data": image_base64}},
                    {"text": _vision_prompt(user_hint)},
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": int(os.getenv("GEMINI_VISION_MAX_TOKENS", "1200")),
        },
    }
    request_data = json.dumps(request_payload, ensure_ascii=False).encode("utf-8")
    timeout = _env_int("GEMINI_VISION_TIMEOUT_SECONDS", "45")
    retries = max(0, _env_int("GEMINI_VISION_RETRIES", "2"))
    retry_backoff = max(0.0, _env_float("GEMINI_VISION_RETRY_BACKOFF_SECONDS", "1.5"))
    parsed: dict[str, object] | None = None
    for attempt in range(retries + 1):
        req = urllib_request.Request(
            f"{base_url}/models/{model}:generateContent?key={api_key}",
            data=request_data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Aegis-Manim-Vision/1.0 (https://manim.yishuziyu.cn)",
            },
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=timeout) as resp:
                parsed = json.loads(resp.read().decode("utf-8"))
                break
        except urllib_error.HTTPError as exc:
            detail = _read_http_error_detail(exc)
            if exc.code in _RETRYABLE_HTTP_STATUS and attempt < retries:
                time.sleep(retry_backoff * (attempt + 1))
                continue
            return _error(HTTPStatus.BAD_GATEWAY, "vision_provider_error", "Gemini 图片理解模型调用失败。", detail=detail)
        except Exception as exc:
            if attempt < retries:
                time.sleep(retry_backoff * (attempt + 1))
                continue
            return _error(HTTPStatus.BAD_GATEWAY, "vision_provider_error", "Gemini 图片理解模型调用失败。", detail=str(exc))
    if parsed is None:
        return _error(HTTPStatus.BAD_GATEWAY, "vision_provider_error", "Gemini 图片理解模型没有返回内容。")

    try:
        candidates = parsed.get("candidates")
        first = candidates[0] if isinstance(candidates, list) and candidates else {}
        content = first.get("content") if isinstance(first, dict) else {}
        parts = content.get("parts") if isinstance(content, dict) else []
        text = ""
        if isinstance(parts, list):
            text = "\n".join(str(part.get("text", "")) for part in parts if isinstance(part, dict)).strip()
        if not text:
            raise RuntimeError("Gemini response missing text parts.")
    except Exception as exc:
        return _error(HTTPStatus.BAD_GATEWAY, "vision_provider_error", "Gemini 返回格式不正确。", detail=str(exc))

    analysis = _extract_json_object(text)
    recommended_prompt = str(analysis.get("recommended_prompt") or analysis.get("visualization_plan") or text).strip()
    return int(HTTPStatus.OK), {
        "ok": True,
        "analysis": analysis,
        "suggestedPrompt": recommended_prompt,
        "visionMeta": {
            "mimeType": mime_type,
            "imageBytes": len(image_bytes),
            "provider": "gemini-vision",
            "model": model,
        },
    }


def analyze_image_payload(payload: dict[str, object]) -> tuple[int, dict[str, object]]:
    if os.getenv("VISION_BACKEND_URL", "").strip():
        return _run_remote_vision_provider(payload)

    try:
        image_base64, mime_type, image_bytes = _parse_image_data(payload)
    except ValueError as exc:
        return _error(HTTPStatus.BAD_REQUEST, "invalid_image", str(exc))
    if image_base64 is None or mime_type is None or image_bytes is None:
        return _error(HTTPStatus.BAD_REQUEST, "missing_image", "请先上传一张图片。")

    user_hint = str(payload.get("prompt", payload.get("userHint", "")))
    cli_command = os.getenv("KIMI_VISION_CLI_COMMAND", "").strip()
    if cli_command:
        return _run_cli_vision_provider(
            command_template=cli_command,
            image_bytes=image_bytes,
            mime_type=mime_type,
            user_hint=user_hint,
        )

    gemini_api_key = (os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip())
    if gemini_api_key:
        return _run_gemini_vision_provider(
            api_key=gemini_api_key,
            image_base64=image_base64,
            image_bytes=image_bytes,
            mime_type=mime_type,
            user_hint=user_hint,
        )

    api_key = (
        os.getenv("VISION_API_KEY", "").strip()
        or os.getenv("KIMI_VISION_API_KEY", "").strip()
        or os.getenv("MOONSHOT_API_KEY", "").strip()
    )
    ocr_command = os.getenv("VISION_OCR_COMMAND", "").strip()
    if not api_key:
        if ocr_command:
            return _run_ocr_command_provider(
                command_template=ocr_command,
                image_bytes=image_bytes,
                mime_type=mime_type,
                user_hint=user_hint,
            )
        code_key_configured = bool(os.getenv("KIMI_CODE_API_KEY", "").strip())
        detail = (
            "检测到 KIMI_CODE_API_KEY，但 Kimi Code 会员 Key 不能作为网页视觉 API 使用；"
            "需要单独配置 GEMINI_API_KEY、VISION_API_KEY、KIMI_VISION_API_KEY 或 MOONSHOT_API_KEY。"
            if code_key_configured
            else "需要配置 GEMINI_API_KEY、VISION_API_KEY、KIMI_VISION_API_KEY、MOONSHOT_API_KEY 或 VISION_OCR_COMMAND。"
        )
        return _error(
            HTTPStatus.SERVICE_UNAVAILABLE,
            "vision_provider_unconfigured",
            "图片理解能力暂未配置，当前不会向公众展示上传入口。",
            detail=f"{detail} 如果复用服务器上的真实 Kimi/Codex/Claude CLI 登录态，请配置 KIMI_VISION_CLI_COMMAND。",
        )

    base_url = os.getenv("VISION_BASE_URL", os.getenv("KIMI_VISION_BASE_URL", "https://api.moonshot.cn/v1")).rstrip("/")
    model = os.getenv("VISION_MODEL", os.getenv("KIMI_VISION_MODEL", "kimi-latest")).strip() or "kimi-latest"
    provider_name = os.getenv("VISION_PROVIDER_NAME", "openai-compatible-vision").strip() or "openai-compatible-vision"
    request_payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_base64}"}},
                    {"type": "text", "text": _vision_prompt(user_hint)},
                ],
            }
        ],
        "temperature": 0.1,
        "max_tokens": int(os.getenv("VISION_MAX_TOKENS", os.getenv("KIMI_VISION_MAX_TOKENS", "1200"))),
    }
    request_data = json.dumps(request_payload, ensure_ascii=False).encode("utf-8")
    timeout = _env_int("VISION_TIMEOUT_SECONDS", os.getenv("KIMI_VISION_TIMEOUT_SECONDS", "45"))
    retries = max(0, _env_int("VISION_RETRIES", "2"))
    retry_backoff = max(0.0, _env_float("VISION_RETRY_BACKOFF_SECONDS", "1.5"))
    parsed = None
    for attempt in range(retries + 1):
        req = urllib_request.Request(
            f"{base_url}/chat/completions",
            data=request_data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "Aegis-Manim-Vision/1.0 (https://manim.yishuziyu.cn)",
            },
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=timeout) as resp:
                parsed = json.loads(resp.read().decode("utf-8"))
                break
        except urllib_error.HTTPError as exc:
            detail = _read_http_error_detail(exc)
            if exc.code in _RETRYABLE_HTTP_STATUS and attempt < retries:
                time.sleep(retry_backoff * (attempt + 1))
                continue
            return _error(HTTPStatus.BAD_GATEWAY, "vision_provider_error", "图片理解模型调用失败。", detail=detail)
        except Exception as exc:
            if attempt < retries:
                time.sleep(retry_backoff * (attempt + 1))
                continue
            return _error(HTTPStatus.BAD_GATEWAY, "vision_provider_error", "图片理解模型调用失败。", detail=str(exc))
    if parsed is None:
        return _error(HTTPStatus.BAD_GATEWAY, "vision_provider_error", "图片理解模型没有返回内容。")

    analysis = _extract_json_object(_extract_openai_text(parsed))
    recommended_prompt = str(analysis.get("recommended_prompt") or analysis.get("visualization_plan") or "").strip()
    return int(HTTPStatus.OK), {
        "ok": True,
        "analysis": analysis,
        "suggestedPrompt": recommended_prompt,
        "visionMeta": {
            "mimeType": mime_type,
            "imageBytes": len(image_bytes),
            "provider": provider_name,
            "model": model,
        },
    }

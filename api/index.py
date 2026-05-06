from __future__ import annotations

import json
import ipaddress
import socket
import sys
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

APP_VERSION = "vercel_gateway_v20260506_1"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = PROJECT_ROOT / "core"
if str(CORE_PATH) not in sys.path:
    sys.path.insert(0, str(CORE_PATH))

from llm_providers import (  # noqa: E402
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    provider_presets_for_ui,
    resolve_provider,
)
from manim_agent import (  # noqa: E402
    apply_runtime_compatibility_fixes,
    extract_python_only,
    generate_code_with_llm,
    load_system_prompt,
)
import web_app as local_web_app  # noqa: E402

SYSTEM_PROMPT = load_system_prompt()
DISABLED_CLOUD_PROVIDERS = {"codex-cli", "codex-local-proxy"}
LOCAL_HOSTNAMES = {"localhost"}
CLOUD_ENDPOINT_ERROR = (
    "Vercel 云端只支持公网 HTTPS 模型端点；本机、内网和 http:// 地址请在本地 Aegis Web 使用。"
)


def build_health_payload() -> dict[str, object]:
    return {
        "ok": True,
        "runtime": "vercel-python-function",
        "renderBackend": "external-required",
        "version": APP_VERSION,
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def build_generate_unavailable_payload() -> dict[str, object]:
    return {
        "ok": False,
        "error": "Video rendering is not available on the Vercel gateway.",
        "detail": (
            "Aegis-Manim needs a long-running Python service with Manim, ffmpeg, "
            "and local media storage. Keep Vercel as the public gateway and deploy "
            "the render backend on a VPS, Render, or Fly.io."
        ),
    }


def public_provider_config() -> dict[str, object]:
    config = provider_presets_for_ui()
    providers = {
        provider_id: dict(provider)
        for provider_id, provider in dict(config.get("providers", {})).items()
    }
    for provider_id in DISABLED_CLOUD_PROVIDERS:
        provider = providers.get(provider_id)
        if not provider:
            continue
        provider["name"] = f"{provider.get('name', provider_id)}（仅本地）"
        provider["cloudUnavailable"] = True
        provider["apiKeyPlaceholder"] = "仅本地 Aegis Web 可用"
        provider["requiresApiKey"] = False
    return {**config, "providers": providers}


def clamp_temperature(value: object) -> float:
    try:
        temperature = float(value)
    except (TypeError, ValueError):
        temperature = 0.2
    return max(0.0, min(1.0, temperature))


def is_private_or_local_host(host: str) -> bool:
    normalized = host.strip("[]").lower().rstrip(".")
    if (
        normalized in LOCAL_HOSTNAMES
        or normalized.endswith(".localhost")
        or normalized.endswith(".local")
    ):
        return True

    try:
        ip = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_cloud_model_endpoint(raw_url: str, *, field_name: str) -> str | None:
    cleaned = raw_url.strip()
    if not cleaned:
        return None

    parsed = urlparse(cleaned)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        return CLOUD_ENDPOINT_ERROR
    if is_private_or_local_host(parsed.hostname):
        return CLOUD_ENDPOINT_ERROR

    try:
        resolved = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return f"{field_name} 无法解析，请填写公网可访问的 HTTPS 模型端点。"

    for result in resolved:
        address = result[4][0]
        if is_private_or_local_host(address):
            return CLOUD_ENDPOINT_ERROR
    return None


def generate_manim_code_for_gateway(payload: dict[str, object]) -> tuple[int, dict[str, object]]:
    prompt = str(payload.get("prompt", "")).strip()
    if not prompt:
        return HTTPStatus.BAD_REQUEST, {"ok": False, "error": "请输入要讲清楚的问题。"}

    provider_id = str(payload.get("provider", DEFAULT_PROVIDER)).strip() or DEFAULT_PROVIDER
    if provider_id in DISABLED_CLOUD_PROVIDERS:
        return HTTPStatus.BAD_REQUEST, {
            "ok": False,
            "error": "这个 Provider 只能在本机使用，不能在 Vercel 云端运行。",
        }

    provider = resolve_provider(provider_id)
    api_key = str(payload.get("apiKey", "")).strip()
    model = str(payload.get("model", "")).strip() or provider.default_model or DEFAULT_MODEL
    base_url = str(payload.get("baseUrl", "")).strip()
    endpoint = str(payload.get("endpoint", "")).strip()
    scene_name = local_web_app.safe_scene_name(str(payload.get("sceneName", "GeneratedScene")))
    temperature = clamp_temperature(payload.get("temperature", 0.2))

    for field_name, raw_url in (("Base URL", base_url), ("Endpoint", endpoint)):
        endpoint_error = validate_cloud_model_endpoint(raw_url, field_name=field_name)
        if endpoint_error:
            return HTTPStatus.BAD_REQUEST, {"ok": False, "error": endpoint_error}

    try:
        raw_code, used_provider, used_endpoint = generate_code_with_llm(
            provider_id=provider.id,
            api_key=api_key,
            base_url=base_url,
            endpoint=endpoint,
            model=model,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=prompt,
            temperature=temperature,
        )
        cleaned_code = extract_python_only(raw_code)
        patched_code, compatibility_notes = apply_runtime_compatibility_fixes(cleaned_code)
    except ValueError as exc:
        return HTTPStatus.BAD_REQUEST, {
            "ok": False,
            "error": str(exc),
        }
    except Exception as exc:
        return HTTPStatus.BAD_GATEWAY, {
            "ok": False,
            "error": "Model request failed.",
            "detail": str(exc),
        }

    return HTTPStatus.OK, {
        "ok": True,
        "provider": used_provider.id,
        "providerName": used_provider.name,
        "model": model,
        "endpoint": used_endpoint,
        "code": patched_code,
        "warnings": compatibility_notes,
        "compatibilityNotes": compatibility_notes,
        "sceneName": scene_name,
        "codeFile": "vercel-generated-code",
        "requestId": datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-vercel"),
        "rendered": False,
        "renderBackend": "external-required",
        "message": "Vercel 已生成 Manim 代码；视频渲染需要后端服务承载。",
    }


def build_index_html() -> str:
    local_web_app.provider_presets_for_ui = public_provider_config
    html = local_web_app.make_index_html()
    replacements = {
        "LOCAL · USER-KEY · RENDER": "VERCEL · USER-KEY · CODE",
        "用你的 Key + 自然语言问题，把抽象知识直接变成动态可视化视频。": (
            "用你的 Key + 自然语言问题，先生成 Manim 代码；完整视频渲染由独立后端承载。"
        ),
        "支持智谱、OpenAI-Compatible、本地 Codex 代理、MiniMax Token/Coding Plan。": (
            "支持可从云端访问的 OpenAI-Compatible、智谱、MiniMax 等模型服务。"
        ),
        "Key 仅用于本次请求，不写入仓库；本地代理如果不需要鉴权可以留空。": (
            "Key 仅用于本次请求，不写入仓库；云端无法访问你电脑上的 127.0.0.1 本地代理。"
        ),
        "使用本机 codex login 登录态，不需要在页面粘贴 API Key。": (
            "本机登录态 Provider 仅在本地 Aegis Web 可执行；Vercel 云端只展示能力入口。"
        ),
        "这个 Provider 允许无 Key，例如本地代理；如网关要求鉴权，也可以填写。": (
            "这个 Provider 可按网关要求选择是否填写 Key；云端只支持公网可访问服务。"
        ),
        '<input id="noRender" name="noRender" type="checkbox" />': (
            '<input id="noRender" name="noRender" type="checkbox" checked disabled />'
        ),
        "只生成代码，不渲染视频（调试模式）": "只生成代码，不渲染视频（Vercel 云端模式）",
        "Generate & Render": "Generate Code",
        "代码、修复提示、渲染视频统一展示。": "代码与兼容修复提示会在这里展示；视频渲染需要独立后端。",
    }
    for old, new in replacements.items():
        html = html.replace(old, new)
    return html


class handler(BaseHTTPRequestHandler):
    def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict[str, object]:
        raw_len = self.headers.get("Content-Length", "0")
        try:
            body_len = int(raw_len)
        except ValueError:
            return {}
        if body_len <= 0:
            return {}
        raw = self.rfile.read(body_len)
        parsed = json.loads(raw.decode("utf-8"))
        if not isinstance(parsed, dict):
            return {}
        return parsed

    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if route == "/":
            self._send_html(build_index_html())
            return
        if route == "/api/health":
            self._send_json(HTTPStatus.OK, build_health_payload())
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found."})

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if route == "/api/generate":
            try:
                payload = self._read_json_body()
            except Exception as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                return
            status, response = generate_manim_code_for_gateway(payload)
            self._send_json(HTTPStatus(status), response)
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found."})

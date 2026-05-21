from __future__ import annotations

import json
import ipaddress
import os
import socket
import sys
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse
from urllib import request as urllib_request

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
    load_dotenv,
    load_system_prompt,
)

# Load .env so trial provider keys and RENDER_BACKEND_URL are available
load_dotenv(PROJECT_ROOT / ".env")
import web_app as local_web_app  # noqa: E402

SYSTEM_PROMPT = load_system_prompt()
DISABLED_CLOUD_PROVIDERS = {"codex-cli", "codex-local-proxy"}
LOCAL_HOSTNAMES = {"localhost"}
MAX_PUBLIC_BODY_BYTES = 32_000
MAX_PUBLIC_PROMPT_CHARS = 4_000
PUBLIC_TRIAL_DEFAULT_PROVIDER = "trial-kimi-priority"
PUBLIC_TRIAL_PLANS = {
    "trial-kimi-priority": {
        "name": "免费试用 · Kimi 优先",
        "description": "内测免费额度：优先使用 Kimi，额度或调用失败时自动切换 MiniMax。",
        "model_label": "Kimi 优先 / MiniMax 备用",
        "attempts": (
            {
                "provider_id": "kimi-code",
                "env": "KIMI_CODE_API_KEY",
                "model": "kimi-for-coding",
            },
            {
                "provider_id": "minimax-coding-cn",
                "env": "MINIMAX_API_KEY",
                "model": "MiniMax-M2.7",
            },
        ),
    },
    "trial-minimax-direct": {
        "name": "免费试用 · MiniMax 稳定",
        "description": "内测免费额度：直接使用 MiniMax，适合较长或更稳的教学脚本生成。",
        "model_label": "MiniMax 稳定试用",
        "attempts": (
            {
                "provider_id": "minimax-coding-cn",
                "env": "MINIMAX_API_KEY",
                "model": "MiniMax-M2.7",
            },
        ),
    },
}
CLOUD_ENDPOINT_ERROR = (
    "Vercel 云端只支持公网 HTTPS 模型端点；本机、内网和 http:// 地址请在本地 Aegis Web 使用。"
)

# Render backend configuration
RENDER_BACKEND_URL = os.environ.get("RENDER_BACKEND_URL", "").rstrip("/")
RENDER_BACKEND_API_KEY = os.environ.get("RENDER_BACKEND_API_KEY", "").strip()


def _render_backend_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if RENDER_BACKEND_API_KEY:
        headers["X-API-Key"] = RENDER_BACKEND_API_KEY
    return headers


def _proxy_to_render_backend(path: str, method: str = "GET", payload: dict[str, object] | None = None, timeout: int = 15) -> tuple[int, dict[str, object]]:
    """Proxy a request to the render backend. Returns (http_status, json_body)."""
    if not RENDER_BACKEND_URL:
        return HTTPStatus.SERVICE_UNAVAILABLE, {
            "ok": False,
            "error": "渲染后端未配置。请设置 RENDER_BACKEND_URL 环境变量。",
        }
    url = f"{RENDER_BACKEND_URL}{path}"
    try:
        if method == "POST" and payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = urllib_request.Request(
                url, data=data, headers=_render_backend_headers(), method="POST"
            )
        else:
            req = urllib_request.Request(
                url, headers=_render_backend_headers(), method=method
            )
        with urllib_request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            status = resp.status
    except urllib_request.HTTPError as exc:
        body = exc.read().decode("utf-8")
        status = exc.code
    except Exception as exc:
        return HTTPStatus.BAD_GATEWAY, {
            "ok": False,
            "error": f"渲染后端连接失败: {exc}",
        }
    try:
        parsed = json.loads(body) if body else {}
    except json.JSONDecodeError:
        parsed = {"ok": False, "error": "渲染后端返回非 JSON 响应", "raw": body[:200]}
    return status, parsed


def _proxy_to_render_backend_raw(path: str, method: str = "GET", payload: dict[str, object] | None = None, timeout: int = 15) -> tuple[int, bytes, dict[str, str]]:
    """Proxy a request to the render backend and return raw bytes. Returns (http_status, body_bytes, headers_dict)."""
    if not RENDER_BACKEND_URL:
        return HTTPStatus.SERVICE_UNAVAILABLE, b"", {}
    url = f"{RENDER_BACKEND_URL}{path}"
    try:
        if method == "POST" and payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = urllib_request.Request(
                url, data=data, headers=_render_backend_headers(), method="POST"
            )
        else:
            req = urllib_request.Request(
                url, headers=_render_backend_headers(), method=method
            )
        with urllib_request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            status = resp.status
            headers = dict(resp.headers)
    except urllib_request.HTTPError as exc:
        body = exc.read()
        status = exc.code
        headers = dict(exc.headers)
    except Exception as exc:
        err_body = f"渲染后端连接失败: {exc}".encode("utf-8")
        return HTTPStatus.BAD_GATEWAY, err_body, {"content-type": "text/plain; charset=utf-8"}
    return status, body, headers


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
    providers = {
        provider_id: {
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
        for provider_id, plan in PUBLIC_TRIAL_PLANS.items()
    }
    return {
        "defaultProvider": PUBLIC_TRIAL_DEFAULT_PROVIDER,
        "regionLabels": {"trial": "内测免费试用"},
        "providerStorageKey": "aegis.provider.public.v3",
        "providers": providers,
    }


def read_server_key(env_name: str) -> str:
    return os.getenv(env_name, "").strip()


def build_request_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-vercel")


def sanitize_upstream_error(exc: Exception) -> str:
    text = str(exc)
    if "401" in text or "invalid" in text.lower() or "auth" in text.lower():
        return "auth"
    if "429" in text or "quota" in text.lower() or "rate" in text.lower():
        return "quota"
    return "request"


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


def generate_code_with_trial_plan(
    *,
    trial_provider_id: str,
    prompt: str,
    scene_name: str,
    temperature: float,
    request_id: str,
) -> tuple[int, dict[str, object]]:
    plan = PUBLIC_TRIAL_PLANS.get(trial_provider_id)
    if not plan:
        return HTTPStatus.BAD_REQUEST, {
            "ok": False,
            "error": "公开内测页只支持内置免费试用模型。",
            "requestId": request_id,
        }

    skipped: list[str] = []
    last_error: str | None = None
    for attempt in plan["attempts"]:
        env_name = str(attempt["env"])
        api_key = read_server_key(env_name)
        provider_id = str(attempt["provider_id"])
        provider = resolve_provider(provider_id)
        model = str(attempt["model"]) or provider.default_model or DEFAULT_MODEL
        if not api_key:
            skipped.append(provider.name)
            continue

        try:
            raw_code, _used_provider_name, _used_endpoint = generate_code_with_llm(
                provider_id=provider.id,
                api_key=api_key,
                base_url="",
                endpoint="",
                model=model,
                system_prompt=SYSTEM_PROMPT,
                user_prompt=prompt,
                temperature=temperature,
            )
            cleaned_code = extract_python_only(raw_code)
            patched_code, compatibility_notes = apply_runtime_compatibility_fixes(cleaned_code)
        except Exception as exc:
            last_error = sanitize_upstream_error(exc)
            print(
                f"[{request_id}] trial provider failed: {provider.id} reason={last_error}",
                file=sys.stderr,
            )
            continue

        warnings = list(compatibility_notes)
        if skipped:
            warnings.append("部分试用模型暂不可用，已自动使用可用的备用模型。")
        elif provider.id != str(plan["attempts"][0]["provider_id"]):
            warnings.append("Kimi 暂不可用，已自动切换到 MiniMax 备用模型。")

        return HTTPStatus.OK, {
            "ok": True,
            "provider": trial_provider_id,
            "providerName": str(plan["name"]),
            "model": str(plan["model_label"]),
            "endpoint": "server-managed-trial",
            "code": patched_code,
            "warnings": warnings,
            "compatibilityNotes": warnings,
            "sceneName": scene_name,
            "codeFile": "vercel-generated-code",
            "requestId": request_id,
            "rendered": False,
            "renderBackend": "external-required",
            "message": "内测免费试用已生成 Manim 代码；视频渲染需要后端服务承载。",
        }

    if skipped and last_error is None:
        print(
            f"[{request_id}] no trial provider keys configured: {', '.join(skipped)}",
            file=sys.stderr,
        )
    return HTTPStatus.SERVICE_UNAVAILABLE, {
        "ok": False,
        "error": "内测试用模型暂不可用，请稍后再试。",
        "requestId": request_id,
    }


def generate_manim_code_for_gateway(payload: dict[str, object]) -> tuple[int, dict[str, object]]:
    request_id = build_request_id()
    prompt = str(payload.get("prompt", "")).strip()
    if not prompt:
        return HTTPStatus.BAD_REQUEST, {"ok": False, "error": "请输入要讲清楚的问题。", "requestId": request_id}
    if len(prompt) > MAX_PUBLIC_PROMPT_CHARS:
        return HTTPStatus.BAD_REQUEST, {
            "ok": False,
            "error": f"问题太长了，请先压缩到 {MAX_PUBLIC_PROMPT_CHARS} 字以内。",
            "requestId": request_id,
        }

    provider_id = str(payload.get("provider", PUBLIC_TRIAL_DEFAULT_PROVIDER)).strip() or PUBLIC_TRIAL_DEFAULT_PROVIDER
    scene_name = local_web_app.safe_scene_name(str(payload.get("sceneName", "GeneratedScene")))
    temperature = clamp_temperature(payload.get("temperature", 0.2))
    if provider_id in PUBLIC_TRIAL_PLANS:
        return generate_code_with_trial_plan(
            trial_provider_id=provider_id,
            prompt=prompt,
            scene_name=scene_name,
            temperature=temperature,
            request_id=request_id,
        )

    return HTTPStatus.BAD_REQUEST, {
        "ok": False,
        "error": "公开内测页只支持内置免费试用模型。",
        "requestId": request_id,
    }


def generate_manim_code_with_client_provider(payload: dict[str, object]) -> tuple[int, dict[str, object]]:
    request_id = build_request_id()
    prompt = str(payload.get("prompt", "")).strip()
    if not prompt:
        return HTTPStatus.BAD_REQUEST, {"ok": False, "error": "请输入要讲清楚的问题。", "requestId": request_id}

    provider_id = str(payload.get("provider", DEFAULT_PROVIDER)).strip() or DEFAULT_PROVIDER
    if provider_id in DISABLED_CLOUD_PROVIDERS:
        return HTTPStatus.BAD_REQUEST, {
            "ok": False,
            "error": "这个 Provider 只能在本机使用，不能在 Vercel 云端运行。",
            "requestId": request_id,
        }

    provider = resolve_provider(provider_id)
    api_key = str(payload.get("apiKey", "")).strip()
    model = str(payload.get("model", "")).strip() or provider.default_model or DEFAULT_MODEL
    base_url = str(payload.get("baseUrl", "")).strip()
    endpoint = str(payload.get("endpoint", "")).strip()
    temperature = clamp_temperature(payload.get("temperature", 0.2))

    for field_name, raw_url in (("Base URL", base_url), ("Endpoint", endpoint)):
        endpoint_error = validate_cloud_model_endpoint(raw_url, field_name=field_name)
        if endpoint_error:
            return HTTPStatus.BAD_REQUEST, {"ok": False, "error": endpoint_error, "requestId": request_id}

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
            "requestId": request_id,
        }
    except Exception as exc:
        return HTTPStatus.BAD_GATEWAY, {
            "ok": False,
            "error": "Model request failed.",
            "requestId": request_id,
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
        "requestId": request_id,
        "rendered": False,
        "renderBackend": "external-required",
        "message": "Vercel 已生成 Manim 代码；视频渲染需要后端服务承载。",
    }


def build_index_html() -> str:
    local_web_app.provider_presets_for_ui = public_provider_config
    html = local_web_app.make_index_html()
    replacements = {
        "LOCAL · USER-KEY · RENDER": "VERCEL · FREE TRIAL · CODE",
        "用你的 Key + 自然语言问题，把抽象知识直接变成动态可视化视频。": (
            "内测阶段无需填写模型 Key，直接把自然语言问题变成 Manim 教学代码。"
        ),
        "Secure by design: API Key 仅用于本次请求，不落盘到仓库。": (
            "内测免费试用：Aegis 后端托管模型额度，页面不接收你的模型 Key。"
        ),
        "支持智谱、OpenAI-Compatible、本地 Codex 代理、MiniMax Token/Coding Plan。": (
            "当前提供 Kimi 优先与 MiniMax 稳定两种内测试用模型。"
        ),
        "Key 仅用于本次请求，不写入仓库；本地代理如果不需要鉴权可以留空。": (
            "内测阶段由 Aegis 承担模型调用额度；页面不会接收或保存你的模型 Key。"
        ),
        "使用本机 codex login 登录态，不需要在页面粘贴 API Key。": (
            "本机登录态 Provider 仅在本地 Aegis Web 可执行；Vercel 云端只展示能力入口。"
        ),
        "这个 Provider 允许无 Key，例如本地代理；如网关要求鉴权，也可以填写。": (
            "这个 Provider 可按网关要求选择是否填写 Key；云端只支持公网可访问服务。"
        ),
        "只生成代码，不渲染视频（调试模式）": "只生成代码，不渲染视频（关闭视频渲染）",
        "代码、修复提示、渲染视频统一展示。": "代码、修复提示与渲染视频统一展示。",
        'fetch("/api/generate/start"': 'fetch("/api/generate"',
        "await waitForJob(data.statusUrl, payload);": (
            'applyGenerateResult(data, payload, data.requestId || "-");'
        ),
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
        if body_len > MAX_PUBLIC_BODY_BYTES:
            raise ValueError("请求体太大，请缩短问题后再试。")
        if body_len <= 0:
            return {}
        raw = self.rfile.read(body_len)
        parsed = json.loads(raw.decode("utf-8"))
        if not isinstance(parsed, dict):
            return {}
        return parsed

    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if route == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if route == "/":
            self._send_html(build_index_html())
            return
        if route == "/api/health":
            self._send_json(HTTPStatus.OK, build_health_payload())
            return
        # Render proxy: status
        if route.startswith("/api/render/status/"):
            job_id = route.split("/api/render/status/", 1)[-1]
            status, response = _proxy_to_render_backend(f"/status/{job_id}")
            self._send_json(HTTPStatus(status), response)
            return
        # Render proxy: download (return redirect URL)
        if route.startswith("/api/render/download/"):
            job_id = route.split("/api/render/download/", 1)[-1]
            status, response = _proxy_to_render_backend(f"/download/{job_id}")
            self._send_json(HTTPStatus(status), response)
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found.", "path": route, "raw_path": self.path, "method": "POST"})

    def do_HEAD(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if route == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if route == "/":
            body = build_index_html().encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return
        self.send_response(HTTPStatus.NOT_FOUND)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        # 诊断：记录所有 POST 请求的路径信息
        print(f"[DEBUG] POST path={self.path!r} route={route!r}", file=sys.stderr)
        if route == "/api/generate":
            try:
                payload = self._read_json_body()
            except Exception as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                return
            status, response = generate_manim_code_for_gateway(payload)
            self._send_json(HTTPStatus(status), response)
            return
        if route == "/api/render" or route.startswith("/api/render/"):
            try:
                payload = self._read_json_body()
            except Exception as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                return
            # Validate
            code = str(payload.get("code", "")).strip()
            scene_name = str(payload.get("sceneName", "GeneratedScene")).strip()
            if not code:
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "缺少 code 字段"})
                return
            # Proxy to render backend async endpoint
            status, response = _proxy_to_render_backend(
                "/render-async",
                method="POST",
                payload={"code": code, "scene_name": scene_name},
                timeout=15,
            )
            self._send_json(HTTPStatus(status), response)
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found."})

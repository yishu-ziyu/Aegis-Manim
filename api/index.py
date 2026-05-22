from __future__ import annotations

import json
import ipaddress
import os
import socket
import sys
import time
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
MAX_PUBLIC_RENDER_PLAYS = 14
MAX_PUBLIC_RENDER_WAITS = 12
MAX_PUBLIC_LAGGED_STARTS = 2
PUBLIC_TRIAL_MODEL_TIMEOUT_SECONDS = int(os.environ.get("PUBLIC_TRIAL_MODEL_TIMEOUT_SECONDS", "45"))
PUBLIC_TRIAL_REPAIR_TIMEOUT_SECONDS = int(os.environ.get("PUBLIC_TRIAL_REPAIR_TIMEOUT_SECONDS", "25"))
PUBLIC_TRIAL_DEFAULT_PROVIDER = "trial-minimax-direct"
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
    """Proxy a request to the render backend. Returns (http_status, json_body).

    If the first attempt fails due to a connection error (e.g. Render free tier
    instance is spun down), we send a wake-up ping, wait briefly, and retry once.
    """
    if not RENDER_BACKEND_URL:
        return HTTPStatus.SERVICE_UNAVAILABLE, {
            "ok": False,
            "error": "渲染后端未配置。请设置 RENDER_BACKEND_URL 环境变量。",
        }

    def _try_once() -> tuple[int, str] | None:
        """Return (status, body) on success, None on connection failure."""
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
                return resp.status, resp.read().decode("utf-8")
        except urllib_request.HTTPError as exc:
            # HTTP error means the instance is up but returned an error status
            return exc.code, exc.read().decode("utf-8")
        except (urllib_request.URLError, socket.error, TimeoutError, OSError):
            # Connection-level error: instance is likely spun down
            return None
        except Exception:
            # Unexpected error, treat as connection failure for retry purposes
            return None

    # First attempt
    result = _try_once()

    # If connection failed, wake up the instance and retry once
    if result is None:
        print("[Render] Connection failed, instance may be cold. Sending wake-up ping...", file=sys.stderr)
        # Fire-and-forget wake-up request (ignore any response)
        try:
            ping_url = f"{RENDER_BACKEND_URL}/health"
            ping_req = urllib_request.Request(
                ping_url, headers=_render_backend_headers(), method="GET"
            )
            urllib_request.urlopen(ping_req, timeout=5)
        except Exception:
            pass  # Wake-up pings are best-effort

        # Wait for Render free tier to cold-start (typically 30-60s, but 10s is often enough for the HTTP layer)
        time.sleep(10)

        print("[Render] Retrying original request after wake-up...", file=sys.stderr)
        result = _try_once()

    if result is None:
        return HTTPStatus.BAD_GATEWAY, {
            "ok": False,
            "error": "渲染后端连接失败：实例可能正在冷启动，请稍后再试。",
        }

    status, body = result
    try:
        parsed = json.loads(body) if body else {}
    except json.JSONDecodeError:
        parsed = {"ok": False, "error": "渲染后端返回非 JSON 响应", "raw": body[:200]}
    return status, parsed


def _proxy_to_render_backend_raw(path: str, method: str = "GET", payload: dict[str, object] | None = None, timeout: int = 15) -> tuple[int, bytes, dict[str, str]]:
    """Proxy a request to the render backend and return raw bytes. Returns (http_status, body_bytes, headers_dict).

    If the first attempt fails due to a connection error (e.g. Render free tier
    instance is spun down), we send a wake-up ping, wait briefly, and retry once.
    """
    if not RENDER_BACKEND_URL:
        return HTTPStatus.SERVICE_UNAVAILABLE, b"", {}

    def _try_once_raw() -> tuple[int, bytes, dict[str, str]] | None:
        """Return (status, body, headers) on success, None on connection failure."""
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
                return resp.status, resp.read(), dict(resp.headers)
        except urllib_request.HTTPError as exc:
            return exc.code, exc.read(), dict(exc.headers)
        except (urllib_request.URLError, socket.error, TimeoutError, OSError):
            return None
        except Exception:
            return None

    result = _try_once_raw()

    if result is None:
        print("[RenderRaw] Connection failed, instance may be cold. Sending wake-up ping...", file=sys.stderr)
        try:
            ping_url = f"{RENDER_BACKEND_URL}/health"
            ping_req = urllib_request.Request(
                ping_url, headers=_render_backend_headers(), method="GET"
            )
            urllib_request.urlopen(ping_req, timeout=5)
        except Exception:
            pass
        time.sleep(10)
        print("[RenderRaw] Retrying original request after wake-up...", file=sys.stderr)
        result = _try_once_raw()

    if result is None:
        err_body = "渲染后端连接失败：实例可能正在冷启动，请稍后再试。".encode("utf-8")
        return HTTPStatus.BAD_GATEWAY, err_body, {"content-type": "text/plain; charset=utf-8"}

    return result


def _extract_download_video_url(payload: dict[str, object]) -> str | None:
    video_url = payload.get("video_url")
    if not isinstance(video_url, str):
        return None
    parsed = urlparse(video_url)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        return None
    return video_url


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
        "providerStorageKey": "aegis.provider.public.v4",
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


def render_budget_warnings(code: str) -> list[str]:
    warnings: list[str] = []
    play_count = code.count("self.play(")
    wait_count = code.count("self.wait(")
    lagged_count = code.count("LaggedStart(")
    if play_count > MAX_PUBLIC_RENDER_PLAYS:
        warnings.append(f"self.play count {play_count} exceeds hosted budget {MAX_PUBLIC_RENDER_PLAYS}")
    if wait_count > MAX_PUBLIC_RENDER_WAITS:
        warnings.append(f"self.wait count {wait_count} exceeds hosted budget {MAX_PUBLIC_RENDER_WAITS}")
    if lagged_count > MAX_PUBLIC_LAGGED_STARTS:
        warnings.append(f"LaggedStart count {lagged_count} exceeds hosted budget {MAX_PUBLIC_LAGGED_STARTS}")
    return warnings


def hosted_render_budget_prompt(prompt: str, warnings: list[str]) -> str:
    return "\n".join(
        [
            prompt,
            "",
            "Hosted render budget correction:",
            "; ".join(warnings),
            "Regenerate the complete Manim Python file as a reliable segmented-render scene.",
            "Hard limits: at most 14 self.play(...) calls, at most 12 self.wait(...) calls, at most 2 LaggedStart(...).",
            "No dense object swarms, no loops containing self.play/self.wait, no long wait chains, no more than 8 visible text labels at once.",
            "Target video length: 20-45 seconds. Prefer a clear 4-step explanation over a long lecture.",
        ]
    )


def build_fallback_manim_code(prompt: str, scene_name: str) -> str:
    """Return a deterministic Manim scene when trial model providers are slow/unavailable."""
    safe_scene_name = local_web_app.safe_scene_name(scene_name)
    compact = " ".join(prompt.split())[:28] or "抽象概念"
    if "帕累托" in prompt or "Pareto" in prompt or "pareto" in prompt:
        return f'''from manim import *

class {safe_scene_name}(Scene):
    def construct(self):
        self.camera.background_color = "#0f172a"
        title = Text("帕累托最优", font_size=38, color=YELLOW).to_edge(UP)
        subtitle = Text("不能让一人更好，而不让他人更差", font_size=22, color=GREY_B).next_to(title, DOWN, buff=0.22)
        axes = Axes(
            x_range=[0, 5, 1],
            y_range=[0, 5, 1],
            x_length=5.8,
            y_length=4.2,
            tips=False,
            axis_config={{"include_numbers": False, "color": GREY_B}},
        ).shift(DOWN * 0.35)
        x_label = Text("Alice收益", font_size=18, color=BLUE).next_to(axes.x_axis, RIGHT, buff=0.18)
        y_label = Text("Bob收益", font_size=18, color=GREEN).next_to(axes.y_axis, UP, buff=0.18)
        feasible = Polygon(
            axes.c2p(0.5, 0.7),
            axes.c2p(4.4, 0.8),
            axes.c2p(4.1, 2.3),
            axes.c2p(3.0, 3.5),
            axes.c2p(1.2, 3.8),
            axes.c2p(0.5, 0.7),
            color=TEAL,
            fill_opacity=0.18,
            stroke_width=3,
        )
        start = Dot(axes.c2p(1.3, 1.2), color=RED)
        better = Dot(axes.c2p(2.8, 2.6), color=BLUE)
        frontier = VMobject(color=YELLOW, stroke_width=6).set_points_smoothly([
            axes.c2p(1.2, 3.8),
            axes.c2p(2.2, 3.75),
            axes.c2p(3.0, 3.5),
            axes.c2p(3.7, 2.95),
            axes.c2p(4.1, 2.3),
        ])
        arrow = Arrow(start.get_center(), better.get_center(), buff=0.18, color=WHITE)
        note1 = Text("内部点：还能一起变好", font_size=22, color=WHITE).to_edge(DOWN)
        note2 = Text("前沿点：改进会带来代价", font_size=22, color=YELLOW).to_edge(DOWN)
        final = Text("最优不是总量最大，而是没有无损改进", font_size=22, color=GREEN).to_edge(DOWN)

        self.play(FadeIn(title), FadeIn(subtitle, shift=DOWN), run_time=0.8)
        self.wait(0.5)
        self.play(Create(axes), FadeIn(VGroup(x_label, y_label)), run_time=1.0)
        self.wait(0.4)
        self.play(FadeIn(feasible), FadeIn(start), Write(note1), run_time=1.0)
        self.wait(0.7)
        self.play(Create(arrow), TransformFromCopy(start, better), run_time=1.1)
        self.wait(0.5)
        self.play(FadeOut(note1), Create(frontier), Write(note2), run_time=1.1)
        self.wait(0.8)
        self.play(Indicate(frontier), ReplacementTransform(note2, final), run_time=1.0)
        self.wait(1.2)
'''
    title = compact[:12]
    labels = ["问题", "变量", "关系", "变化", "结论"]
    title_literal = json.dumps(title, ensure_ascii=False)
    subtitle_literal = json.dumps(compact, ensure_ascii=False)
    labels_literal = ", ".join(json.dumps(label, ensure_ascii=False) for label in labels)
    return f'''from manim import *

class {safe_scene_name}(Scene):
    def construct(self):
        self.camera.background_color = "#0f172a"
        title = Text({title_literal}, font_size=36, color=YELLOW).to_edge(UP)
        subtitle = Text({subtitle_literal}, font_size=20, color=GREY_B).next_to(title, DOWN, buff=0.25)
        frame = RoundedRectangle(width=7.4, height=3.0, corner_radius=0.12, color=GREY_B, stroke_opacity=0.55)
        axis = NumberLine(x_range=[0, 5, 1], length=6.4, color=GREY_B).shift(DOWN * 1.15)
        dot = Dot(axis.n2p(0), color=BLUE)
        labels = VGroup(*[
            Text(text, font_size=22, color=WHITE)
            for text in [{labels_literal}]
        ]).arrange(RIGHT, buff=0.58).next_to(axis, UP, buff=0.55)
        arrows = VGroup(*[
            Arrow(labels[i].get_right(), labels[i + 1].get_left(), buff=0.12, color=TEAL, stroke_width=3)
            for i in range(len(labels) - 1)
        ])
        question = Text("先看什么在变，再看什么不变", font_size=22, color=WHITE).move_to(frame.get_top() + DOWN * 0.65)
        conclusion = Text("把抽象问题拆成可观察步骤", font_size=24, color=GREEN).to_edge(DOWN)

        self.play(FadeIn(title), FadeIn(subtitle, shift=DOWN), run_time=0.4)
        self.wait(0.4)
        self.play(Create(frame), Write(question), run_time=0.8)
        self.wait(0.5)
        self.play(Create(axis), FadeIn(dot), FadeIn(labels, shift=UP * 0.2), run_time=0.9)
        self.wait(0.5)
        self.play(Create(arrows), dot.animate.move_to(axis.n2p(5)), run_time=1.0)
        self.wait(0.6)
        self.play(FadeIn(conclusion, shift=UP), Indicate(labels[-1]), run_time=0.9)
        self.wait(1.0)
'''


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
                timeout=PUBLIC_TRIAL_MODEL_TIMEOUT_SECONDS,
            )
            cleaned_code = extract_python_only(raw_code)
            patched_code, compatibility_notes = apply_runtime_compatibility_fixes(cleaned_code)
            budget_notes = render_budget_warnings(patched_code)
            if budget_notes:
                raw_code, _used_provider_name, _used_endpoint = generate_code_with_llm(
                    provider_id=provider.id,
                    api_key=api_key,
                    base_url="",
                    endpoint="",
                    model=model,
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=hosted_render_budget_prompt(prompt, budget_notes),
                    temperature=min(temperature, 0.2),
                    timeout=PUBLIC_TRIAL_REPAIR_TIMEOUT_SECONDS,
                )
                cleaned_code = extract_python_only(raw_code)
                patched_code, compatibility_notes = apply_runtime_compatibility_fixes(cleaned_code)
                budget_notes = render_budget_warnings(patched_code)
                if budget_notes:
                    last_error = "budget"
                    print(
                        f"[{request_id}] trial provider exceeded render budget after repair: {provider.id}",
                        file=sys.stderr,
                    )
                    continue
            detected_scene_name = local_web_app.detect_scene_name(patched_code, scene_name)
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
            "sceneName": detected_scene_name,
            "sceneNameInput": scene_name,
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
    fallback_code = build_fallback_manim_code(prompt, scene_name)
    fallback_code, compatibility_notes = apply_runtime_compatibility_fixes(fallback_code)
    warnings = [
        "内测试用模型响应较慢或暂不可用，已自动切换到稳定模板生成，视频仍会继续渲染。",
        *compatibility_notes,
    ]
    detected_scene_name = local_web_app.detect_scene_name(fallback_code, scene_name)
    return HTTPStatus.OK, {
        "ok": True,
        "provider": trial_provider_id,
        "providerName": str(plan["name"]),
        "model": "stable-template-fallback",
        "endpoint": "server-managed-fallback",
        "code": fallback_code,
        "warnings": warnings,
        "compatibilityNotes": warnings,
        "sceneName": detected_scene_name,
        "sceneNameInput": scene_name,
        "codeFile": "vercel-generated-fallback",
        "requestId": request_id,
        "rendered": False,
        "renderBackend": "external-required",
        "message": "模型接口暂慢，已使用稳定模板生成 Manim 代码并继续云端渲染。",
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
            timeout=PUBLIC_TRIAL_MODEL_TIMEOUT_SECONDS,
        )
        cleaned_code = extract_python_only(raw_code)
        patched_code, compatibility_notes = apply_runtime_compatibility_fixes(cleaned_code)
        detected_scene_name = local_web_app.detect_scene_name(patched_code, scene_name)
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
        "sceneName": detected_scene_name,
        "sceneNameInput": scene_name,
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
            video_url = _extract_download_video_url(response)
            if status == HTTPStatus.OK and video_url:
                self.send_response(HTTPStatus.FOUND)
                self.send_header("Location", video_url)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
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
            render_mode = str(payload.get("renderMode", payload.get("render_mode", "auto"))).strip() or "auto"
            if not code:
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "缺少 code 字段"})
                return
            code, _notes = apply_runtime_compatibility_fixes(code)
            scene_name = local_web_app.detect_scene_name(code, scene_name)
            # Proxy to render backend async endpoint
            status, response = _proxy_to_render_backend(
                "/render-async",
                method="POST",
                payload={"code": code, "scene_name": scene_name, "render_mode": render_mode},
                timeout=15,
            )
            self._send_json(HTTPStatus(status), response)
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found."})

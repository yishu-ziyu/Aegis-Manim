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
    PROVIDER_PRESETS,
    generate_code_with_provider,
    is_local_only_provider,
    provider_presets_for_ui,
    redact_client_secrets,
    resolve_provider,
)
from alignment import generate_alignment  # noqa: E402
from manim_agent import (  # noqa: E402
    apply_runtime_compatibility_fixes,
    extract_python_only,
    generate_code_with_llm,
    is_placeholder_api_key,
    load_dotenv,
    load_system_prompt,
)
from manim_knowledge import precheck_manim_code, summarize_precheck_for_prompt  # noqa: E402
from vision_analysis import (  # noqa: E402
    MAX_VISION_REQUEST_BYTES,
    analyze_image_payload,
    disabled_vision_response,
    is_vision_public_enabled,
)

# Load .env so trial provider keys and RENDER_BACKEND_URL are available
load_dotenv(PROJECT_ROOT / ".env")
import web_app as local_web_app  # noqa: E402

SYSTEM_PROMPT = load_system_prompt()
DISABLED_CLOUD_PROVIDERS = {"codex-cli", "codex-local-proxy"}
LOCAL_HOSTNAMES = {"localhost"}
MAX_PUBLIC_BODY_BYTES = 32_000
MAX_PUBLIC_PROMPT_CHARS = 4_000
MAX_PUBLIC_RENDER_PLAYS = 24
MAX_PUBLIC_RENDER_WAITS = 20
MAX_PUBLIC_LAGGED_STARTS = 4
MAX_PUBLIC_RENDER_HARD_PLAYS = 40
MAX_PUBLIC_RENDER_HARD_WAITS = 32
MAX_PUBLIC_HARD_LAGGED_STARTS = 8
PUBLIC_RENDER_RISKY_PATTERNS = (
    ("LaggedStart(", "LaggedStart can create slow segmented-render chunks"),
    ("BraceLabel(", "BraceLabel can be slow or brittle on hosted segmented rendering"),
)
PUBLIC_CHINESE_SCENE_CONTRACT = (
    "Chinese-first visible text contract:",
    "All visible Text(...) titles, captions, axis explanations, step labels, and conclusions must be Chinese by default unless the user explicitly asks for another language.",
    "If the internal draft uses English, translate it before putting text into Text(...); do not leave English prose such as Demand, Supply, Tax Revenue, or Deadweight Loss on screen.",
    "Compact symbols are allowed, but pair them with Chinese labels: 价格 P, 数量 Q, 需求 D, 供给 S, 边际成本 MC, 边际收益 MR.",
    "Keep each Chinese Text line short, ideally 8 Chinese characters or fewer; split longer explanations into VGroup rows and call scale_to_fit_width when needed.",
    "For Chinese captions, do not Transform or ReplacementTransform one sentence into another; FadeOut the old caption, then FadeIn the new caption to avoid transient mixed glyphs.",
    "Do not pass arbitrary font= values into Text; the runtime injects a CJK-capable default font.",
)
PUBLIC_TRIAL_MODEL_TIMEOUT_SECONDS = int(os.environ.get("PUBLIC_TRIAL_MODEL_TIMEOUT_SECONDS", "45"))
PUBLIC_TRIAL_REPAIR_TIMEOUT_SECONDS = int(os.environ.get("PUBLIC_TRIAL_REPAIR_TIMEOUT_SECONDS", "25"))
PUBLIC_TRIAL_KIMI_TIMEOUT_SECONDS = int(
    os.environ.get("PUBLIC_TRIAL_KIMI_TIMEOUT_SECONDS", os.environ.get("PUBLIC_TRIAL_MODEL_TIMEOUT_SECONDS", "55"))
)
PUBLIC_TRIAL_MINIMAX_TIMEOUT_SECONDS = int(
    os.environ.get("PUBLIC_TRIAL_MINIMAX_TIMEOUT_SECONDS", os.environ.get("PUBLIC_TRIAL_MODEL_TIMEOUT_SECONDS", "150"))
)
PUBLIC_TRIAL_DEEPSEEK_TIMEOUT_SECONDS = int(
    os.environ.get("PUBLIC_TRIAL_DEEPSEEK_TIMEOUT_SECONDS", os.environ.get("PUBLIC_TRIAL_MODEL_TIMEOUT_SECONDS", "90"))
)
PUBLIC_TRIAL_KIMI_REPAIR_TIMEOUT_SECONDS = int(
    os.environ.get("PUBLIC_TRIAL_KIMI_REPAIR_TIMEOUT_SECONDS", os.environ.get("PUBLIC_TRIAL_REPAIR_TIMEOUT_SECONDS", "35"))
)
PUBLIC_TRIAL_MINIMAX_REPAIR_TIMEOUT_SECONDS = int(
    os.environ.get("PUBLIC_TRIAL_MINIMAX_REPAIR_TIMEOUT_SECONDS", os.environ.get("PUBLIC_TRIAL_REPAIR_TIMEOUT_SECONDS", "90"))
)
PUBLIC_TRIAL_DEEPSEEK_REPAIR_TIMEOUT_SECONDS = int(
    os.environ.get("PUBLIC_TRIAL_DEEPSEEK_REPAIR_TIMEOUT_SECONDS", os.environ.get("PUBLIC_TRIAL_REPAIR_TIMEOUT_SECONDS", "60"))
)
PUBLIC_TRIAL_MIMO_TIMEOUT_SECONDS = int(
    os.environ.get("PUBLIC_TRIAL_MIMO_TIMEOUT_SECONDS", os.environ.get("PUBLIC_TRIAL_MODEL_TIMEOUT_SECONDS", "150"))
)
PUBLIC_TRIAL_MIMO_REPAIR_TIMEOUT_SECONDS = int(
    os.environ.get("PUBLIC_TRIAL_MIMO_REPAIR_TIMEOUT_SECONDS", os.environ.get("PUBLIC_TRIAL_REPAIR_TIMEOUT_SECONDS", "60"))
)
PUBLIC_TRIAL_DEFAULT_PROVIDER = "trial-minimax-direct"
PUBLIC_TRIAL_PLANS = {
    "trial-minimax-direct": {
        "name": "免费试用 · MiniMax M3",
        "description": "内测免费额度：直接使用 MiniMax M3，作为默认教学脚本生成模型。",
        "model_label": "MiniMax M3 试用",
        "attempts": (
            {
                "provider_id": "minimax-coding-cn",
                "env": "MINIMAX_API_KEY",
                "model": "MiniMax-M3",
            },
        ),
    },
    "trial-mimo-direct": {
        "name": "免费试用 · Mimo 编程",
        "description": "内测免费额度：直接使用 Mimo Token Plan 生成教学脚本。",
        "model_label": "Mimo 编程试用",
        "attempts": (
            {
                "provider_id": "mimo",
                "env": "MIMO_API_KEY",
                "model": "mimo-v2.5-pro",
                "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
            },
        ),
    },
}
CLOUD_ENDPOINT_ERROR = (
    "Vercel 云端只支持公网 HTTPS 模型端点；本机、内网和 http:// 地址请在本地 Aegis Web 使用。"
)
UNKNOWN_TRIAL_ERROR = "这个试用模型已下线，请改用当前免费试用或自带密钥。"
UNKNOWN_PROVIDER_ERROR = "未知的模型服务。请选择免费试用，或使用自带密钥的公开 Provider。"
LOCAL_ONLY_PROVIDER_ERROR = "这个 Provider 只能在本机使用，不能在 Vercel 云端运行。"
BYOK_CUSTOM_URL_REQUIRED_ERROR = "自定义 Provider 需要填写可公网访问的 HTTPS Base URL。"
BYOK_PLACEHOLDER_KEY_ERROR = "请粘贴真实 API Key，不要填环境变量名或示例占位符。"
BYOK_TRIAL_PREFLIGHT_ERROR = "免费试用无需测试密钥。请改用自带密钥模式。"
BYOK_PREFLIGHT_TIMEOUT_SECONDS = 20
BYOK_PREFLIGHT_MAX_TOKENS = 16

# Render backend configuration
RENDER_BACKEND_URL = os.environ.get("RENDER_BACKEND_URL", "").rstrip("/")
RENDER_BACKEND_API_KEY = os.environ.get("RENDER_BACKEND_API_KEY", "").strip()
RENDER_BACKEND_RETRYABLE_STATUS = {502, 503, 504}


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

    retries = max(0, int(os.environ.get("RENDER_BACKEND_RETRIES", "2")))
    wakeup_wait = max(0.0, float(os.environ.get("RENDER_BACKEND_WAKEUP_WAIT_SECONDS", "12")))
    result: tuple[int, str] | None = None
    last_status: int | None = None
    last_body = ""

    for attempt in range(retries + 1):
        result = _try_once()
        if result is not None:
            last_status, last_body = result
            if last_status not in RENDER_BACKEND_RETRYABLE_STATUS or attempt >= retries:
                break

        reason = "connection failed" if result is None else f"status={last_status}"
        print(f"[Render] {reason}, sending wake-up ping before retry...", file=sys.stderr)
        try:
            ping_url = f"{RENDER_BACKEND_URL}/health"
            ping_req = urllib_request.Request(
                ping_url, headers=_render_backend_headers(), method="GET"
            )
            urllib_request.urlopen(ping_req, timeout=5)
        except Exception:
            pass

        if attempt < retries:
            time.sleep(wakeup_wait * (attempt + 1))
            print("[Render] Retrying original request after wake-up...", file=sys.stderr)

    if result is None:
        return HTTPStatus.BAD_GATEWAY, {
            "ok": False,
            "error": "渲染后端连接失败：实例可能正在冷启动，请稍后再试。",
        }

    status, body = result if result is not None else (last_status or HTTPStatus.BAD_GATEWAY, last_body)
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

    retries = max(0, int(os.environ.get("RENDER_BACKEND_RETRIES", "2")))
    wakeup_wait = max(0.0, float(os.environ.get("RENDER_BACKEND_WAKEUP_WAIT_SECONDS", "12")))
    result: tuple[int, bytes, dict[str, str]] | None = None
    last_status: int | None = None
    for attempt in range(retries + 1):
        result = _try_once_raw()
        if result is not None:
            last_status = result[0]
            if last_status not in RENDER_BACKEND_RETRYABLE_STATUS or attempt >= retries:
                break

        reason = "connection failed" if result is None else f"status={last_status}"
        print(f"[RenderRaw] {reason}, sending wake-up ping before retry...", file=sys.stderr)
        try:
            ping_url = f"{RENDER_BACKEND_URL}/health"
            ping_req = urllib_request.Request(
                ping_url, headers=_render_backend_headers(), method="GET"
            )
            urllib_request.urlopen(ping_req, timeout=5)
        except Exception:
            pass
        if attempt < retries:
            time.sleep(wakeup_wait * (attempt + 1))
            print("[RenderRaw] Retrying original request after wake-up...", file=sys.stderr)

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
        "trialProviders": {
            "defaultProvider": PUBLIC_TRIAL_DEFAULT_PROVIDER,
            "configured": {
                "miniMax": bool(read_server_key("MINIMAX_API_KEY")),
                "mimo": bool(read_server_key("MIMO_API_KEY")),
            },
            "timeouts": {
                "miniMax": PUBLIC_TRIAL_MINIMAX_TIMEOUT_SECONDS,
                "miniMaxRepair": PUBLIC_TRIAL_MINIMAX_REPAIR_TIMEOUT_SECONDS,
                "mimo": PUBLIC_TRIAL_MIMO_TIMEOUT_SECONDS,
                "mimoRepair": PUBLIC_TRIAL_MIMO_REPAIR_TIMEOUT_SECONDS,
            },
        },
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


def public_byok_providers() -> dict[str, dict[str, object]]:
    source = provider_presets_for_ui()
    providers: dict[str, dict[str, object]] = {}
    for provider_id, preset in source["providers"].items():
        if is_local_only_provider(provider_id):
            continue
        providers[provider_id] = {
            **preset,
            "byok": True,
            "serverManaged": False,
            "hideApiKey": False,
            "hideBaseUrl": False,
            "lockModel": False,
            "localOnly": False,
            "displayProtocol": "自带密钥",
            "description": (
                f"{preset['name']} · 使用你自己的 Key，只存在这台浏览器，"
                "生成时才发给对应模型服务。"
            ),
        }
    return providers


def public_provider_config() -> dict[str, object]:
    trial_providers = {
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
            "byok": False,
            "displayProtocol": "免费试用",
            "description": plan["description"],
        }
        for provider_id, plan in PUBLIC_TRIAL_PLANS.items()
    }
    return {
        "defaultProvider": PUBLIC_TRIAL_DEFAULT_PROVIDER,
        "defaultMode": "trial",
        "cloudMode": True,
        "directGenerate": True,
        "regionLabels": {
            "trial": "内测免费试用",
            "global": "海外 / 原生厂商",
            "cn": "国内直连",
            "coding": "Token Plan / Coding Plan",
            "custom": "自定义",
        },
        "providerStorageKey": "aegis.provider.public.v5",
        "providers": {**trial_providers, **public_byok_providers()},
    }


def read_server_key(env_name: str) -> str:
    return os.getenv(env_name, "").strip()


def build_request_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-vercel")


def sanitize_upstream_error(exc: Exception) -> str:
    text = str(exc)
    if "401" in text or "invalid" in text.lower() or "auth" in text.lower():
        return "auth"
    if "402" in text or "balance" in text.lower() or "billing" in text.lower():
        return "billing"
    if "403" in text or "access" in text.lower() or "terminated" in text.lower():
        return "access"
    if "429" in text or "quota" in text.lower() or "rate" in text.lower():
        return "quota"
    if "timeout" in text.lower() or "timed out" in text.lower() or "504" in text:
        return "timeout"
    if "503" in text or "overload" in text.lower() or "busy" in text.lower():
        return "overloaded"
    return "request"


def describe_trial_failure(category: str) -> str:
    if category == "access":
        return "权限/白名单/套餐额度问题"
    if category == "auth":
        return "Key 无效或鉴权失败"
    if category == "billing":
        return "余额或计费不可用"
    if category == "quota":
        return "额度耗尽或限流"
    if category == "timeout":
        return "请求超时"
    if category == "overloaded":
        return "服务繁忙"
    if category == "precheck":
        return "代码预检未通过"
    if category == "budget":
        return "渲染预算超限"
    return category


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
    for pattern, message in PUBLIC_RENDER_RISKY_PATTERNS:
        if pattern in code:
            warnings.append(message)
    return warnings


def render_hard_budget_warnings(code: str) -> list[str]:
    warnings: list[str] = []
    play_count = code.count("self.play(")
    wait_count = code.count("self.wait(")
    lagged_count = code.count("LaggedStart(")
    if play_count > MAX_PUBLIC_RENDER_HARD_PLAYS:
        warnings.append(f"self.play count {play_count} exceeds hard render budget {MAX_PUBLIC_RENDER_HARD_PLAYS}")
    if wait_count > MAX_PUBLIC_RENDER_HARD_WAITS:
        warnings.append(f"self.wait count {wait_count} exceeds hard render budget {MAX_PUBLIC_RENDER_HARD_WAITS}")
    if lagged_count > MAX_PUBLIC_HARD_LAGGED_STARTS:
        warnings.append(f"LaggedStart count {lagged_count} exceeds hard render budget {MAX_PUBLIC_HARD_LAGGED_STARTS}")
    return warnings


def hosted_render_budget_prompt(prompt: str, warnings: list[str]) -> str:
    return "\n".join(
        [
            prompt,
            "",
            "Hosted render budget correction:",
            "; ".join(warnings),
            "Regenerate the complete Manim Python file as a reliable segmented-render scene.",
            f"Hard limits: at most {MAX_PUBLIC_RENDER_PLAYS} self.play(...) calls, at most {MAX_PUBLIC_RENDER_WAITS} self.wait(...) calls, at most {MAX_PUBLIC_LAGGED_STARTS} LaggedStart(...).",
            "No dense object swarms, no loops containing self.play/self.wait, no long wait chains, no LaggedStart, no BraceLabel, no more than 8 visible text labels at once.",
            "Target video length: 45-120 seconds when the renderer can segment the scene. Prefer clear visual beats over a dense lecture.",
            *PUBLIC_CHINESE_SCENE_CONTRACT,
        ]
    )


def trial_generation_prompt(prompt: str) -> str:
    lines = [prompt, "", local_web_app.build_teaching_brief(prompt)]
    try:
        if not local_web_app.is_complex_learning_prompt(prompt):
            lines.append("简短问题也按教学 brief 输出，避免退化成占位动画。")
    except Exception:
        pass
    lines.extend(
        [
            "",
            "Public hosted quality contract:",
            "Return only a complete Manim Python file. No Markdown fences or prose.",
            "Make a high-quality teaching scene, not a placeholder: 4-6 visual beats, 8-14 self.play calls, clear diagrams, short Chinese labels.",
            "Use Text instead of Tex/MathTex. Keep labels inside the frame and avoid dense paragraphs.",
            "Prefer Axes, Line, Dot, Polygon, Arrow, VGroup, FadeIn/FadeOut/ReplacementTransform for reliable rendering.",
            "Avoid hosted-render slow paths: no LaggedStart, no BraceLabel, no dense brace annotations, no animation loops.",
            "Use supported Manim Community APIs: place graph points through axes.c2p(...), pass axis labels through get_axis_labels(Text(...), Text(...)), and do not pass x_label/y_label into Axes(...).",
            "For economics diagrams, draw the economic object itself: curves, equilibrium dots, dashed projection lines, arrows, and surplus/profit/deadweight-loss areas with Polygon.",
            "Every Text(...) must set font_size; no more than 8 visible labels at once; remove old explanation text before adding new explanation text.",
            *PUBLIC_CHINESE_SCENE_CONTRACT,
        ]
    )
    return "\n".join(lines)


def trial_timeout_seconds(provider_id: str, *, repair: bool = False) -> int:
    if provider_id == "kimi-code":
        return PUBLIC_TRIAL_KIMI_REPAIR_TIMEOUT_SECONDS if repair else PUBLIC_TRIAL_KIMI_TIMEOUT_SECONDS
    if provider_id == "deepseek":
        return PUBLIC_TRIAL_DEEPSEEK_REPAIR_TIMEOUT_SECONDS if repair else PUBLIC_TRIAL_DEEPSEEK_TIMEOUT_SECONDS
    if provider_id.startswith("minimax"):
        return PUBLIC_TRIAL_MINIMAX_REPAIR_TIMEOUT_SECONDS if repair else PUBLIC_TRIAL_MINIMAX_TIMEOUT_SECONDS
    if provider_id == "mimo":
        return PUBLIC_TRIAL_MIMO_REPAIR_TIMEOUT_SECONDS if repair else PUBLIC_TRIAL_MIMO_TIMEOUT_SECONDS
    return PUBLIC_TRIAL_REPAIR_TIMEOUT_SECONDS if repair else PUBLIC_TRIAL_MODEL_TIMEOUT_SECONDS


def trial_precheck_repair_prompt(prompt: str, code: str, issues: list[object]) -> str:
    precheck_summary = summarize_precheck_for_prompt(issues)  # type: ignore[arg-type]
    return "\n".join(
        [
            trial_generation_prompt(prompt),
            "",
            "The previous generated code failed the pre-render quality gate.",
            precheck_summary,
            "",
            "Previous code excerpt:",
            code[-2600:],
            "",
            "Regenerate the full scene. Fix every issue before returning code.",
        ]
    )


def is_tax_wedge_prompt(prompt: str) -> bool:
    lowered = prompt.lower()
    tax_markers = (
        "tax wedge",
        "deadweight loss",
        "tax revenue",
        "unit tax",
        "税收楔子",
        "无谓损失",
        "税收收入",
        "单位税",
        "征税",
        "买方价格",
        "卖方价格",
    )
    return any(marker in lowered or marker in prompt for marker in tax_markers)


def is_two_part_pricing_prompt(prompt: str) -> bool:
    lowered = prompt.lower()
    markers = (
        "two-part pricing",
        "two part pricing",
        "two-part tariff",
        "two part tariff",
        "fixed fee",
        "entry fee",
        "access fee",
        "二部定价",
        "两部定价",
        "固定入场费",
        "入场费",
    )
    return any(marker in lowered or marker in prompt for marker in markers)


def is_standard_monopoly_prompt(prompt: str) -> bool:
    if is_two_part_pricing_prompt(prompt):
        return False
    lowered = prompt.lower()
    markers = (
        "monopoly",
        "monopolist",
        "mr",
        "mc",
        "marginal revenue",
        "marginal cost",
        "垄断定价",
        "垄断市场",
        "垄断厂商",
        "边际收益",
        "边际成本",
        "垄断利润",
        "完全竞争产量",
    )
    return any(marker in lowered or marker in prompt for marker in markers)


def is_consumer_choice_prompt(prompt: str) -> bool:
    lowered = prompt.lower()
    markers = (
        "consumer choice",
        "budget line",
        "budget constraint",
        "indifference curve",
        "substitution effect",
        "income effect",
        "price effect",
        "compensated budget",
        "消费者选择",
        "预算线",
        "预算约束",
        "无差异曲线",
        "替代效应",
        "收入效应",
        "价格效应",
        "补偿预算线",
    )
    return any(marker in lowered or marker in prompt for marker in markers)


def has_topic_specific_fallback(prompt: str) -> bool:
    return (
        is_tax_wedge_prompt(prompt)
        or is_two_part_pricing_prompt(prompt)
        or is_standard_monopoly_prompt(prompt)
        or is_consumer_choice_prompt(prompt)
    )


def topic_quality_warnings(prompt: str, code: str) -> list[str]:
    warnings: list[str] = []
    if is_standard_monopoly_prompt(prompt):
        lowered_code = code.lower()
        required_groups = (
            ("垄断", "monopoly"),
            ("边际收益", "mr", "marginal revenue"),
            ("边际成本", "mc", "marginal cost"),
            ("垄断利润", "monopoly profit"),
            ("无谓损失", "deadweight loss", "dwl"),
        )
        for group in required_groups:
            if not any(marker in code or marker in lowered_code for marker in group):
                warnings.append(f"standard-monopoly missing {'/'.join(group)}")
        if "Polygon(" not in code:
            warnings.append("standard-monopoly missing profit/dwl polygon")
        return warnings
    if is_consumer_choice_prompt(prompt):
        lowered_code = code.lower()
        required_groups = (
            ("预算线", "budget line", "budget constraint"),
            ("无差异曲线", "indifference"),
            ("替代效应", "substitution effect"),
            ("收入效应", "income effect"),
            ("补偿预算线", "compensated budget"),
        )
        for group in required_groups:
            if not any(marker in code or marker in lowered_code for marker in group):
                warnings.append(f"consumer-choice missing {'/'.join(group)}")
        for point in ("A", "B", "C"):
            if f'"{point}"' not in code and f"'{point}'" not in code:
                warnings.append(f"consumer-choice missing point {point}")
        return warnings
    if is_tax_wedge_prompt(prompt):
        required_groups = (
            ("税收收入", "tax revenue"),
            ("无谓损失", "deadweight loss", "dwl"),
            ("买方", "buyer"),
            ("卖方", "seller"),
        )
        lowered_code = code.lower()
        for group in required_groups:
            if not any(marker in code or marker in lowered_code for marker in group):
                warnings.append(f"tax-wedge missing {'/'.join(group)}")
        if "Polygon(" not in code:
            warnings.append("tax-wedge missing revenue/dwl polygon")
    if is_two_part_pricing_prompt(prompt):
        lowered_code = code.lower()
        required_groups = (
            ("二部定价", "两部定价", "two-part", "two part"),
            ("消费者剩余", "consumer surplus"),
            ("固定入场费", "入场费", "fixed fee", "entry fee", "access fee"),
            ("边际成本", "marginal cost", " mc"),
            ("垄断定价", "monopoly price", "linear monopoly"),
            ("有效率产量", "efficient output", "q_e"),
        )
        for group in required_groups:
            if not any(marker in code or marker in lowered_code for marker in group):
                warnings.append(f"two-part-pricing missing {'/'.join(group)}")
        if "Polygon(" not in code:
            warnings.append("two-part-pricing missing surplus/profit region polygon")
    return warnings


def build_fallback_manim_code(prompt: str, scene_name: str) -> str:
    """Return a deterministic Manim scene when trial model providers are slow/unavailable."""
    safe_scene_name = local_web_app.safe_scene_name(scene_name)
    compact = " ".join(prompt.split())[:28] or "抽象概念"
    if is_two_part_pricing_prompt(prompt):
        return f'''from manim import *

class {safe_scene_name}(Scene):
    def construct(self):
        self.camera.background_color = "#0f172a"
        title = Text("垄断厂商的二部定价", font_size=34, color=YELLOW).to_edge(UP)
        subtitle = Text("单位价格降到边际成本，固定入场费提取消费者剩余", font_size=20, color=GREY_B).next_to(title, DOWN, buff=0.18)

        axis_x = Line(LEFT * 3.2 + DOWN * 1.8, RIGHT * 2.4 + DOWN * 1.8, color=GREY_B)
        axis_y = Line(LEFT * 3.2 + DOWN * 1.8, LEFT * 3.2 + UP * 1.75, color=GREY_B)
        demand = Line(LEFT * 2.75 + UP * 1.35, RIGHT * 1.85 + DOWN * 1.25, color=BLUE, stroke_width=5)
        mc = Line(LEFT * 2.9 + DOWN * 0.65, RIGHT * 2.15 + DOWN * 0.65, color=GREEN, stroke_width=5)
        monopoly_point = Dot(LEFT * 1.25 + UP * 0.35, color=RED)
        efficient_point = Dot(RIGHT * 1.05 + DOWN * 0.65, color=YELLOW)
        surplus = Polygon(
            LEFT * 2.9 + UP * 1.55,
            RIGHT * 1.05 + DOWN * 0.65,
            LEFT * 2.9 + DOWN * 0.65,
            color=TEAL,
            fill_opacity=0.25,
            stroke_width=2,
        )
        labels = VGroup(
            Text("需求 D", font_size=18, color=BLUE).move_to(LEFT * 0.2 + UP * 1.35),
            Text("边际成本 MC", font_size=18, color=GREEN).move_to(RIGHT * 1.15 + DOWN * 0.36),
            Text("垄断点", font_size=17, color=RED).next_to(monopoly_point, UP, buff=0.12).shift(RIGHT * 0.25),
            Text("有效率产量 Qe", font_size=18, color=YELLOW).next_to(efficient_point, DOWN, buff=0.16).shift(RIGHT * 0.35),
            Text("消费者剩余", font_size=17, color=TEAL).move_to(LEFT * 2.05 + UP * 0.08),
        )
        rule_box = VGroup(
            Text("二部定价规则", font_size=23, color=YELLOW),
            Text("1. 单价 = MC，交易量扩大", font_size=19, color=WHITE),
            Text("2. 固定入场费 = 消费者剩余", font_size=19, color=WHITE),
            Text("3. 无谓损失消失，剩余转为利润", font_size=19, color=WHITE),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.16).to_edge(RIGHT, buff=0.55).shift(DOWN * 0.15)

        self.play(FadeIn(title), FadeIn(subtitle), run_time=0.7)
        self.play(Create(VGroup(axis_x, axis_y, demand, mc)), FadeIn(labels[:2]), run_time=0.9)
        self.play(FadeIn(monopoly_point), FadeIn(efficient_point), FadeIn(surplus), FadeIn(labels[2:]), run_time=0.9)
        self.play(FadeIn(rule_box), Indicate(surplus), run_time=1.0)
        self.wait(0.8)
'''
    if is_standard_monopoly_prompt(prompt):
        return f'''from manim import *

class {safe_scene_name}(Scene):
    def construct(self):
        self.camera.background_color = "#0f172a"
        title = Text("垄断定价与福利损失", font_size=34, color=YELLOW).to_edge(UP)
        subtitle = Text("MR=MC 决定 Qm，再由需求曲线决定 Pm", font_size=20, color=GREY_B).next_to(title, DOWN, buff=0.18)

        axes = Axes(
            x_range=[0, 6, 1],
            y_range=[0, 5, 1],
            x_length=6.4,
            y_length=4.25,
            tips=False,
            axis_config={{"include_numbers": False, "color": GREY_B}},
        ).shift(DOWN * 0.32)
        q_label = Text("产量 Q", font_size=18, color=GREY_B).next_to(axes.x_axis, RIGHT, buff=0.18)
        p_label = Text("价格 P", font_size=18, color=GREY_B).next_to(axes.y_axis, UP, buff=0.18)

        demand = Line(axes.c2p(0.75, 4.35), axes.c2p(5.35, 0.75), color=BLUE, stroke_width=5)
        mr = Line(axes.c2p(0.75, 4.0), axes.c2p(3.95, 0.65), color=RED, stroke_width=5)
        mc = Line(axes.c2p(0.75, 1.55), axes.c2p(5.35, 1.55), color=GREEN, stroke_width=5)
        labels = VGroup(
            Text("需求 D", font_size=18, color=BLUE).next_to(demand.get_start(), UP, buff=0.1),
            Text("边际收益 MR", font_size=18, color=RED).next_to(mr.get_center(), DOWN, buff=0.12).shift(LEFT * 0.35),
            Text("边际成本 MC", font_size=18, color=GREEN).next_to(mc.get_end(), UP, buff=0.1),
        )

        qm, pm, mc_price, qc = 2.65, 2.82, 1.55, 4.15
        monopoly_dot = Dot(axes.c2p(qm, mc_price), color=RED)
        price_dot = Dot(axes.c2p(qm, pm), color=YELLOW)
        competition_dot = Dot(axes.c2p(qc, mc_price), color=WHITE)
        qm_line = DashedLine(axes.c2p(qm, 0), axes.c2p(qm, pm), color=YELLOW, stroke_opacity=0.65)
        pm_line = DashedLine(axes.c2p(0, pm), axes.c2p(qm, pm), color=YELLOW, stroke_opacity=0.65)
        qc_line = DashedLine(axes.c2p(qc, 0), axes.c2p(qc, mc_price), color=WHITE, stroke_opacity=0.5)

        profit = Polygon(
            axes.c2p(0, mc_price),
            axes.c2p(qm, mc_price),
            axes.c2p(qm, pm),
            axes.c2p(0, pm),
            color=TEAL,
            fill_opacity=0.22,
            stroke_width=2,
        )
        dwl = Polygon(
            axes.c2p(qm, pm),
            axes.c2p(qm, mc_price),
            axes.c2p(qc, mc_price),
            color=RED,
            fill_opacity=0.34,
            stroke_width=3,
        )
        outcome_labels = VGroup(
            Text("Qm", font_size=18, color=YELLOW).next_to(axes.c2p(qm, 0), DOWN, buff=0.12),
            Text("Pm", font_size=18, color=YELLOW).next_to(axes.c2p(0, pm), LEFT, buff=0.12),
            Text("Qc", font_size=18, color=WHITE).next_to(axes.c2p(qc, 0), DOWN, buff=0.12),
            Text("垄断利润", font_size=18, color=TEAL).move_to(profit.get_center()),
            Text("无谓损失", font_size=18, color=RED).next_to(dwl, RIGHT, buff=0.12),
        )
        step1 = Text("1. 垄断厂商按 MR=MC 选择产量 Qm", font_size=21, color=WHITE).to_edge(DOWN)
        step2 = Text("2. 再沿需求曲线向上找到垄断价格 Pm", font_size=21, color=WHITE).to_edge(DOWN)
        step3 = Text("3. 相比 Qc，少生产的部分造成无谓损失", font_size=21, color=YELLOW).to_edge(DOWN)

        self.play(FadeIn(title), FadeIn(subtitle), run_time=0.7)
        self.play(Create(axes), FadeIn(VGroup(q_label, p_label)), run_time=0.8)
        self.play(Create(demand), Create(mr), Create(mc), FadeIn(labels), run_time=1.1)
        self.play(FadeIn(monopoly_dot), Create(qm_line), FadeIn(outcome_labels[0]), FadeIn(step1), run_time=1.0)
        self.wait(0.5)
        self.play(FadeIn(price_dot), Create(pm_line), FadeIn(outcome_labels[1]), ReplacementTransform(step1, step2), FadeIn(profit), FadeIn(outcome_labels[3]), run_time=1.1)
        self.wait(0.5)
        self.play(FadeIn(competition_dot), Create(qc_line), FadeIn(outcome_labels[2]), ReplacementTransform(step2, step3), FadeIn(dwl), FadeIn(outcome_labels[4]), run_time=1.2)
        self.wait(1.2)
'''
    if is_consumer_choice_prompt(prompt):
        return f'''from manim import *

class {safe_scene_name}(Scene):
    def construct(self):
        self.camera.background_color = "#0f172a"
        title = Text("消费者选择与价格效应", font_size=34, color=YELLOW).to_edge(UP)
        subtitle = Text("X 降价：A 到 B 是替代效应，B 到 C 是收入效应", font_size=20, color=GREY_B).next_to(title, DOWN, buff=0.18)

        axes = Axes(
            x_range=[0, 6, 1],
            y_range=[0, 5, 1],
            x_length=6.4,
            y_length=4.25,
            tips=False,
            axis_config={{"include_numbers": False, "color": GREY_B}},
        ).shift(DOWN * 0.32)
        x_label = Text("商品 X", font_size=18, color=GREY_B).next_to(axes.x_axis, RIGHT, buff=0.18)
        y_label = Text("商品 Y", font_size=18, color=GREY_B).next_to(axes.y_axis, UP, buff=0.18)

        old_budget = Line(axes.c2p(0.45, 4.15), axes.c2p(3.95, 0.45), color=GREY_B, stroke_width=4)
        new_budget = Line(axes.c2p(0.45, 4.15), axes.c2p(5.45, 0.45), color=BLUE, stroke_width=5)
        comp_budget = DashedLine(axes.c2p(0.95, 3.15), axes.c2p(4.75, 0.35), color=ORANGE, stroke_width=4)

        old_ic = VMobject(color=RED, stroke_width=4).set_points_smoothly([
            axes.c2p(1.05, 3.75),
            axes.c2p(1.65, 2.35),
            axes.c2p(2.55, 1.35),
            axes.c2p(3.55, 0.86),
        ])
        new_ic = VMobject(color=GREEN, stroke_width=4).set_points_smoothly([
            axes.c2p(2.1, 3.95),
            axes.c2p(3.05, 2.45),
            axes.c2p(4.05, 1.48),
            axes.c2p(5.1, 1.05),
        ])

        point_a = Dot(axes.c2p(2.0, 1.88), color=RED)
        point_b = Dot(axes.c2p(3.25, 1.45), color=ORANGE)
        point_c = Dot(axes.c2p(4.35, 1.72), color=GREEN)
        point_labels = VGroup(
            Text("A", font_size=22, color=RED).next_to(point_a, UP, buff=0.08),
            Text("B", font_size=22, color=ORANGE).next_to(point_b, DOWN, buff=0.08),
            Text("C", font_size=22, color=GREEN).next_to(point_c, UP, buff=0.08),
        )

        line_labels = VGroup(
            Text("原预算线", font_size=18, color=GREY_B).next_to(old_budget, DOWN, buff=0.1).shift(LEFT * 0.55),
            Text("新预算线", font_size=18, color=BLUE).next_to(new_budget, RIGHT, buff=0.1),
            Text("补偿预算线", font_size=18, color=ORANGE).next_to(comp_budget, DOWN, buff=0.12),
            Text("原无差异曲线", font_size=17, color=RED).next_to(old_ic, LEFT, buff=0.12),
            Text("更高无差异曲线", font_size=17, color=GREEN).next_to(new_ic, RIGHT, buff=0.12),
        )

        substitution = Arrow(axes.c2p(2.0, 0.28), axes.c2p(3.25, 0.28), color=ORANGE, buff=0.02, stroke_width=4)
        income = Arrow(axes.c2p(3.25, 0.28), axes.c2p(4.35, 0.28), color=GREEN, buff=0.02, stroke_width=4)
        effect_labels = VGroup(
            Text("替代效应", font_size=18, color=ORANGE).next_to(substitution, DOWN, buff=0.08),
            Text("收入效应", font_size=18, color=GREEN).next_to(income, DOWN, buff=0.08),
        )
        guides = VGroup(
            DashedLine(point_a.get_center(), axes.c2p(2.0, 0), color=RED, stroke_opacity=0.45),
            DashedLine(point_b.get_center(), axes.c2p(3.25, 0), color=ORANGE, stroke_opacity=0.45),
            DashedLine(point_c.get_center(), axes.c2p(4.35, 0), color=GREEN, stroke_opacity=0.45),
        )

        step1 = Text("1. 初始最优点 A：预算线与无差异曲线相切", font_size=20, color=WHITE).to_edge(DOWN)
        step2 = Text("2. X 降价使预算线绕纵轴向外旋转", font_size=20, color=WHITE).to_edge(DOWN)
        step3 = Text("3. 补偿预算线分解 A 到 C 的总变化", font_size=20, color=YELLOW).to_edge(DOWN)

        self.play(FadeIn(title), FadeIn(subtitle), run_time=0.7)
        self.play(Create(axes), FadeIn(VGroup(x_label, y_label)), run_time=0.8)
        self.play(Create(old_budget), Create(old_ic), FadeIn(point_a), FadeIn(point_labels[0]), FadeIn(line_labels[0]), FadeIn(line_labels[3]), FadeIn(step1), run_time=1.1)
        self.wait(0.4)
        self.play(Create(new_budget), Create(new_ic), FadeIn(point_c), FadeIn(point_labels[2]), FadeIn(line_labels[1]), FadeIn(line_labels[4]), ReplacementTransform(step1, step2), run_time=1.2)
        self.wait(0.4)
        self.play(Create(comp_budget), FadeIn(point_b), FadeIn(point_labels[1]), FadeIn(line_labels[2]), FadeIn(guides), ReplacementTransform(step2, step3), run_time=1.0)
        self.play(GrowArrow(substitution), GrowArrow(income), FadeIn(effect_labels), run_time=1.0)
        self.wait(1.1)
'''
    if is_tax_wedge_prompt(prompt):
        return f'''from manim import *

class {safe_scene_name}(Scene):
    def construct(self):
        self.camera.background_color = "#0f172a"
        title = Text("税收楔子与无谓损失", font_size=36, color=YELLOW).to_edge(UP)
        subtitle = Text("税把买方价和卖方价拉开，交易量下降", font_size=20, color=GREY_B).next_to(title, DOWN, buff=0.22)

        axes = Axes(
            x_range=[0, 6, 1],
            y_range=[0, 5, 1],
            x_length=6.4,
            y_length=4.4,
            tips=False,
            axis_config={{"include_numbers": False, "color": GREY_B}},
        ).shift(DOWN * 0.35)
        q_label = Text("数量 Q", font_size=18, color=GREY_B).next_to(axes.x_axis, RIGHT, buff=0.18)
        p_label = Text("价格 P", font_size=18, color=GREY_B).next_to(axes.y_axis, UP, buff=0.18)

        demand = Line(axes.c2p(0.7, 4.35), axes.c2p(5.3, 0.75), color=BLUE, stroke_width=5)
        supply = Line(axes.c2p(0.7, 0.75), axes.c2p(5.3, 4.35), color=GREEN, stroke_width=5)
        d_label = Text("需求 D", font_size=18, color=BLUE).next_to(demand.get_start(), UP, buff=0.12)
        s_label = Text("供给 S", font_size=18, color=GREEN).next_to(supply.get_end(), UP, buff=0.12)

        q0, p0 = 3.0, 2.55
        q1, pb, ps = 2.15, 3.22, 1.88
        eq_dot = Dot(axes.c2p(q0, p0), color=WHITE)
        eq_lines = VGroup(
            DashedLine(axes.c2p(q0, 0), axes.c2p(q0, p0), color=WHITE, stroke_opacity=0.55),
            DashedLine(axes.c2p(0, p0), axes.c2p(q0, p0), color=WHITE, stroke_opacity=0.55),
        )
        eq_text = Text("税前均衡", font_size=19, color=WHITE).next_to(eq_dot, RIGHT, buff=0.15)

        wedge = Line(axes.c2p(q1, ps), axes.c2p(q1, pb), color=YELLOW, stroke_width=7)
        wedge_label = Text("单位税", font_size=18, color=YELLOW).next_to(wedge, LEFT, buff=0.12)
        buyer_line = DashedLine(axes.c2p(0, pb), axes.c2p(q1, pb), color=BLUE, stroke_opacity=0.65)
        seller_line = DashedLine(axes.c2p(0, ps), axes.c2p(q1, ps), color=GREEN, stroke_opacity=0.65)
        q1_line = DashedLine(axes.c2p(q1, 0), axes.c2p(q1, pb), color=YELLOW, stroke_opacity=0.55)
        buyer_text = Text("买方价上升", font_size=18, color=BLUE).next_to(buyer_line, LEFT, buff=0.1)
        seller_text = Text("卖方价下降", font_size=18, color=GREEN).next_to(seller_line, LEFT, buff=0.1)

        revenue = Polygon(
            axes.c2p(0, ps),
            axes.c2p(q1, ps),
            axes.c2p(q1, pb),
            axes.c2p(0, pb),
            color=TEAL,
            fill_opacity=0.22,
            stroke_width=2,
        )
        revenue_label = Text("税收收入", font_size=18, color=TEAL).move_to(revenue.get_center())
        dwl = Polygon(
            axes.c2p(q1, pb),
            axes.c2p(q1, ps),
            axes.c2p(q0, p0),
            color=RED,
            fill_opacity=0.38,
            stroke_width=3,
        )
        dwl_label = Text("无谓损失", font_size=18, color=RED).next_to(dwl, RIGHT, buff=0.12)

        step1 = Text("1. 无税时，供给与需求在 E0 相交", font_size=21, color=WHITE).to_edge(DOWN)
        step2 = Text("2. 征税后，买方支付更高价，卖方得到更低价", font_size=21, color=WHITE).to_edge(DOWN)
        step3 = Text("3. Q1 小于 Q0：原本互利的交易消失", font_size=21, color=WHITE).to_edge(DOWN)
        step4 = Text("4. 三角形就是社会总剩余的净损失", font_size=21, color=YELLOW).to_edge(DOWN)

        self.play(FadeIn(title), FadeIn(subtitle, shift=DOWN), run_time=0.8)
        self.play(Create(axes), FadeIn(VGroup(q_label, p_label)), run_time=1.0)
        self.play(Create(demand), Create(supply), FadeIn(VGroup(d_label, s_label)), run_time=1.1)
        self.play(FadeIn(eq_dot), Create(eq_lines), Write(eq_text), FadeIn(step1), run_time=1.1)
        self.wait(0.7)
        self.play(ReplacementTransform(step1, step2), Create(wedge), FadeIn(wedge_label), Create(VGroup(buyer_line, seller_line, q1_line)), FadeIn(VGroup(buyer_text, seller_text)), run_time=1.3)
        self.wait(0.7)
        self.play(ReplacementTransform(step2, step3), FadeIn(revenue), Write(revenue_label), run_time=1.0)
        self.wait(0.6)
        self.play(ReplacementTransform(step3, step4), FadeIn(dwl), Write(dwl_label), Indicate(dwl), run_time=1.2)
        self.wait(1.4)
'''
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


def resolve_public_byok_provider(provider_id: str) -> tuple[object | None, str | None]:
    cleaned = (provider_id or "").strip()
    if not cleaned:
        return None, "请选择模型服务。"
    if cleaned in PUBLIC_TRIAL_PLANS or cleaned.startswith("trial-"):
        return None, BYOK_TRIAL_PREFLIGHT_ERROR
    if is_local_only_provider(cleaned) or cleaned in DISABLED_CLOUD_PROVIDERS:
        return None, LOCAL_ONLY_PROVIDER_ERROR
    if cleaned not in PROVIDER_PRESETS:
        return None, UNKNOWN_PROVIDER_ERROR
    return resolve_provider(cleaned), None


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


def build_trial_fallback_response(
    *,
    trial_provider_id: str,
    plan: dict[str, object],
    prompt: str,
    scene_name: str,
    request_id: str,
    failed_categories: list[str] | None = None,
    skipped: list[str] | None = None,
    last_error: str | None = None,
    lead_warning: str | None = None,
) -> tuple[int, dict[str, object]]:
    fallback_code = build_fallback_manim_code(prompt, scene_name)
    fallback_code, compatibility_notes = apply_runtime_compatibility_fixes(fallback_code)
    warnings = [
        lead_warning
        or "内测试用模型响应较慢或暂不可用，已自动切换到稳定模板生成，视频仍会继续渲染。",
        *compatibility_notes,
    ]
    if failed_categories:
        warnings.append("模型失败类别：" + ", ".join(failed_categories[-3:]))
    elif last_error:
        warnings.append(f"模型失败类别：{last_error}")
    if skipped:
        warnings.append("未配置的试用模型：" + ", ".join(skipped))
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
            "error": UNKNOWN_TRIAL_ERROR,
            "requestId": request_id,
        }
    generation_prompt = trial_generation_prompt(prompt)
    skipped: list[str] = []
    failed_categories: list[str] = []
    last_error: str | None = None
    for attempt in plan["attempts"]:
        env_name = str(attempt["env"])
        api_key = read_server_key(env_name)
        provider_id = str(attempt["provider_id"])
        provider = resolve_provider(provider_id)
        model = str(attempt["model"]) or provider.default_model or DEFAULT_MODEL
        trial_base_url = str(attempt.get("base_url", "")).strip()
        if not api_key:
            skipped.append(provider.name)
            continue

        quality_warnings: list[str] = []
        try:
            raw_code, _used_provider_name, _used_endpoint = generate_code_with_llm(
                provider_id=provider.id,
                api_key=api_key,
                base_url=trial_base_url,
                endpoint="",
                model=model,
                system_prompt=SYSTEM_PROMPT,
                user_prompt=generation_prompt,
                temperature=temperature,
                timeout=trial_timeout_seconds(provider.id),
            )
            cleaned_code = extract_python_only(raw_code)
            patched_code, compatibility_notes = apply_runtime_compatibility_fixes(cleaned_code)
            detected_scene_name = local_web_app.detect_scene_name(patched_code, scene_name)
            precheck_issues = [
                issue
                for issue in precheck_manim_code(patched_code, detected_scene_name)
                if issue.severity == "error"
            ]
            if precheck_issues:
                raw_code, _used_provider_name, _used_endpoint = generate_code_with_llm(
                    provider_id=provider.id,
                    api_key=api_key,
                    base_url="",
                    endpoint="",
                    model=model,
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=trial_precheck_repair_prompt(prompt, patched_code, precheck_issues),
                    temperature=min(temperature, 0.2),
                    timeout=trial_timeout_seconds(provider.id, repair=True),
                )
                cleaned_code = extract_python_only(raw_code)
                patched_code, compatibility_notes = apply_runtime_compatibility_fixes(cleaned_code)
                detected_scene_name = local_web_app.detect_scene_name(patched_code, scene_name)
                precheck_issues = [
                    issue
                    for issue in precheck_manim_code(patched_code, detected_scene_name)
                    if issue.severity == "error"
                ]
                if precheck_issues:
                    last_error = "precheck"
                    failed_categories.append(f"{provider.id}:precheck")
                    print(
                        f"[{request_id}] trial provider failed precheck after repair: {provider.id}",
                        file=sys.stderr,
                    )
                    continue
            budget_notes = render_budget_warnings(patched_code)
            if budget_notes:
                raw_code, _used_provider_name, _used_endpoint = generate_code_with_llm(
                    provider_id=provider.id,
                    api_key=api_key,
                    base_url="",
                    endpoint="",
                    model=model,
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=hosted_render_budget_prompt(generation_prompt, budget_notes),
                    temperature=min(temperature, 0.2),
                    timeout=trial_timeout_seconds(provider.id, repair=True),
                )
                cleaned_code = extract_python_only(raw_code)
                patched_code, compatibility_notes = apply_runtime_compatibility_fixes(cleaned_code)
                detected_scene_name = local_web_app.detect_scene_name(patched_code, scene_name)
                budget_notes = render_budget_warnings(patched_code)
                if budget_notes:
                    hard_budget_notes = render_hard_budget_warnings(patched_code)
                    if hard_budget_notes:
                        last_error = "budget"
                        failed_categories.append(f"{provider.id}:budget")
                        print(
                            f"[{request_id}] trial provider exceeded hard render budget after repair: {provider.id}",
                            file=sys.stderr,
                        )
                        continue
                    if has_topic_specific_fallback(prompt):
                        last_error = "topic-budget"
                        failed_categories.append(f"{provider.id}:topic-budget")
                        print(
                            f"[{request_id}] trial provider exceeded topic fallback render budget: {provider.id}",
                            file=sys.stderr,
                        )
                        continue
                    quality_warnings.extend(
                        f"模型脚本略超软预算，已交给分段渲染尝试：{note}"
                        for note in budget_notes[:3]
                    )
            topic_notes = topic_quality_warnings(prompt, patched_code)
            if topic_notes:
                last_error = "topic-quality"
                failed_categories.append(f"{provider.id}:topic-quality")
                print(
                    f"[{request_id}] trial provider missed topic quality gate: {provider.id} notes={'; '.join(topic_notes[:3])}",
                    file=sys.stderr,
                )
                continue
        except Exception as exc:
            last_error = sanitize_upstream_error(exc)
            failed_categories.append(f"{provider.id}:{last_error}")
            print(
                f"[{request_id}] trial provider failed: {provider.id} reason={last_error}",
                file=sys.stderr,
            )
            continue

        warnings = [*compatibility_notes, *quality_warnings]
        if skipped:
            warnings.append("部分试用模型暂不可用，已自动使用可用的备用模型。")
        if provider.id != str(plan["attempts"][0]["provider_id"]):
            reason_text = failed_categories[0].split(":", 1)[1] if failed_categories else "request"
            warnings.append(f"{plan['name']} 首选模型本次未完成（{describe_trial_failure(reason_text)}），已自动切换到 {provider.name} 备用模型。")
        if failed_categories:
            warnings.append("模型失败类别：" + ", ".join(failed_categories[-3:]))

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
    return build_trial_fallback_response(
        trial_provider_id=trial_provider_id,
        plan=plan,
        prompt=prompt,
        scene_name=scene_name,
        request_id=request_id,
        failed_categories=failed_categories,
        skipped=skipped,
        last_error=last_error,
    )


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
    if provider_id.startswith("trial-"):
        return HTTPStatus.BAD_REQUEST, {
            "ok": False,
            "error": UNKNOWN_TRIAL_ERROR,
            "requestId": request_id,
        }
    if is_local_only_provider(provider_id) or provider_id in DISABLED_CLOUD_PROVIDERS:
        return HTTPStatus.BAD_REQUEST, {
            "ok": False,
            "error": LOCAL_ONLY_PROVIDER_ERROR,
            "requestId": request_id,
        }
    if provider_id not in PROVIDER_PRESETS:
        return HTTPStatus.BAD_REQUEST, {
            "ok": False,
            "error": UNKNOWN_PROVIDER_ERROR,
            "requestId": request_id,
        }

    return generate_manim_code_with_client_provider(payload)


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
    scene_name = local_web_app.safe_scene_name(str(payload.get("sceneName", "GeneratedScene")))
    api_key = str(payload.get("apiKey", "")).strip()
    model = str(payload.get("model", "")).strip() or provider.default_model or DEFAULT_MODEL
    base_url = str(payload.get("baseUrl", "")).strip()
    endpoint = str(payload.get("endpoint", "")).strip()
    temperature = clamp_temperature(payload.get("temperature", 0.2))

    if provider.requires_api_key and not api_key:
        return HTTPStatus.BAD_REQUEST, {
            "ok": False,
            "error": f"请填写你的 {provider.name} API Key。密钥只用于本次请求，不会写入服务器。",
            "requestId": request_id,
        }
    if api_key and is_placeholder_api_key(api_key):
        return HTTPStatus.BAD_REQUEST, {
            "ok": False,
            "error": BYOK_PLACEHOLDER_KEY_ERROR,
            "requestId": request_id,
        }
    if provider.id in {"custom-openai", "custom-anthropic"} and not (base_url or endpoint):
        return HTTPStatus.BAD_REQUEST, {
            "ok": False,
            "error": BYOK_CUSTOM_URL_REQUIRED_ERROR,
            "requestId": request_id,
        }

    for field_name, raw_url in (("Base URL", base_url), ("Endpoint", endpoint)):
        endpoint_error = validate_cloud_model_endpoint(raw_url, field_name=field_name)
        if endpoint_error:
            return HTTPStatus.BAD_REQUEST, {"ok": False, "error": endpoint_error, "requestId": request_id}

    try:
        raw_code, _used_provider, used_endpoint = generate_code_with_llm(
            provider_id=provider.id,
            api_key=api_key,
            base_url=base_url,
            endpoint=endpoint,
            model=model,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=trial_generation_prompt(prompt),
            temperature=temperature,
            timeout=trial_timeout_seconds(provider.id),
        )
        cleaned_code = extract_python_only(raw_code)
        patched_code, compatibility_notes = apply_runtime_compatibility_fixes(cleaned_code)
        detected_scene_name = local_web_app.detect_scene_name(patched_code, scene_name)
    except ValueError as exc:
        return HTTPStatus.BAD_REQUEST, {
            "ok": False,
            "error": redact_client_secrets(str(exc), api_key),
            "requestId": request_id,
        }
    except Exception as exc:
        category = sanitize_upstream_error(exc)
        reason = describe_trial_failure(category)
        if reason == "request":
            reason = "请检查 Key、额度与 Base URL"
        return HTTPStatus.BAD_GATEWAY, {
            "ok": False,
            "error": f"模型请求失败：{reason}。",
            "requestId": request_id,
        }

    return HTTPStatus.OK, {
        "ok": True,
        "provider": provider.id,
        "providerName": provider.name,
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
        "authMode": "byok",
        "message": "已使用你的密钥生成 Manim 代码；密钥未写入服务器。",
    }


def preflight_byok_provider(payload: dict[str, object]) -> tuple[int, dict[str, object]]:
    request_id = build_request_id()
    provider, provider_error = resolve_public_byok_provider(str(payload.get("provider", "")).strip())
    if provider_error or provider is None:
        return HTTPStatus.BAD_REQUEST, {
            "ok": False,
            "error": provider_error or UNKNOWN_PROVIDER_ERROR,
            "requestId": request_id,
        }

    api_key = str(payload.get("apiKey", "")).strip()
    model = str(payload.get("model", "")).strip() or provider.default_model or DEFAULT_MODEL
    base_url = str(payload.get("baseUrl", "")).strip()
    endpoint = str(payload.get("endpoint", "")).strip()

    if provider.requires_api_key and not api_key:
        return HTTPStatus.BAD_REQUEST, {
            "ok": False,
            "error": f"请填写你的 {provider.name} API Key。密钥只用于本次请求，不会写入服务器。",
            "requestId": request_id,
        }
    if api_key and is_placeholder_api_key(api_key):
        return HTTPStatus.BAD_REQUEST, {
            "ok": False,
            "error": BYOK_PLACEHOLDER_KEY_ERROR,
            "requestId": request_id,
        }
    if provider.id in {"custom-openai", "custom-anthropic"} and not (base_url or endpoint):
        return HTTPStatus.BAD_REQUEST, {
            "ok": False,
            "error": BYOK_CUSTOM_URL_REQUIRED_ERROR,
            "requestId": request_id,
        }

    for field_name, raw_url in (("Base URL", base_url), ("Endpoint", endpoint)):
        endpoint_error = validate_cloud_model_endpoint(raw_url, field_name=field_name)
        if endpoint_error:
            return HTTPStatus.BAD_REQUEST, {"ok": False, "error": endpoint_error, "requestId": request_id}

    started = time.monotonic()
    try:
        _probe, _used_provider, used_endpoint = generate_code_with_provider(
            provider_id=provider.id,
            api_key=api_key,
            base_url=base_url,
            endpoint=endpoint,
            model=model,
            system_prompt="You are a connectivity probe. Reply with the single word ok.",
            user_prompt="ok",
            temperature=0,
            timeout=BYOK_PREFLIGHT_TIMEOUT_SECONDS,
            max_tokens=BYOK_PREFLIGHT_MAX_TOKENS,
        )
    except ValueError as exc:
        return HTTPStatus.BAD_REQUEST, {
            "ok": False,
            "error": redact_client_secrets(str(exc), api_key),
            "requestId": request_id,
        }
    except Exception as exc:
        category = sanitize_upstream_error(exc)
        reason = describe_trial_failure(category)
        if reason == "request":
            reason = "请检查 Key、额度与 Base URL"
        return HTTPStatus.BAD_GATEWAY, {
            "ok": False,
            "error": f"连通失败：{reason}。",
            "requestId": request_id,
        }

    latency_ms = int((time.monotonic() - started) * 1000)
    return HTTPStatus.OK, {
        "ok": True,
        "authMode": "byok",
        "provider": provider.id,
        "providerName": provider.name,
        "model": model,
        "endpoint": used_endpoint,
        "latencyMs": latency_ms,
        "requestId": request_id,
        "message": "密钥可用，已连通模型服务。密钥未写入服务器。",
    }


def _alignment_model_call(
    *,
    provider_id: str,
    api_key: str,
    base_url: str | None,
    endpoint: str | None,
    model: str,
    temperature: float,
    timeout: int,
):
    def call(system_prompt: str, user_prompt: str) -> str:
        raw_text, _provider_name, _endpoint = generate_code_with_llm(
            provider_id=provider_id,
            api_key=api_key,
            base_url=base_url,
            endpoint=endpoint,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=min(0.4, temperature),
            timeout=timeout,
        )
        return raw_text

    return call


def align_script_for_gateway(payload: dict[str, object]) -> tuple[int, dict[str, object]]:
    request_id = build_request_id()
    prompt = str(payload.get("prompt", "")).strip()
    code = str(payload.get("code", "")).strip()
    scene_name = local_web_app.safe_scene_name(str(payload.get("sceneName", "GeneratedScene")))
    video_duration = local_web_app.optional_positive_float(payload.get("videoDuration"))
    provider_id = str(payload.get("provider", PUBLIC_TRIAL_DEFAULT_PROVIDER)).strip() or PUBLIC_TRIAL_DEFAULT_PROVIDER
    temperature = clamp_temperature(payload.get("temperature", 0.2))
    client_key = str(payload.get("apiKey", "")).strip()

    if len(prompt) < 6 or not code:
        return HTTPStatus.BAD_REQUEST, {
            "ok": False,
            "error": "对齐需要问题和已生成的代码。",
            "requestId": request_id,
        }

    secrets: list[str] = [client_key] if client_key else []
    llm_call = None
    auth_mode = "trial"
    used_provider_id = provider_id
    used_provider_name = provider_id

    if provider_id in PUBLIC_TRIAL_PLANS:
        plan = PUBLIC_TRIAL_PLANS[provider_id]
        used_provider_name = str(plan["name"])
        for attempt in plan["attempts"]:
            server_key = read_server_key(str(attempt["env"]))
            if not server_key:
                continue
            secrets.append(server_key)
            provider = resolve_provider(str(attempt["provider_id"]))
            llm_call = _alignment_model_call(
                provider_id=provider.id,
                api_key=server_key,
                base_url=str(attempt.get("base_url", "")).strip() or None,
                endpoint=None,
                model=str(attempt["model"]) or provider.default_model or DEFAULT_MODEL,
                temperature=temperature,
                timeout=trial_timeout_seconds(provider.id, repair=True),
            )
            break
    elif provider_id.startswith("trial-"):
        return HTTPStatus.BAD_REQUEST, {
            "ok": False,
            "error": UNKNOWN_TRIAL_ERROR,
            "requestId": request_id,
        }
    elif is_local_only_provider(provider_id) or provider_id in DISABLED_CLOUD_PROVIDERS:
        return HTTPStatus.BAD_REQUEST, {
            "ok": False,
            "error": LOCAL_ONLY_PROVIDER_ERROR,
            "requestId": request_id,
        }
    else:
        provider, provider_error = resolve_public_byok_provider(provider_id)
        if provider_error or provider is None:
            return HTTPStatus.BAD_REQUEST, {
                "ok": False,
                "error": provider_error or UNKNOWN_PROVIDER_ERROR,
                "requestId": request_id,
            }
        api_key = client_key
        model = str(payload.get("model", "")).strip() or provider.default_model or DEFAULT_MODEL
        base_url = str(payload.get("baseUrl", "")).strip()
        endpoint = str(payload.get("endpoint", "")).strip()
        if provider.requires_api_key and not api_key:
            return HTTPStatus.BAD_REQUEST, {
                "ok": False,
                "error": f"请填写你的 {provider.name} API Key。密钥只用于本次请求，不会写入服务器。",
                "requestId": request_id,
            }
        if api_key and is_placeholder_api_key(api_key):
            return HTTPStatus.BAD_REQUEST, {
                "ok": False,
                "error": BYOK_PLACEHOLDER_KEY_ERROR,
                "requestId": request_id,
            }
        if provider.id in {"custom-openai", "custom-anthropic"} and not (base_url or endpoint):
            return HTTPStatus.BAD_REQUEST, {
                "ok": False,
                "error": BYOK_CUSTOM_URL_REQUIRED_ERROR,
                "requestId": request_id,
            }
        for field_name, raw_url in (("Base URL", base_url), ("Endpoint", endpoint)):
            endpoint_error = validate_cloud_model_endpoint(raw_url, field_name=field_name)
            if endpoint_error:
                return HTTPStatus.BAD_REQUEST, {"ok": False, "error": endpoint_error, "requestId": request_id}
        llm_call = _alignment_model_call(
            provider_id=provider.id,
            api_key=api_key,
            base_url=base_url or None,
            endpoint=endpoint or None,
            model=model,
            temperature=temperature,
            timeout=trial_timeout_seconds(provider.id),
        )
        auth_mode = "byok"
        used_provider_id = provider.id
        used_provider_name = provider.name

    alignment = generate_alignment(
        prompt=prompt,
        code=code,
        scene_name=scene_name,
        video_duration=video_duration,
        llm_call=llm_call,
    )
    alignment = local_web_app.redact_json_secrets(alignment, *secrets)
    return HTTPStatus.OK, {
        "ok": True,
        "requestId": request_id,
        "provider": used_provider_id,
        "providerName": used_provider_name,
        "authMode": auth_mode,
        "alignment": alignment,
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
            "当前提供 MiniMax M3 与 Mimo 编程两种内测试用模型，也可切换到自带密钥。"
        ),
        "免费试用走内置额度；自带密钥可接入智谱、OpenAI、DeepSeek、Kimi、MiniMax。": (
            "当前提供 MiniMax M3 与 Mimo 编程两种内测试用模型，也可切换到自带密钥。"
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


def build_render_backend_submit_payload(
    payload: dict[str, object],
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    code = str(payload.get("code", "")).strip()
    if not code:
        return None, {"ok": False, "error": "缺少 code 字段"}

    raw_scene_name = payload.get("sceneName", payload.get("scene_name", "GeneratedScene"))
    scene_name = local_web_app.safe_scene_name(str(raw_scene_name))
    render_mode = str(payload.get("renderMode", payload.get("render_mode", "auto"))).strip() or "auto"

    code, _notes = apply_runtime_compatibility_fixes(code)
    scene_name = local_web_app.detect_scene_name(code, scene_name)
    return {"code": code, "scene_name": scene_name, "render_mode": render_mode}, None


def proxy_community_request(
    route: str,
    *,
    query: str = "",
    method: str = "GET",
    payload: dict[str, object] | None = None,
) -> tuple[int, dict[str, object]]:
    if route == "/api/community/search" and method == "GET":
        backend_path = "/community/search" + (f"?{query}" if query else "")
        return _proxy_to_render_backend(backend_path, method="GET", timeout=15)
    if route == "/api/community/review/queue" and method == "GET":
        backend_path = "/community/review/queue" + (f"?{query}" if query else "")
        return _proxy_to_render_backend(backend_path, method="GET", timeout=20)
    if method != "POST":
        return HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found."}
    if route == "/api/community/works":
        return _proxy_to_render_backend("/community/works", method="POST", payload=payload or {}, timeout=15)
    prefix = "/api/community/works/"
    if route.startswith(prefix):
        suffix = route[len(prefix):]
        parts = [part for part in suffix.split("/") if part]
        if len(parts) == 2 and parts[1] in {"rating", "reuse", "review"}:
            return _proxy_to_render_backend(
                f"/community/works/{parts[0]}/{parts[1]}",
                method="POST",
                payload=payload or {},
                timeout=20,
            )
    return HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found."}


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

    def _read_json_body(self, *, max_bytes: int = MAX_PUBLIC_BODY_BYTES) -> dict[str, object]:
        raw_len = self.headers.get("Content-Length", "0")
        try:
            body_len = int(raw_len)
        except ValueError:
            return {}
        if body_len > max_bytes:
            raise ValueError("请求体太大，请缩短问题后再试。")
        if body_len <= 0:
            return {}
        raw = self.rfile.read(body_len)
        parsed = json.loads(raw.decode("utf-8"))
        if not isinstance(parsed, dict):
            return {}
        return parsed

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path
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
        if route == "/api/community/search":
            status, response = proxy_community_request(route, query=parsed.query)
            self._send_json(HTTPStatus(status), response)
            return
        if route == "/api/community/review/queue":
            status, response = proxy_community_request(route, query=parsed.query)
            self._send_json(HTTPStatus(status), response)
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
        if route == "/api/byok/preflight":
            try:
                payload = self._read_json_body()
            except Exception as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                return
            status, response = preflight_byok_provider(payload)
            self._send_json(HTTPStatus(status), response)
            return
        if route == "/api/align":
            try:
                payload = self._read_json_body()
            except Exception as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                return
            status, response = align_script_for_gateway(payload)
            self._send_json(HTTPStatus(status), response)
            return
        if route == "/api/vision/analyze":
            if not is_vision_public_enabled():
                status, response = disabled_vision_response()
                self._send_json(HTTPStatus(status), response)
                return
            try:
                payload = self._read_json_body(max_bytes=MAX_VISION_REQUEST_BYTES)
            except Exception as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                return
            status, response = analyze_image_payload(payload)
            self._send_json(HTTPStatus(status), response)
            return
        if route == "/api/community/works" or route.startswith("/api/community/works/"):
            try:
                payload = self._read_json_body()
            except Exception as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                return
            status, response = proxy_community_request(route, method="POST", payload=payload)
            self._send_json(HTTPStatus(status), response)
            return
        if route == "/api/render" or route.startswith("/api/render/"):
            try:
                payload = self._read_json_body()
            except Exception as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                return
            render_payload, error_payload = build_render_backend_submit_payload(payload)
            if error_payload is not None or render_payload is None:
                self._send_json(HTTPStatus.BAD_REQUEST, error_payload or {"ok": False, "error": "Invalid render payload."})
                return
            # Proxy to render backend async endpoint
            status, response = _proxy_to_render_backend(
                "/render-async",
                method="POST",
                payload=render_payload,
                timeout=15,
            )
            self._send_json(HTTPStatus(status), response)
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found."})

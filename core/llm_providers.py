from __future__ import annotations

import json
import os
import subprocess
import tempfile
import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib import error, request
from urllib.parse import urlparse

DEFAULT_PROVIDER = "codex-cli"
DEFAULT_ZHIPU_ENDPOINT = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
DEFAULT_ZHIPU_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
DEFAULT_MODEL = "glm-5"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ProviderPreset:
    id: str
    name: str
    api_type: str
    region: str
    base_url: str
    default_model: str
    models: tuple[str, ...]
    doc: str = ""
    api_key_placeholder: str = "API Key..."
    requires_api_key: bool = True


PROVIDER_PRESETS: dict[str, ProviderPreset] = {
    "zhipu": ProviderPreset(
        id="zhipu",
        name="智谱 GLM",
        api_type="openai-compatible",
        region="cn",
        base_url=DEFAULT_ZHIPU_BASE_URL,
        default_model=DEFAULT_MODEL,
        models=("glm-5", "glm-4.5", "glm-4-plus", "glm-4-flash"),
        doc="https://open.bigmodel.cn/dev/api",
        api_key_placeholder="BIGMODEL_API_KEY",
    ),
    "openai": ProviderPreset(
        id="openai",
        name="OpenAI API",
        api_type="openai-compatible",
        region="global",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        models=("gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1", "gpt-5-mini"),
        doc="https://platform.openai.com/docs/api-reference/chat",
        api_key_placeholder="OPENAI_API_KEY / sk-...",
    ),
    "kimi-code": ProviderPreset(
        id="kimi-code",
        name="Kimi Code API",
        api_type="anthropic-compatible",
        region="cn",
        base_url="https://api.kimi.com/coding",
        default_model="kimi-for-coding",
        models=("kimi-for-coding",),
        doc="https://www.kimi.com/coding/docs/",
        api_key_placeholder="KIMI_CODE_API_KEY",
    ),
    "moonshot-kimi": ProviderPreset(
        id="moonshot-kimi",
        name="Moonshot Kimi API",
        api_type="openai-compatible",
        region="cn",
        base_url="https://api.moonshot.cn/v1",
        default_model="kimi-k2-0711-preview",
        models=("kimi-k2-0711-preview", "kimi-latest", "kimi-thinking-preview"),
        doc="https://platform.kimi.ai/docs/api/overview",
        api_key_placeholder="MOONSHOT_API_KEY",
    ),
    "deepseek": ProviderPreset(
        id="deepseek",
        name="DeepSeek API",
        api_type="openai-compatible",
        region="cn",
        base_url="https://api.deepseek.com",
        default_model="deepseek-v4-flash",
        models=("deepseek-v4-flash", "deepseek-v4-pro", "deepseek-chat", "deepseek-reasoner"),
        doc="https://api-docs.deepseek.com/",
        api_key_placeholder="DEEPSEEK_API_KEY",
    ),
    "codex-local-proxy": ProviderPreset(
        id="codex-local-proxy",
        name="Codex / 本地 OpenAI-Compatible 代理",
        api_type="openai-compatible",
        region="local",
        base_url="http://127.0.0.1:8317/api/provider/antigravity/v1",
        default_model="claude-opus-4-6-thinking",
        models=("claude-opus-4-6-thinking", "gemini-3.1-pro-preview"),
        doc="",
        api_key_placeholder="本地代理如不需要鉴权可留空",
        requires_api_key=False,
    ),
    "codex-cli": ProviderPreset(
        id="codex-cli",
        name="Codex CLI 登录态（本机）",
        api_type="codex-cli",
        region="local",
        base_url="",
        default_model="gpt-5.5",
        models=("gpt-5.5", "gpt-5.4", "gpt-5.4-mini"),
        doc="",
        api_key_placeholder="不需要 API Key；使用本机 codex login 登录态",
        requires_api_key=False,
    ),
    "minimax-token-global": ProviderPreset(
        id="minimax-token-global",
        name="MiniMax Token Plan (Global)",
        api_type="anthropic-compatible",
        region="global",
        base_url="https://api.minimax.io/anthropic/v1",
        default_model="MiniMax-M2.7",
        models=(
            "MiniMax-M2.7",
            "MiniMax-M2.7-highspeed",
            "MiniMax-M2.5",
            "MiniMax-M2.5-highspeed",
            "MiniMax-M2",
        ),
        doc="https://platform.minimax.io/docs/guides/quickstart",
        api_key_placeholder="MINIMAX_API_KEY",
    ),
    "minimax-token-cn": ProviderPreset(
        id="minimax-token-cn",
        name="MiniMax Token Plan (CN)",
        api_type="anthropic-compatible",
        region="cn",
        base_url="https://api.minimaxi.com/anthropic/v1",
        default_model="MiniMax-M2.7",
        models=(
            "MiniMax-M2.7",
            "MiniMax-M2.7-highspeed",
            "MiniMax-M2.5",
            "MiniMax-M2.5-highspeed",
            "MiniMax-M2",
        ),
        doc="https://platform.minimaxi.com/docs/guides/quickstart",
        api_key_placeholder="MINIMAX_API_KEY",
    ),
    "minimax-coding-global": ProviderPreset(
        id="minimax-coding-global",
        name="MiniMax Coding Plan (Global)",
        api_type="anthropic-compatible",
        region="coding",
        base_url="https://api.minimax.io/anthropic/v1",
        default_model="MiniMax-M2.7",
        models=("MiniMax-M2.7", "MiniMax-M2.7-highspeed", "MiniMax-M2.5", "MiniMax-M2"),
        doc="https://platform.minimax.io/docs/coding-plan/intro",
        api_key_placeholder="MINIMAX_API_KEY",
    ),
    "minimax-coding-cn": ProviderPreset(
        id="minimax-coding-cn",
        name="MiniMax Coding Plan (CN)",
        api_type="anthropic-compatible",
        region="coding",
        base_url="https://api.minimaxi.com/anthropic/v1",
        default_model="MiniMax-M2.7",
        models=("MiniMax-M2.7", "MiniMax-M2.7-highspeed", "MiniMax-M2.5", "MiniMax-M2"),
        doc="https://platform.minimaxi.com/docs/coding-plan/intro",
        api_key_placeholder="MINIMAX_API_KEY",
    ),
    "minimax-openai-cn": ProviderPreset(
        id="minimax-openai-cn",
        name="MiniMax OpenAI-Compatible (CN)",
        api_type="openai-compatible",
        region="cn",
        base_url="https://api.minimaxi.com/v1",
        default_model="MiniMax-M2.7",
        models=("MiniMax-M2.7", "MiniMax-M2", "custom/MiniMax-M2.7"),
        doc="https://platform.minimaxi.com/docs/guides/quickstart",
        api_key_placeholder="MINIMAX_API_KEY",
    ),
    "custom-openai": ProviderPreset(
        id="custom-openai",
        name="自定义 OpenAI-Compatible",
        api_type="openai-compatible",
        region="custom",
        base_url="",
        default_model="",
        models=(),
        doc="https://platform.openai.com/docs/api-reference/chat",
        api_key_placeholder="API Key，可按网关要求留空",
        requires_api_key=False,
    ),
    "mimo": ProviderPreset(
        id="mimo",
        name="Mimo Token Plan",
        api_type="openai-compatible",
        region="cn",
        base_url="https://token-plan-cn.xiaomimimo.com/v1",
        default_model="mimo-v2.5-pro",
        models=("mimo-v2.5-pro",),
        doc="https://docs.mimo.com/",
        api_key_placeholder="MIMO_API_KEY (tp-...)",
    ),
    "custom-anthropic": ProviderPreset(
        id="custom-anthropic",
        name="自定义 Anthropic-Compatible",
        api_type="anthropic-compatible",
        region="custom",
        base_url="",
        default_model="",
        models=(),
        doc="https://docs.anthropic.com/en/api/messages",
        api_key_placeholder="API Key，可按网关要求留空",
        requires_api_key=False,
    ),
}

REGION_LABELS = {
    "trial": "内测免费试用",
    "global": "海外 / 原生厂商",
    "cn": "国内直连",
    "coding": "Token Plan / Coding Plan",
    "local": "本地代理",
    "custom": "自定义",
}


def provider_presets_for_ui() -> dict[str, object]:
    return {
        "defaultProvider": DEFAULT_PROVIDER,
        "regionLabels": REGION_LABELS,
        "providers": {
            provider_id: {
                **asdict(preset),
                "baseURL": preset.base_url,
                "apiType": preset.api_type,
                "defaultModel": preset.default_model,
                "apiKeyPlaceholder": preset.api_key_placeholder,
                "requiresApiKey": preset.requires_api_key,
                "models": list(preset.models),
            }
            for provider_id, preset in PROVIDER_PRESETS.items()
        },
    }


def resolve_provider(provider_id: str | None) -> ProviderPreset:
    key = (provider_id or DEFAULT_PROVIDER).strip() or DEFAULT_PROVIDER
    return PROVIDER_PRESETS.get(key, PROVIDER_PRESETS[DEFAULT_PROVIDER])


def normalize_base_url(raw_base_url: str | None, *, api_type: str, fallback: str = "") -> str:
    value = (raw_base_url or fallback or "").strip()
    if not value:
        raise ValueError("Base URL is required for this provider.")

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Base URL must be a valid http(s) URL: {value}")

    cleaned = value.rstrip("/")
    lower = cleaned.lower()

    if api_type == "openai-compatible":
        for suffix in ("/chat/completions",):
            if lower.endswith(suffix):
                return cleaned[: -len(suffix)].rstrip("/")
    if api_type == "anthropic-compatible" and lower.endswith("/messages"):
        return cleaned[: -len("/messages")].rstrip("/")

    return cleaned


def normalize_chat_completions_endpoint(endpoint: str | None) -> str:
    cleaned = (endpoint or DEFAULT_ZHIPU_ENDPOINT).strip().rstrip("/")
    if not cleaned:
        return DEFAULT_ZHIPU_ENDPOINT
    lower = cleaned.lower()
    if lower.endswith("/chat/completions"):
        return cleaned
    if lower == "https://open.bigmodel.cn/api":
        return DEFAULT_ZHIPU_ENDPOINT
    if lower.endswith("/paas/v4"):
        return f"{cleaned}/chat/completions"
    return cleaned


def openai_chat_completions_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/chat/completions"


def anthropic_messages_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/messages"


def read_error_detail(exc: error.HTTPError) -> str:
    return exc.read().decode("utf-8", errors="replace")


def read_response_json(req: request.Request, *, timeout: int | None = None) -> dict:
    timeout = timeout or int(os.getenv("LLM_HTTP_TIMEOUT_SECONDS", "120"))
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except error.HTTPError:
        raise
    except error.URLError as exc:
        raise RuntimeError(f"Cannot reach model provider: {exc}") from exc

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Provider returned non-JSON response: {body[:300]}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Provider returned unexpected response: {parsed}")
    return parsed


def extract_openai_text(response_json: dict) -> str:
    choices = response_json.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError(f"Unexpected API response (missing choices): {response_json}")

    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise RuntimeError(f"Unexpected API response (missing message): {response_json}")

    content = message.get("content")
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        if parts:
            return "\n".join(parts)

    raise RuntimeError(f"Unexpected API response (missing text content): {response_json}")


def extract_anthropic_text(response_json: dict) -> str:
    content = response_json.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item.get("content"), str):
                    parts.append(item["content"])
        if parts:
            return "\n".join(parts)
    raise RuntimeError(f"Unexpected API response (missing text content): {response_json}")


def validate_api_key(api_key: str, preset: ProviderPreset) -> None:
    if preset.requires_api_key and not api_key:
        raise ValueError(f"{preset.name} API key is required.")


def call_openai_compatible(
    *,
    api_key: str,
    base_url: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    provider_name: str,
    timeout: int | None = None,
    max_tokens: int | None = None,
    extra_payload: dict[str, object] | None = None,
) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens
    if extra_payload:
        payload.update(extra_payload)
    user_agent = "Aegis-Manim/1.0 (https://manim.yishuziyu.cn; contact@yishuziyu.cn)"
    if "Kimi Code" in provider_name:
        user_agent = "Aegis-Manim-Coding-Agent/1.0 (https://manim.yishuziyu.cn; contact@yishuziyu.cn)"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": user_agent,
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = request.Request(
        openai_chat_completions_url(base_url),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        parsed = read_response_json(req, timeout=timeout)
    except error.HTTPError as exc:
        raise RuntimeError(f"{provider_name} HTTP {exc.code}: {read_error_detail(exc)}") from exc
    if "error" in parsed:
        raise RuntimeError(f"{provider_name} error: {parsed['error']}")
    return extract_openai_text(parsed)


def call_anthropic_compatible(
    *,
    api_key: str,
    base_url: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    provider_name: str,
    timeout: int | None = None,
    max_tokens: int | None = None,
) -> str:
    payload = {
        "model": model,
        "max_tokens": max_tokens or 4096,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
        "temperature": temperature,
    }
    headers = {
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
        "User-Agent": "Aegis-Manim/1.0 (https://manim.yishuziyu.cn; contact@yishuziyu.cn)",
    }
    if api_key:
        headers["x-api-key"] = api_key

    req = request.Request(
        anthropic_messages_url(base_url),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        parsed = read_response_json(req, timeout=timeout)
    except error.HTTPError as exc:
        raise RuntimeError(f"{provider_name} HTTP {exc.code}: {read_error_detail(exc)}") from exc
    if "error" in parsed:
        raise RuntimeError(f"{provider_name} error: {parsed['error']}")
    return extract_anthropic_text(parsed)


def build_codex_cli_prompt(*, system_prompt: str, user_prompt: str) -> str:
    return "\n\n".join(
        [
            "你是 Aegis Studio Web 后端调用的代码生成模型。",
            "不要修改文件，不要运行命令，不要解释执行过程。",
            "只输出满足用户需求的完整 Manim Python 代码；不要输出 Markdown 代码块。",
            "## system",
            system_prompt,
            "## user",
            user_prompt,
        ]
    )


def call_codex_cli(
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
    provider_name: str,
) -> str:
    codex_bin = os.getenv("CODEX_BIN", "codex")
    timeout = int(os.getenv("CODEX_CLI_TIMEOUT_SECONDS", "600"))
    prompt = build_codex_cli_prompt(system_prompt=system_prompt, user_prompt=user_prompt)

    with tempfile.TemporaryDirectory(prefix="aegis-codex-") as temp_dir:
        output_file = Path(temp_dir) / "last-message.txt"
        args = [
            codex_bin,
            "-a",
            "never",
            "exec",
            "--skip-git-repo-check",
            "--ephemeral",
            "--ignore-rules",
            "--sandbox",
            "read-only",
            "--output-last-message",
            str(output_file),
            "--model",
            model,
            "-C",
            str(PROJECT_ROOT),
            "-",
        ]
        result = subprocess.run(
            args,
            input=prompt,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"{provider_name} error: {detail or f'exit {result.returncode}'}")
        return output_file.read_text(encoding="utf-8")


def max_tokens_for_provider(provider_id: str, model: str) -> int | None:
    if provider_id == "kimi-code":
        return int(os.getenv("KIMI_CODE_MAX_TOKENS", "8192"))
    if provider_id == "deepseek":
        return int(os.getenv("DEEPSEEK_MAX_TOKENS", "8192"))
    if provider_id.startswith("minimax"):
        return int(os.getenv("MINIMAX_MAX_TOKENS", "8192"))
    raw = os.getenv("LLM_MAX_TOKENS", "").strip()
    return int(raw) if raw else None


def extra_openai_payload_for_provider(provider_id: str, model: str, user_prompt: str) -> dict[str, object]:
    if provider_id != "kimi-code":
        return {}
    digest = hashlib.sha256(f"{model}\n{user_prompt}".encode("utf-8")).hexdigest()
    return {
        "prompt_cache_key": f"aegis-manim-{digest[:24]}",
        "safety_identifier": f"aegis-public-{digest[24:48]}",
    }


def generate_code_with_provider(
    *,
    provider_id: str | None,
    api_key: str,
    base_url: str | None,
    endpoint: str | None,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    timeout: int | None = None,
) -> tuple[str, ProviderPreset, str]:
    preset = resolve_provider(provider_id)
    validate_api_key(api_key, preset)

    selected_model = (model or preset.default_model).strip()
    if not selected_model:
        raise ValueError(f"{preset.name} model is required.")

    if preset.api_type == "codex-cli":
        return (
            call_codex_cli(
                model=selected_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                provider_name=preset.name,
            ),
            preset,
            "codex exec",
        )

    if preset.api_type == "openai-compatible":
        if endpoint and not base_url:
            normalized_endpoint = normalize_chat_completions_endpoint(endpoint)
            normalized_base = normalize_base_url(
                normalized_endpoint,
                api_type=preset.api_type,
                fallback=preset.base_url,
            )
        else:
            normalized_base = normalize_base_url(
                base_url,
                api_type=preset.api_type,
                fallback=preset.base_url,
            )
        return (
            call_openai_compatible(
                api_key=api_key,
                base_url=normalized_base,
                model=selected_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                provider_name=preset.name,
                timeout=timeout,
                max_tokens=max_tokens_for_provider(preset.id, selected_model),
                extra_payload=extra_openai_payload_for_provider(
                    preset.id,
                    selected_model,
                    user_prompt,
                ),
            ),
            preset,
            openai_chat_completions_url(normalized_base),
        )

    if preset.api_type == "anthropic-compatible":
        normalized_base = normalize_base_url(
            base_url,
            api_type=preset.api_type,
            fallback=preset.base_url,
        )
        return (
            call_anthropic_compatible(
                api_key=api_key,
                base_url=normalized_base,
                model=selected_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                provider_name=preset.name,
                timeout=timeout,
                max_tokens=max_tokens_for_provider(preset.id, selected_model),
            ),
            preset,
            anthropic_messages_url(normalized_base),
        )

    raise ValueError(f"Unsupported provider protocol: {preset.api_type}")

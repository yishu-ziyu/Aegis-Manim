from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORE_DIR = PROJECT_ROOT / "core"
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api import index as gateway  # noqa: E402
from llm_providers import redact_client_secrets, resolve_provider  # noqa: E402
from manim_agent import is_placeholder_api_key  # noqa: E402

LIVE_BYOK_CANDIDATES = (
    ("MINIMAX_API_KEY", "minimax-token-cn"),
    ("ANTHROPIC_AUTH_TOKEN", "minimax-token-cn"),
    ("DEEPSEEK_API_KEY", "deepseek"),
    ("OPENAI_API_KEY", "openai"),
    ("BIGMODEL_API_KEY", "zhipu"),
    ("KIMI_CODE_API_KEY", "kimi-code"),
    ("MOONSHOT_API_KEY", "moonshot-kimi"),
    ("MIMO_API_KEY", "mimo"),
)


def discover_live_byok_provider() -> tuple[str, str] | None:
    """Return (provider_id, env_name) for the first usable live key. Never returns the secret."""
    for env_name, provider_id in LIVE_BYOK_CANDIDATES:
        value = os.getenv(env_name, "").strip()
        if value and not is_placeholder_api_key(value):
            return provider_id, env_name
    return None


def run_live_byok_generate() -> int:
    found = discover_live_byok_provider()
    if found is None:
        print("SKIP: no live BYOK key in environment")
        return 2

    provider_id, env_name = found
    api_key = os.environ.get(env_name, "").strip()
    provider = resolve_provider(provider_id)
    status, response = gateway.generate_manim_code_for_gateway(
        {
            "prompt": "用一两句话解释消费者剩余，并写成很短的 Manim 教学草稿。",
            "provider": provider_id,
            "apiKey": api_key,
            "model": provider.default_model,
            "baseUrl": provider.base_url,
            "sceneName": "GeneratedScene",
        }
    )
    dumped = json.dumps(response, ensure_ascii=False)
    echoed = api_key in dumped
    has_code = "class " in str(response.get("code") or "")
    ok = (
        status == 200
        and response.get("ok") is True
        and response.get("authMode") == "byok"
        and has_code
        and not echoed
    )
    print(
        f"provider={provider_id} status={status} authMode={response.get('authMode')} "
        f"code={has_code} echoed={echoed}"
    )
    if not ok:
        print("error=" + redact_client_secrets(str(response.get("error") or ""), api_key))
        return 1
    print("LIVE_BYOK_OK")
    return 0


def main() -> int:
    return run_live_byok_generate()


if __name__ == "__main__":
    raise SystemExit(main())

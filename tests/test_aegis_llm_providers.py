from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORE_DIR = PROJECT_ROOT / "core"
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

import llm_providers  # noqa: E402
from llm_providers import (  # noqa: E402
    anthropic_messages_url,
    generate_code_with_provider,
    normalize_base_url,
    normalize_chat_completions_endpoint,
    openai_chat_completions_url,
    resolve_provider,
)


class AegisLLMProviderTest(unittest.TestCase):
    def test_normalize_openai_base_url_trims_chat_completion_suffix(self) -> None:
        base_url = normalize_base_url(
            "https://api.example.com/v1/chat/completions",
            api_type="openai-compatible",
        )

        assert base_url == "https://api.example.com/v1"
        assert openai_chat_completions_url(base_url) == "https://api.example.com/v1/chat/completions"

    def test_normalize_anthropic_base_url_trims_messages_suffix(self) -> None:
        base_url = normalize_base_url(
            "https://api.minimaxi.com/anthropic/v1/messages",
            api_type="anthropic-compatible",
        )

        assert base_url == "https://api.minimaxi.com/anthropic/v1"
        assert anthropic_messages_url(base_url) == "https://api.minimaxi.com/anthropic/v1/messages"

    def test_legacy_zhipu_endpoint_normalization_keeps_compatibility(self) -> None:
        assert normalize_chat_completions_endpoint("https://open.bigmodel.cn/api") == "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        assert normalize_chat_completions_endpoint("https://open.bigmodel.cn/api/paas/v4") == "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    def test_codex_local_proxy_allows_empty_api_key(self) -> None:
        provider = resolve_provider("codex-local-proxy")

        assert provider.api_type == "openai-compatible"
        assert not provider.requires_api_key

    def test_codex_cli_provider_requires_no_key_or_base_url(self) -> None:
        provider = resolve_provider("codex-cli")

        assert provider.api_type == "codex-cli"
        assert provider.base_url == ""
        assert not provider.requires_api_key

    def test_codex_cli_provider_uses_local_codex_runner(self) -> None:
        calls = []

        def fake_call_codex_cli(**kwargs: object) -> str:
            calls.append(kwargs)
            return "from manim import *\n"

        original = llm_providers.call_codex_cli
        llm_providers.call_codex_cli = fake_call_codex_cli
        try:
            code, provider, resolved_endpoint = generate_code_with_provider(
                provider_id="codex-cli",
                api_key="",
                base_url="",
                endpoint=None,
                model="gpt-5.5",
                system_prompt="system",
                user_prompt="user",
                temperature=0.2,
            )
        finally:
            llm_providers.call_codex_cli = original

        assert code == "from manim import *\n"
        assert provider.id == "codex-cli"
        assert resolved_endpoint == "codex exec"
        assert calls == [
            {
                "model": "gpt-5.5",
                "system_prompt": "system",
                "user_prompt": "user",
                "provider_name": "Codex CLI 登录态（本机）",
            }
        ]


if __name__ == "__main__":
    unittest.main()

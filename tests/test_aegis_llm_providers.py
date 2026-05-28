from __future__ import annotations

import sys
import json
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

    def test_kimi_code_provider_uses_official_anthropic_coding_endpoint(self) -> None:
        provider = resolve_provider("kimi-code")

        assert provider.api_type == "anthropic-compatible"
        assert provider.base_url == "https://api.kimi.com/coding"
        assert anthropic_messages_url(provider.base_url) == "https://api.kimi.com/coding/messages"
        assert provider.default_model == "kimi-for-coding"
        assert provider.requires_api_key

    def test_deepseek_provider_uses_official_openai_compatible_endpoint(self) -> None:
        provider = resolve_provider("deepseek")

        assert provider.api_type == "openai-compatible"
        assert provider.base_url == "https://api.deepseek.com"
        assert openai_chat_completions_url(provider.base_url) == "https://api.deepseek.com/chat/completions"
        assert provider.default_model == "deepseek-v4-flash"
        assert "deepseek-v4-flash" in provider.models
        assert provider.requires_api_key

    def test_deepseek_openai_request_uses_configured_token_budget_without_leaking_key(self) -> None:
        captured: dict[str, object] = {}

        def fake_read_response_json(req, timeout=None):
            captured["url"] = req.full_url
            captured["headers"] = dict(req.header_items())
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return {"choices": [{"message": {"content": "from manim import *\n"}}]}

        original = llm_providers.read_response_json
        llm_providers.read_response_json = fake_read_response_json
        try:
            code, provider, endpoint = generate_code_with_provider(
                provider_id="deepseek",
                api_key="server-key",
                base_url="",
                endpoint=None,
                model="deepseek-v4-flash",
                system_prompt="system",
                user_prompt="explain two-part pricing",
                temperature=0.2,
                timeout=12,
            )
        finally:
            llm_providers.read_response_json = original

        payload = captured["payload"]
        assert code == "from manim import *\n"
        assert provider.id == "deepseek"
        assert endpoint == "https://api.deepseek.com/chat/completions"
        assert captured["url"] == endpoint
        assert isinstance(payload, dict)
        assert payload["model"] == "deepseek-v4-flash"
        assert payload["max_tokens"] == 8192
        assert "server-key" not in json.dumps(payload)

    def test_kimi_code_anthropic_request_uses_coding_endpoint(self) -> None:
        captured: dict[str, object] = {}

        def fake_read_response_json(req, timeout=None):
            captured["url"] = req.full_url
            captured["headers"] = dict(req.header_items())
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return {"content": [{"type": "text", "text": "from manim import *\n"}]}

        original = llm_providers.read_response_json
        llm_providers.read_response_json = fake_read_response_json
        try:
            code, provider, endpoint = generate_code_with_provider(
                provider_id="kimi-code",
                api_key="server-key",
                base_url="",
                endpoint=None,
                model="kimi-for-coding",
                system_prompt="system",
                user_prompt="explain tax wedge",
                temperature=0.2,
                timeout=12,
            )
        finally:
            llm_providers.read_response_json = original

        payload = captured["payload"]
        assert code == "from manim import *\n"
        assert provider.id == "kimi-code"
        assert endpoint == "https://api.kimi.com/coding/messages"
        assert captured["url"] == endpoint
        assert isinstance(payload, dict)
        assert payload["model"] == "kimi-for-coding"
        assert payload["max_tokens"] == 8192
        assert payload["system"] == "system"
        assert captured["headers"]["X-api-key"] == "server-key"
        assert "server-key" not in json.dumps(payload)

    def test_minimax_coding_cn_provider_uses_anthropic_messages_endpoint(self) -> None:
        provider = resolve_provider("minimax-coding-cn")

        assert provider.api_type == "anthropic-compatible"
        assert provider.base_url == "https://api.minimaxi.com/anthropic/v1"
        assert anthropic_messages_url(provider.base_url) == "https://api.minimaxi.com/anthropic/v1/messages"
        assert provider.default_model == "MiniMax-M2.7"
        assert provider.requires_api_key

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

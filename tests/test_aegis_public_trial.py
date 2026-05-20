from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api import index as gateway  # noqa: E402


class AegisPublicTrialTest(unittest.TestCase):
    def setUp(self) -> None:
        self._old_kimi = os.environ.get("KIMI_CODE_API_KEY")
        self._old_minimax = os.environ.get("MINIMAX_API_KEY")
        os.environ.pop("KIMI_CODE_API_KEY", None)
        os.environ.pop("MINIMAX_API_KEY", None)

    def tearDown(self) -> None:
        if self._old_kimi is None:
            os.environ.pop("KIMI_CODE_API_KEY", None)
        else:
            os.environ["KIMI_CODE_API_KEY"] = self._old_kimi
        if self._old_minimax is None:
            os.environ.pop("MINIMAX_API_KEY", None)
        else:
            os.environ["MINIMAX_API_KEY"] = self._old_minimax

    def test_public_config_exposes_only_safe_trial_choices(self) -> None:
        config = gateway.public_provider_config()
        providers = config["providers"]

        assert config["defaultProvider"] == "trial-kimi-priority"
        assert set(providers) == {"trial-kimi-priority", "trial-minimax-direct"}
        assert providers["trial-kimi-priority"]["serverManaged"] is True
        assert providers["trial-kimi-priority"]["requiresApiKey"] is False
        assert providers["trial-kimi-priority"]["hideApiKey"] is True
        assert "baseURL" not in providers["trial-kimi-priority"]
        assert "apiType" not in providers["trial-kimi-priority"]

    def test_trial_uses_server_kimi_key_without_client_key(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_generate_code_with_llm(**kwargs: object) -> tuple[str, object, str]:
            calls.append(kwargs)
            provider = gateway.resolve_provider(str(kwargs["provider_id"]))
            return "from manim import *\nclass GeneratedScene(Scene):\n    pass\n", provider, "hidden"

        original = gateway.generate_code_with_llm
        os.environ["KIMI_CODE_API_KEY"] = "server-kimi-key"
        os.environ["MINIMAX_API_KEY"] = "server-minimax-key"
        gateway.generate_code_with_llm = fake_generate_code_with_llm
        try:
            status, response = gateway.generate_manim_code_for_gateway(
                {
                    "prompt": "解释消费者剩余",
                    "provider": "trial-kimi-priority",
                    "apiKey": "client-key-must-be-ignored",
                    "baseUrl": "https://evil.example/v1",
                    "endpoint": "https://evil.example/v1/chat/completions",
                }
            )
        finally:
            gateway.generate_code_with_llm = original

        assert status == 200
        assert response["ok"] is True
        assert response["provider"] == "trial-kimi-priority"
        assert response["endpoint"] == "server-managed-trial"
        assert calls[0]["provider_id"] == "kimi-code"
        assert calls[0]["api_key"] == "server-kimi-key"
        assert calls[0]["base_url"] == ""
        assert calls[0]["endpoint"] == ""

    def test_trial_falls_back_to_minimax_when_kimi_fails(self) -> None:
        calls: list[str] = []

        def fake_generate_code_with_llm(**kwargs: object) -> tuple[str, object, str]:
            provider_id = str(kwargs["provider_id"])
            calls.append(provider_id)
            if provider_id == "kimi-code":
                raise RuntimeError("Kimi Code API HTTP 429: quota exceeded")
            provider = gateway.resolve_provider(provider_id)
            return "from manim import *\nclass GeneratedScene(Scene):\n    pass\n", provider, "hidden"

        original = gateway.generate_code_with_llm
        os.environ["KIMI_CODE_API_KEY"] = "server-kimi-key"
        os.environ["MINIMAX_API_KEY"] = "server-minimax-key"
        gateway.generate_code_with_llm = fake_generate_code_with_llm
        try:
            status, response = gateway.generate_manim_code_for_gateway(
                {"prompt": "解释税收楔子", "provider": "trial-kimi-priority"}
            )
        finally:
            gateway.generate_code_with_llm = original

        assert status == 200
        assert response["ok"] is True
        assert calls == ["kimi-code", "minimax-coding-cn"]
        assert "MiniMax" in "\n".join(response["warnings"])
        assert "detail" not in response

    def test_public_gateway_rejects_arbitrary_provider_and_long_prompt(self) -> None:
        status, response = gateway.generate_manim_code_for_gateway(
            {"prompt": "解释消费者剩余", "provider": "custom-openai"}
        )
        assert status == 400
        assert "内置免费试用模型" in response["error"]

        status, response = gateway.generate_manim_code_for_gateway(
            {"prompt": "x" * (gateway.MAX_PUBLIC_PROMPT_CHARS + 1)}
        )
        assert status == 400
        assert "问题太长" in response["error"]


if __name__ == "__main__":
    unittest.main()

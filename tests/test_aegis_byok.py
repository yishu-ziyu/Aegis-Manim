from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORE_DIR = PROJECT_ROOT / "core"
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api import index as gateway  # noqa: E402
import llm_providers  # noqa: E402
import web_app  # noqa: E402


def _scene(text: str = "消费者剩余") -> str:
    return (
        "from manim import *\nclass GeneratedScene(Scene):\n"
        f"    def construct(self):\n        self.play(Write(Text('{text}', font_size=28)))\n"
    )


class AegisByokTest(unittest.TestCase):
    def test_local_provider_ui_marks_byok_and_local_only(self) -> None:
        config = llm_providers.provider_presets_for_ui()
        providers = config["providers"]

        assert config["providerStorageKey"] == "aegis.provider"
        assert providers["openai"]["byok"] is True
        assert providers["openai"]["keyHint"]
        assert providers["codex-cli"]["localOnly"] is True
        assert providers["codex-cli"]["byok"] is False
        assert providers["custom-openai"]["byok"] is True

    def test_gateway_byok_uses_client_key_and_does_not_echo_it(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_generate_code_with_llm(**kwargs: object):
            calls.append(kwargs)
            return _scene(), "OpenAI API", "https://api.openai.com/v1/chat/completions"

        with patch.object(gateway, "generate_code_with_llm", fake_generate_code_with_llm):
            status, response = gateway.generate_manim_code_for_gateway(
                {
                    "prompt": "解释消费者剩余",
                    "provider": "openai",
                    "apiKey": "sk-live-secret-key",
                    "model": "gpt-4o-mini",
                    "baseUrl": "https://api.openai.com/v1",
                }
            )

        assert status == 200
        assert response["ok"] is True
        assert response["authMode"] == "byok"
        assert response["provider"] == "openai"
        assert calls[0]["api_key"] == "sk-live-secret-key"
        assert calls[0]["provider_id"] == "openai"
        assert "sk-live-secret-key" not in json.dumps(response)

    def test_gateway_byok_requires_key_for_openai(self) -> None:
        status, response = gateway.generate_manim_code_for_gateway(
            {"prompt": "解释消费者剩余", "provider": "openai"}
        )

        assert status == 400
        assert response["ok"] is False
        assert "API Key" in str(response["error"])

    def test_gateway_trial_still_ignores_client_key(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_generate_code_with_llm(**kwargs: object):
            calls.append(kwargs)
            provider = gateway.resolve_provider(str(kwargs["provider_id"]))
            return _scene(), provider, "hidden"

        old_key = os.environ.get("MINIMAX_API_KEY")
        os.environ["MINIMAX_API_KEY"] = "server-minimax-key"
        try:
            with patch.object(gateway, "generate_code_with_llm", fake_generate_code_with_llm):
                status, response = gateway.generate_manim_code_for_gateway(
                    {
                        "prompt": "解释消费者剩余",
                        "provider": "trial-minimax-direct",
                        "apiKey": "client-key-must-be-ignored",
                    }
                )
        finally:
            if old_key is None:
                os.environ.pop("MINIMAX_API_KEY", None)
            else:
                os.environ["MINIMAX_API_KEY"] = old_key

        assert status == 200
        assert response["provider"] == "trial-minimax-direct"
        assert calls[0]["api_key"] == "server-minimax-key"
        assert "client-key-must-be-ignored" not in json.dumps(response)

    def test_page_byok_controls_exist_in_local_and_cloud_html(self) -> None:
        local_html = web_app.make_index_html()
        cloud_html = gateway.build_index_html()

        for html in (local_html, cloud_html):
            assert 'id="modeTrialBtn"' in html
            assert 'id="modeByokBtn"' in html
            assert 'id="byokPanel"' in html
            assert 'id="saveKeyBtn"' in html
            assert 'id="forgetKeyBtn"' in html
            assert "aegis.byok.vault.v1" in html
            assert "function applyMode" in html
            assert "savedVaultKey" in html
            assert "API Key 只用于本次生成，不写入仓库。" in html

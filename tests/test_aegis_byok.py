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
from manim_agent import is_placeholder_api_key  # noqa: E402
import web_app  # noqa: E402

SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
import live_byok_smoke  # noqa: E402


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
        assert "MiniMax M3 与 Mimo 编程" in cloud_html

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
            assert "先在密钥库填写 API Key" in html
            assert 'id="resultEmpty"' in html
            assert 'id="vaultList"' in html
            assert "forgetAllKeys" in html
            assert "keyLooksUsable" in html
            assert 'id="preflightBtn"' in html
            assert 'id="preflightStatus"' in html
            assert "function preflightCurrentKey" in html
            assert 'fetch("/api/byok/preflight"' in html
            assert 'id="communityDrawer"' in html
            assert "测试连通" in html
            assert "粘贴完整 API Key，不要填环境变量名" in html
            assert 'placeholder="粘贴完整 API Key，不要填环境变量名"' in html
            assert "输入你自己的 API Key" not in html
            assert "模型与接口" in html
            assert "writeVaultEntry" in html
            assert 'id="keyNotice"' in html
            assert "keyNotice.hidden" in html
            assert "function secretInPayload" in html
            assert "function hideSecret" in html
            assert 'id="authTag"' in html
            assert "boot-byok" in html
            assert 'data-default-mode="' in html
            assert '" empty"' in html
            assert "const featured" in html
            assert "minimax-coding-cn" in html
            assert '"mimo"' in html
            assert "密钥只存在这台浏览器。请粘贴完整 Key，不要填环境变量名。" in html
            assert 'localStorage.getItem("aegis.mode")' in html
            assert "Auth: 自带密钥" in html
            assert "生成接口返回了不该出现的密钥" in html
            assert "对齐接口返回了不该出现的密钥" in html
            assert "verifiedAt" in html
            assert "已连通" in html
            assert "function customEndpointReady" in html
            assert "已使用你的密钥，未写入服务器。" in html
            assert "currentMode !== \"byok\"" in html
            assert "用自带密钥生成" in html
            assert "用已连通的密钥生成" in html

    def test_gateway_byok_redacts_key_from_value_error(self) -> None:
        def boom(**kwargs: object):
            raise ValueError("upstream rejected " + str(kwargs["api_key"]))

        with patch.object(gateway, "generate_code_with_llm", boom):
            status, response = gateway.generate_manim_code_for_gateway(
                {
                    "prompt": "解释消费者剩余",
                    "provider": "openai",
                    "apiKey": "sk-live-secret-key",
                }
            )

        dumped = json.dumps(response)
        assert status == 400
        assert response["ok"] is False
        assert "sk-live-secret-key" not in dumped
        assert "[redacted]" in response["error"]

    def test_preflight_uses_client_key_and_does_not_echo_it(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_generate_code_with_provider(**kwargs: object):
            calls.append(kwargs)
            return "ok", gateway.resolve_provider("openai"), "https://api.openai.com/v1/chat/completions"

        with patch.object(gateway, "generate_code_with_provider", fake_generate_code_with_provider):
            status, response = gateway.preflight_byok_provider(
                {
                    "provider": "openai",
                    "apiKey": "sk-live-secret-key",
                    "model": "gpt-4o-mini",
                    "baseUrl": "https://api.openai.com/v1",
                }
            )

        dumped = json.dumps(response)
        assert status == 200
        assert response["ok"] is True
        assert response["authMode"] == "byok"
        assert response["provider"] == "openai"
        assert calls[0]["api_key"] == "sk-live-secret-key"
        assert calls[0]["max_tokens"] == gateway.BYOK_PREFLIGHT_MAX_TOKENS
        assert "sk-live-secret-key" not in dumped

    def test_preflight_requires_key_and_rejects_trial(self) -> None:
        missing = gateway.preflight_byok_provider({"provider": "openai"})
        assert missing[0] == 400
        assert "API Key" in str(missing[1]["error"])

        trial = gateway.preflight_byok_provider(
            {"provider": "trial-minimax-direct", "apiKey": "sk-live-secret-key"}
        )
        assert trial[0] == 400
        assert "免费试用" in trial[1]["error"]
        assert "sk-live-secret-key" not in json.dumps(trial[1])

        local_only = gateway.preflight_byok_provider(
            {"provider": "codex-cli", "apiKey": "sk-live-secret-key"}
        )
        assert local_only[0] == 400
        assert "只能在本机使用" in local_only[1]["error"]

    def test_preflight_redacts_key_from_value_error(self) -> None:
        def boom(**kwargs: object):
            raise ValueError("probe failed for " + str(kwargs["api_key"]))

        with patch.object(gateway, "generate_code_with_provider", boom):
            status, response = gateway.preflight_byok_provider(
                {
                    "provider": "openai",
                    "apiKey": "sk-live-secret-key",
                    "baseUrl": "https://api.openai.com/v1",
                }
            )

        assert status == 400
        assert "sk-live-secret-key" not in json.dumps(response)
        assert "[redacted]" in response["error"]

    def test_asgi_byok_generate_and_preflight_do_not_echo_key(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("aegis_vercel_asgi_app", PROJECT_ROOT / "app.py")
        assert spec and spec.loader
        vercel_asgi = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(vercel_asgi)

        async def call_asgi(path: str, payload: dict[str, object]) -> tuple[int, dict[str, object]]:
            raw = json.dumps(payload).encode("utf-8")
            messages = [{"type": "http.request", "body": raw, "more_body": False}]
            events: list[dict[str, object]] = []

            async def receive() -> dict[str, object]:
                if messages:
                    return messages.pop(0)
                return {"type": "http.request", "body": b"", "more_body": False}

            async def send(message: dict[str, object]) -> None:
                events.append(message)

            await vercel_asgi.app(
                {"type": "http", "method": "POST", "path": path, "query_string": b""},
                receive,
                send,
            )
            status = next(event["status"] for event in events if event["type"] == "http.response.start")
            body = b"".join(event.get("body", b"") for event in events if event["type"] == "http.response.body")
            return int(status), json.loads(body.decode("utf-8")) if body else {}

        secret = "sk-http-smoke-secret-key"

        def fake_generate_code_with_llm(**kwargs: object):
            return (
                _scene(),
                "OpenAI API",
                "https://api.openai.com/v1/chat/completions",
            )

        def fake_generate_code_with_provider(**kwargs: object):
            return "ok", gateway.resolve_provider("openai"), "https://api.openai.com/v1/chat/completions"

        import asyncio

        with patch.object(gateway, "generate_code_with_llm", fake_generate_code_with_llm):
            generate_status, generate_body = asyncio.run(
                call_asgi(
                    "/api/generate",
                    {
                        "prompt": "解释消费者剩余",
                        "provider": "openai",
                        "apiKey": secret,
                        "model": "gpt-4o-mini",
                        "baseUrl": "https://api.openai.com/v1",
                    },
                )
            )
        with patch.object(gateway, "generate_code_with_provider", fake_generate_code_with_provider):
            preflight_status, preflight_body = asyncio.run(
                call_asgi(
                    "/api/byok/preflight",
                    {
                        "provider": "openai",
                        "apiKey": secret,
                        "model": "gpt-4o-mini",
                        "baseUrl": "https://api.openai.com/v1",
                    },
                )
            )

        assert generate_status == 200
        assert generate_body["ok"] is True
        assert generate_body["authMode"] == "byok"
        assert secret not in json.dumps(generate_body)
        assert preflight_status == 200
        assert preflight_body["ok"] is True
        assert preflight_body["authMode"] == "byok"
        assert secret not in json.dumps(preflight_body)

    def test_local_generate_job_redacts_key_and_marks_byok(self) -> None:
        secret = "sk-live-secret-key"

        def boom(**kwargs: object):
            raise RuntimeError("upstream rejected " + str(kwargs["api_key"]))

        job_id = web_app.create_job("解释消费者剩余为什么重要")
        with patch.object(web_app, "generate_code_with_llm", boom):
            web_app.run_generate_job(
                job_id,
                {
                    "prompt": "解释消费者剩余为什么重要",
                    "provider": "openai",
                    "apiKey": secret,
                    "noRender": True,
                },
            )
        snapshot = web_app.job_snapshot(job_id)
        dumped = json.dumps(snapshot)
        assert snapshot is not None
        assert snapshot["status"] == "failed"
        assert secret not in dumped
        assert "[redacted]" in json.dumps(snapshot.get("error") or {})

    def test_local_generate_job_success_sets_byok_auth_mode(self) -> None:
        secret = "sk-live-secret-key"

        def fake_generate_code_with_llm(**kwargs: object):
            return _scene(), "OpenAI API", "https://api.openai.com/v1/chat/completions"

        job_id = web_app.create_job("解释消费者剩余为什么重要")
        with patch.object(web_app, "generate_code_with_llm", fake_generate_code_with_llm):
            web_app.run_generate_job(
                job_id,
                {
                    "prompt": "解释消费者剩余为什么重要",
                    "provider": "openai",
                    "apiKey": secret,
                    "noRender": True,
                },
            )
        snapshot = web_app.job_snapshot(job_id)
        dumped = json.dumps(snapshot)
        assert snapshot is not None
        assert snapshot["status"] == "succeeded"
        assert snapshot["result"]["authMode"] == "byok"
        assert secret not in dumped

    def test_gateway_align_uses_client_key_and_does_not_echo_it(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_generate_code_with_llm(**kwargs: object):
            calls.append(kwargs)
            return (
                '{"mode":"posthoc_metadata","confidence":"high","warnings":[],'
                '"segments":[{"id":"seg_1","title":"剩余","script":"解释消费者剩余",'
                '"visualIntent":"标出剩余","startTime":0,"endTime":2,"confidence":"high"}]}',
                "OpenAI API",
                "https://api.openai.com/v1/chat/completions",
            )

        with patch.object(gateway, "generate_code_with_llm", fake_generate_code_with_llm):
            status, response = gateway.align_script_for_gateway(
                {
                    "prompt": "解释消费者剩余为什么会出现",
                    "code": _scene(),
                    "provider": "openai",
                    "apiKey": "sk-live-secret-key",
                    "model": "gpt-4o-mini",
                    "baseUrl": "https://api.openai.com/v1",
                    "videoDuration": 8,
                }
            )

        dumped = json.dumps(response)
        assert status == 200
        assert response["ok"] is True
        assert response["authMode"] == "byok"
        assert calls[0]["api_key"] == "sk-live-secret-key"
        assert "sk-live-secret-key" not in dumped

    def test_gateway_align_trial_ignores_client_key(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_generate_code_with_llm(**kwargs: object):
            calls.append(kwargs)
            return (
                '{"mode":"posthoc_metadata","confidence":"medium","warnings":[],'
                '"segments":[{"id":"seg_1","title":"剩余","script":"解释消费者剩余",'
                '"visualIntent":"标出剩余","startTime":0,"endTime":2,"confidence":"medium"}]}',
                "MiniMax",
                "hidden",
            )

        old_key = os.environ.get("MINIMAX_API_KEY")
        os.environ["MINIMAX_API_KEY"] = "server-minimax-key"
        try:
            with patch.object(gateway, "generate_code_with_llm", fake_generate_code_with_llm):
                status, response = gateway.align_script_for_gateway(
                    {
                        "prompt": "解释消费者剩余为什么会出现",
                        "code": _scene(),
                        "provider": "trial-minimax-direct",
                        "apiKey": "client-key-must-be-ignored",
                        "videoDuration": 8,
                    }
                )
        finally:
            if old_key is None:
                os.environ.pop("MINIMAX_API_KEY", None)
            else:
                os.environ["MINIMAX_API_KEY"] = old_key

        dumped = json.dumps(response)
        assert status == 200
        assert response["authMode"] == "trial"
        assert calls[0]["api_key"] == "server-minimax-key"
        assert "client-key-must-be-ignored" not in dumped
        assert "server-minimax-key" not in dumped

    def test_gateway_align_redacts_key_from_fallback_warning(self) -> None:
        def boom(**kwargs: object):
            raise RuntimeError("upstream rejected " + str(kwargs["api_key"]))

        with patch.object(gateway, "generate_code_with_llm", boom):
            status, response = gateway.align_script_for_gateway(
                {
                    "prompt": "解释消费者剩余为什么会出现",
                    "code": _scene(),
                    "provider": "openai",
                    "apiKey": "sk-live-secret-key",
                    "baseUrl": "https://api.openai.com/v1",
                }
            )

        dumped = json.dumps(response, ensure_ascii=False)
        assert status == 200
        assert response["ok"] is True
        assert "sk-live-secret-key" not in dumped
        assert "[redacted]" in dumped

    def test_live_byok_smoke_discovers_env_without_returning_secret(self) -> None:
        empty = {name: "" for name, _provider_id in live_byok_smoke.LIVE_BYOK_CANDIDATES}
        with patch.dict(os.environ, empty, clear=False):
            assert live_byok_smoke.discover_live_byok_provider() is None
            assert live_byok_smoke.run_live_byok_generate() == 2
        with patch.dict(
            os.environ,
            {**empty, "OPENAI_API_KEY": "sk-live-secret-key-123456"},
            clear=False,
        ):
            assert live_byok_smoke.discover_live_byok_provider() == ("openai", "OPENAI_API_KEY")
        with patch.dict(
            os.environ,
            {**empty, "MINIMAX_API_KEY": "sk-cp-live-minimax-token-plan-key"},
            clear=False,
        ):
            assert live_byok_smoke.discover_live_byok_provider() == ("minimax-token-cn", "MINIMAX_API_KEY")

    def test_local_web_exposes_preflight_route(self) -> None:
        source = Path(web_app.__file__).read_text(encoding="utf-8")
        assert 'if route == "/api/byok/preflight":' in source
        assert "proxy_cloud_preflight" in source
        assert "preflight_byok_provider" in source
        assert "proxy_cloud_align" in source
        assert "align_script_for_gateway" in Path(PROJECT_ROOT / "app.py").read_text(encoding="utf-8")

    def test_placeholder_api_key_rejects_env_names_and_examples(self) -> None:
        assert is_placeholder_api_key("OPENAI_API_KEY")
        assert is_placeholder_api_key("BIGMODEL_API_KEY")
        assert is_placeholder_api_key("your_api_key")
        assert is_placeholder_api_key("sk-xxx")
        assert not is_placeholder_api_key("")
        assert not is_placeholder_api_key("sk-live-secret-key-123456")

    def test_gateway_rejects_placeholder_and_env_name_keys(self) -> None:
        for key in ("OPENAI_API_KEY", "your_api_key_here"):
            status, response = gateway.generate_manim_code_for_gateway(
                {
                    "prompt": "解释消费者剩余",
                    "provider": "openai",
                    "apiKey": key,
                }
            )
            assert status == 400
            assert response["ok"] is False
            assert "真实 API Key" in response["error"]
            assert key not in json.dumps(response)

            preflight = gateway.preflight_byok_provider({"provider": "openai", "apiKey": key})
            assert preflight[0] == 400
            assert "真实 API Key" in preflight[1]["error"]
            assert key not in json.dumps(preflight[1])

    def test_alignment_fallback_redacts_key(self) -> None:
        secret = "sk-align-secret-key"
        handler = object.__new__(web_app.AegisWebHandler)

        def boom(**kwargs: object):
            raise RuntimeError("upstream rejected " + str(kwargs["api_key"]))

        with patch.object(web_app, "generate_code_with_llm", boom):
            alignment = handler._build_alignment_response(
                request_id="align-test",
                prompt="解释消费者剩余为什么会出现",
                code=_scene(),
                scene_name="GeneratedScene",
                video_duration=8.0,
                provider_id="openai",
                api_key=secret,
                base_url="https://api.openai.com/v1",
                endpoint=None,
                model="gpt-4o-mini",
                temperature=0.2,
            )

        dumped = json.dumps(alignment, ensure_ascii=False)
        assert secret not in dumped
        assert "[redacted]" in dumped

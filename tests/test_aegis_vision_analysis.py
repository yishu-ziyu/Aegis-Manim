from __future__ import annotations

import base64
import io
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORE_DIR = PROJECT_ROOT / "core"
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

import vision_analysis  # noqa: E402


TINY_PNG_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADUlEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"


class AegisVisionAnalysisTest(unittest.TestCase):
    def setUp(self) -> None:
        self._old_env = {
            key: os.environ.get(key)
            for key in (
                "AEGIS_VISION_PUBLIC_ENABLED",
                "VISION_BACKEND_URL",
                "VISION_BACKEND_API_KEY",
                "KIMI_VISION_CLI_COMMAND",
                "GEMINI_API_KEY",
                "GOOGLE_API_KEY",
                "GEMINI_VISION_MODEL",
                "GEMINI_VISION_BASE_URL",
                "GEMINI_VISION_RETRIES",
                "GEMINI_VISION_RETRY_BACKOFF_SECONDS",
                "VISION_API_KEY",
                "VISION_BASE_URL",
                "VISION_MODEL",
                "VISION_PROVIDER_NAME",
                "VISION_RETRIES",
                "VISION_RETRY_BACKOFF_SECONDS",
                "VISION_OCR_COMMAND",
                "KIMI_VISION_API_KEY",
                "MOONSHOT_API_KEY",
                "KIMI_CODE_API_KEY",
                "MIMO_API_KEY",
                "MIMO_VISION_BASE_URL",
                "MIMO_VISION_MODEL",
                "MIMO_VISION_TIMEOUT_SECONDS",
                "MIMO_VISION_MAX_TOKENS",
                "MIMO_VISION_RETRIES",
                "MIMO_VISION_RETRY_BACKOFF_SECONDS",
            )
        }
        for key in self._old_env:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        for key, value in self._old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_missing_vision_provider_reports_cli_bridge_option(self) -> None:
        os.environ["KIMI_CODE_API_KEY"] = "server-kimi-code-key"

        status, response = vision_analysis.analyze_image_payload(
            {"imageData": TINY_PNG_BASE64, "mimeType": "image/png"}
        )

        assert status == 503
        assert response["code"] == "vision_provider_unconfigured"
        assert "KIMI_VISION_CLI_COMMAND" in response["detail"]
        assert "GEMINI_API_KEY" in response["detail"]

    def test_remote_vision_backend_counts_as_public_provider_and_proxies_image(self) -> None:
        os.environ["AEGIS_VISION_PUBLIC_ENABLED"] = "1"
        os.environ["VISION_BACKEND_URL"] = "https://vision.example"
        os.environ["VISION_BACKEND_API_KEY"] = "server-secret"
        captured: dict[str, object] = {}

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self) -> bytes:
                return (
                    '{"ok":true,"analysis":{"recognized_content":"税收楔子图"},'
                    '"suggestedPrompt":"用中文解释税收楔子。"}'
                ).encode("utf-8")

        def fake_urlopen(req, timeout=360):
            captured["url"] = req.full_url
            captured["body"] = req.data.decode("utf-8")
            captured["api_key"] = req.headers.get("X-api-key")
            return FakeResponse()

        original_urlopen = vision_analysis.urllib_request.urlopen
        vision_analysis.urllib_request.urlopen = fake_urlopen
        try:
            assert vision_analysis.is_vision_public_enabled() is True
            status, response = vision_analysis.analyze_image_payload(
                {"imageData": TINY_PNG_BASE64, "mimeType": "image/png", "prompt": "按考研风格讲"}
            )
        finally:
            vision_analysis.urllib_request.urlopen = original_urlopen

        assert status == 200
        assert response["ok"] is True
        assert response["suggestedPrompt"] == "用中文解释税收楔子。"
        assert captured["url"] == "https://vision.example/api/vision/analyze"
        assert captured["api_key"] == "server-secret"
        assert "server-secret" not in captured["body"]
        assert "按考研风格讲" in captured["body"]

    def test_cli_bridge_decodes_image_and_returns_chinese_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            script = Path(temp_dir) / "fake_vision_cli.py"
            script.write_text(
                textwrap.dedent(
                    """
                    import json
                    import sys
                    from pathlib import Path

                    image_path = Path(sys.argv[1])
                    prompt_path = Path(sys.argv[2])
                    assert image_path.read_bytes()
                    assert "图片理解" in prompt_path.read_text(encoding="utf-8")
                    print(json.dumps({
                        "image_type": "economics_chart",
                        "recognized_content": "一张供需图。",
                        "key_elements": ["需求曲线", "供给曲线"],
                        "uncertainties": [],
                        "visualization_plan": "先画供需曲线，再标出均衡点。",
                        "recommended_prompt": "请用中文动画解释供给需求均衡。",
                        "auditable_analysis": "测试 CLI 已读取图片。"
                    }, ensure_ascii=False))
                    """
                ),
                encoding="utf-8",
            )
            os.environ["KIMI_VISION_CLI_COMMAND"] = f"{sys.executable} {script} {{image_path}} {{prompt_path}}"

            status, response = vision_analysis.analyze_image_payload(
                {
                    "imageData": f"data:image/png;base64,{TINY_PNG_BASE64}",
                    "prompt": "按经济学考研风格讲解",
                }
            )

        assert status == 200
        assert response["ok"] is True
        assert response["suggestedPrompt"] == "请用中文动画解释供给需求均衡。"
        assert response["visionMeta"]["provider"] == "kimi-vision-cli"
        assert response["visionMeta"]["imageBytes"] == len(base64.b64decode(TINY_PNG_BASE64))

    def test_gemini_provider_uses_native_generate_content_api(self) -> None:
        os.environ["GEMINI_API_KEY"] = "gemini-secret"
        os.environ["GEMINI_VISION_MODEL"] = "gemini-flash-lite-latest"
        captured: dict[str, object] = {}

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self) -> bytes:
                return (
                    '{"candidates":[{"content":{"parts":[{"text":"{'
                    '\\"recognized_content\\":\\"税收楔子图\\",'
                    '\\"key_elements\\":[\\"Pb\\",\\"Ps\\"],'
                    '\\"uncertainties\\":[],'
                    '\\"visualization_plan\\":\\"画供需曲线\\",'
                    '\\"recommended_prompt\\":\\"用中文解释税收楔子\\"'
                    '}"}]}}]}'
                ).encode("utf-8")

        def fake_urlopen(req, timeout=45):
            captured["url"] = req.full_url
            captured["body"] = req.data.decode("utf-8")
            return FakeResponse()

        original_urlopen = vision_analysis.urllib_request.urlopen
        vision_analysis.urllib_request.urlopen = fake_urlopen
        try:
            status, response = vision_analysis.analyze_image_payload(
                {"imageData": TINY_PNG_BASE64, "mimeType": "image/png", "prompt": "考研图"}
            )
        finally:
            vision_analysis.urllib_request.urlopen = original_urlopen

        assert status == 200
        assert response["suggestedPrompt"] == "用中文解释税收楔子"
        assert response["visionMeta"]["provider"] == "gemini-vision"
        assert "models/gemini-flash-lite-latest:generateContent?key=gemini-secret" in captured["url"]
        assert "inline_data" in captured["body"]
        assert "考研图" in captured["body"]

    def test_gemini_provider_retries_transient_http_errors(self) -> None:
        os.environ["GEMINI_API_KEY"] = "gemini-secret"
        os.environ["GEMINI_VISION_RETRIES"] = "1"
        os.environ["GEMINI_VISION_RETRY_BACKOFF_SECONDS"] = "0"
        calls = {"count": 0}

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self) -> bytes:
                return (
                    '{"candidates":[{"content":{"parts":[{"text":"{'
                    '\\"recognized_content\\":\\"需求曲线和供给曲线\\",'
                    '\\"key_elements\\":[\\"D\\",\\"S\\"],'
                    '\\"uncertainties\\":[],'
                    '\\"visualization_plan\\":\\"画均衡点\\",'
                    '\\"recommended_prompt\\":\\"用中文解释供需均衡\\"'
                    '}"}]}}]}'
                ).encode("utf-8")

        def fake_urlopen(req, timeout=45):
            calls["count"] += 1
            if calls["count"] == 1:
                raise vision_analysis.urllib_error.HTTPError(
                    req.full_url,
                    429,
                    "Too Many Requests",
                    hdrs=None,
                    fp=io.BytesIO(b'{"error":{"message":"quota retry later"}}'),
                )
            return FakeResponse()

        original_urlopen = vision_analysis.urllib_request.urlopen
        original_sleep = vision_analysis.time.sleep
        vision_analysis.urllib_request.urlopen = fake_urlopen
        vision_analysis.time.sleep = lambda _: None
        try:
            status, response = vision_analysis.analyze_image_payload(
                {"imageData": TINY_PNG_BASE64, "mimeType": "image/png"}
            )
        finally:
            vision_analysis.urllib_request.urlopen = original_urlopen
            vision_analysis.time.sleep = original_sleep

        assert calls["count"] == 2
        assert status == 200
        assert response["suggestedPrompt"] == "用中文解释供需均衡"

    def test_generic_openai_compatible_provider_can_be_user_configured(self) -> None:
        os.environ["VISION_API_KEY"] = "vision-secret"
        os.environ["VISION_BASE_URL"] = "https://vision-router.example/v1"
        os.environ["VISION_MODEL"] = "cheap-vision-model"
        os.environ["VISION_PROVIDER_NAME"] = "cheap-router"
        captured: dict[str, object] = {}

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self) -> bytes:
                return (
                    '{"choices":[{"message":{"content":"{'
                    '\\"recognized_content\\":\\"IS-LM图\\",'
                    '\\"key_elements\\":[\\"IS\\",\\"LM\\"],'
                    '\\"uncertainties\\":[],'
                    '\\"visualization_plan\\":\\"画IS右移\\",'
                    '\\"recommended_prompt\\":\\"用中文解释财政扩张的IS-LM图\\"'
                    '}"}}]}'
                ).encode("utf-8")

        def fake_urlopen(req, timeout=45):
            captured["url"] = req.full_url
            captured["authorization"] = req.headers.get("Authorization")
            captured["body"] = req.data.decode("utf-8")
            return FakeResponse()

        original_urlopen = vision_analysis.urllib_request.urlopen
        vision_analysis.urllib_request.urlopen = fake_urlopen
        try:
            status, response = vision_analysis.analyze_image_payload(
                {"imageData": TINY_PNG_BASE64, "mimeType": "image/png"}
            )
        finally:
            vision_analysis.urllib_request.urlopen = original_urlopen

        assert status == 200
        assert captured["url"] == "https://vision-router.example/v1/chat/completions"
        assert captured["authorization"] == "Bearer vision-secret"
        assert '"model": "cheap-vision-model"' in captured["body"]
        assert response["visionMeta"]["provider"] == "cheap-router"
        assert response["suggestedPrompt"] == "用中文解释财政扩张的IS-LM图"

    def test_mimo_provider_uses_openai_compatible_endpoint_with_bearer_auth(self) -> None:
        os.environ["MIMO_API_KEY"] = "tp-test-mimo-key"
        os.environ["MIMO_VISION_BASE_URL"] = "https://token-plan-sgp.xiaomimimo.com/v1"
        os.environ["MIMO_VISION_MODEL"] = "mimo-v2.5-pro"
        captured: dict[str, object] = {}

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self) -> bytes:
                return (
                    '{"choices":[{"message":{"content":"{'
                    '\\"recognized_content\\":\\"税收楔子图\\",'
                    '\\"key_elements\\":[\\"Pb\\",\\"Ps\\"],'
                    '\\"uncertainties\\":[],'
                    '\\"visualization_plan\\":\\"画供需曲线\\",'
                    '\\"recommended_prompt\\":\\"用中文解释税收楔子\\"'
                    '}"}}]}'
                ).encode("utf-8")

        def fake_urlopen(req, timeout=45):
            captured["url"] = req.full_url
            captured["authorization"] = req.headers.get("Authorization")
            captured["body"] = req.data.decode("utf-8")
            return FakeResponse()

        original_urlopen = vision_analysis.urllib_request.urlopen
        vision_analysis.urllib_request.urlopen = fake_urlopen
        try:
            status, response = vision_analysis.analyze_image_payload(
                {"imageData": TINY_PNG_BASE64, "mimeType": "image/png"}
            )
        finally:
            vision_analysis.urllib_request.urlopen = original_urlopen

        assert status == 200
        assert captured["url"] == "https://token-plan-sgp.xiaomimimo.com/v1/chat/completions"
        assert captured["authorization"] == "Bearer tp-test-mimo-key"
        assert '"model": "mimo-v2.5-pro"' in captured["body"]
        assert response["visionMeta"]["provider"] == "mimo-vision"
        assert response["visionMeta"]["model"] == "mimo-v2.5-pro"
        assert response["suggestedPrompt"] == "用中文解释税收楔子"

    def test_mimo_provider_is_detected_as_configured(self) -> None:
        os.environ["MIMO_API_KEY"] = "tp-test-mimo-key"
        assert vision_analysis.is_vision_provider_configured() is True

    def test_ocr_command_provider_returns_text_only_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            script = Path(temp_dir) / "fake_ocr.py"
            script.write_text(
                textwrap.dedent(
                    """
                    import sys
                    from pathlib import Path

                    assert Path(sys.argv[1]).read_bytes()
                    print("题目：说明税收楔子如何导致无谓损失。\\n图中有需求曲线D和供给曲线S。")
                    """
                ),
                encoding="utf-8",
            )
            os.environ["VISION_OCR_COMMAND"] = f"{sys.executable} {script} {{image_path}}"

            status, response = vision_analysis.analyze_image_payload(
                {"imageData": TINY_PNG_BASE64, "mimeType": "image/png", "prompt": "做成中文动画"}
            )

        assert status == 200
        assert response["visionMeta"]["provider"] == "ocr-command"
        assert "OCR 识别文字" in response["suggestedPrompt"]
        assert "税收楔子" in response["suggestedPrompt"]

    def test_rejects_invalid_image_type(self) -> None:
        status, response = vision_analysis.analyze_image_payload(
            {"imageData": base64.b64encode(b"hello").decode("ascii"), "mimeType": "text/plain"}
        )

        assert status == 400
        assert response["code"] == "invalid_image"


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORE_DIR = PROJECT_ROOT / "core"
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

import web_app  # noqa: E402


class AegisWebUiTest(unittest.TestCase):
    def test_page_contains_safe_formula_preview_and_alignment_renderer(self) -> None:
        html = web_app.make_index_html()

        assert "https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js" in html
        assert 'id="promptPreview"' in html
        assert "function renderRichText" in html
        assert "renderRichText(script, segment.script" in html
        assert "script.textContent = segment.script" not in html
        assert "PROVIDER_CONFIG.providerStorageKey" in html

    def test_cloud_generate_mode_uses_direct_generate_flow(self) -> None:
        old_url = web_app.AEGIS_CLOUD_GENERATE_URL
        web_app.AEGIS_CLOUD_GENERATE_URL = "https://manim-main.vercel.app/api/generate"
        try:
            html = web_app.make_index_html()
            config = web_app.build_local_trial_config()
        finally:
            web_app.AEGIS_CLOUD_GENERATE_URL = old_url

        assert 'fetch("/api/generate"' in html
        assert 'fetch("/api/generate/start"' not in html
        assert 'applyGenerateResult(data, payload, data.requestId || "-");' in html
        assert "trial-kimi-priority" in config

    def test_cloud_generate_proxy_only_forwards_safe_public_fields(self) -> None:
        old_url = web_app.AEGIS_CLOUD_GENERATE_URL
        web_app.AEGIS_CLOUD_GENERATE_URL = "https://cloud.example/api/generate"
        captured: dict[str, object] = {}

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self) -> bytes:
                return b'{"ok":true,"sceneName":"GeneratedScene"}'

        def fake_urlopen(req, timeout=180):
            captured["url"] = req.full_url
            captured["body"] = req.data.decode("utf-8")
            return FakeResponse()

        original_urlopen = web_app.urllib_request.urlopen
        web_app.urllib_request.urlopen = fake_urlopen
        try:
            status, response = web_app.proxy_cloud_generate(
                {
                    "prompt": "解释帕累托最优",
                    "provider": "trial-kimi-priority",
                    "sceneName": "GeneratedScene",
                    "temperature": 0.2,
                    "apiKey": "must-not-forward",
                    "baseUrl": "https://must-not-forward.example",
                }
            )
        finally:
            web_app.urllib_request.urlopen = original_urlopen
            web_app.AEGIS_CLOUD_GENERATE_URL = old_url

        assert status == 200
        assert response["ok"] is True
        forwarded = captured["body"]
        assert "must-not-forward" not in forwarded
        assert "baseUrl" not in forwarded
        assert "apiKey" not in forwarded

    def test_teaching_brief_requires_chinese_visible_language(self) -> None:
        brief = web_app.build_teaching_brief("解释 $MP_L < 0$ 的经济含义")

        assert "默认使用中文标题" in brief
        assert "变量符号可以保留英文缩写" in brief
        assert "不使用 Tex/MathTex" in brief


if __name__ == "__main__":
    unittest.main()

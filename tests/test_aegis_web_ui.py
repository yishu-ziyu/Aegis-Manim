from __future__ import annotations

import os
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
        assert "aegis.byok.vault.v1" in html
        assert 'id="byokPanel"' in html
        assert 'id="modeByokBtn"' in html
        assert "saveCurrentKey" in html
        assert "密钥只存在这台浏览器" in html
        assert "[hidden] { display: none !important; }" in html
        assert 'id="resultEmpty"' in html
        assert "currentByokKey" in html
        assert "先在密钥库填写 API Key" in html
        assert "选择或拖入图片" in html
        assert 'id="endpointDetails"' in html
        assert 'id="vaultList"' in html
        assert "renderVaultList" in html
        assert "forgetAllKeys" in html
        assert "keyLooksUsable" in html
        assert "清空密钥库" in html
        assert "这个 Key 看起来不像可用密钥" in html

    def test_page_contains_image_understanding_confirmation_flow(self) -> None:
        old_enabled = os.environ.get("AEGIS_VISION_PUBLIC_ENABLED")
        old_command = os.environ.get("KIMI_VISION_CLI_COMMAND")
        os.environ["AEGIS_VISION_PUBLIC_ENABLED"] = "1"
        os.environ["KIMI_VISION_CLI_COMMAND"] = "python3 fake.py {image_path} {prompt_path}"
        try:
            html = web_app.make_index_html()
        finally:
            if old_enabled is None:
                os.environ.pop("AEGIS_VISION_PUBLIC_ENABLED", None)
            else:
                os.environ["AEGIS_VISION_PUBLIC_ENABLED"] = old_enabled
            if old_command is None:
                os.environ.pop("KIMI_VISION_CLI_COMMAND", None)
            else:
                os.environ["KIMI_VISION_CLI_COMMAND"] = old_command

        assert 'id="visionImageInput"' in html
        assert 'id="visionDropZone"' in html
        assert 'id="visionConfirmCard"' in html
        assert 'id="visionUseBtn"' in html
        assert 'fetch("/api/vision/analyze"' in html
        assert "是否按这个方向可视化" in html
        assert "document.addEventListener(\"paste\"" in html
        assert "dragover" in html

    def test_image_understanding_entry_is_hidden_until_publicly_enabled(self) -> None:
        old_enabled = os.environ.get("AEGIS_VISION_PUBLIC_ENABLED")
        old_command = os.environ.get("KIMI_VISION_CLI_COMMAND")
        os.environ.pop("AEGIS_VISION_PUBLIC_ENABLED", None)
        os.environ["KIMI_VISION_CLI_COMMAND"] = "python3 fake.py {image_path} {prompt_path}"
        try:
            html = web_app.make_index_html()
        finally:
            if old_enabled is None:
                os.environ.pop("AEGIS_VISION_PUBLIC_ENABLED", None)
            else:
                os.environ["AEGIS_VISION_PUBLIC_ENABLED"] = old_enabled
            if old_command is None:
                os.environ.pop("KIMI_VISION_CLI_COMMAND", None)
            else:
                os.environ["KIMI_VISION_CLI_COMMAND"] = old_command

        assert '<div class="field" hidden>' in html
        assert 'id="visionImageInput"' in html

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
        assert "trial-minimax-direct" in config
        assert "trial-kimi-priority" not in config

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
                    "provider": "trial-minimax-direct",
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

    def test_cloud_generate_proxy_forwards_byok_key_for_user_providers(self) -> None:
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
                return b'{"ok":true,"authMode":"byok"}'

        def fake_urlopen(req, timeout=180):
            captured["body"] = req.data.decode("utf-8")
            return FakeResponse()

        original_urlopen = web_app.urllib_request.urlopen
        web_app.urllib_request.urlopen = fake_urlopen
        try:
            status, response = web_app.proxy_cloud_generate(
                {
                    "prompt": "解释帕累托最优",
                    "provider": "openai",
                    "sceneName": "GeneratedScene",
                    "temperature": 0.2,
                    "apiKey": "sk-user-owned",
                    "baseUrl": "https://api.openai.com/v1",
                    "model": "gpt-4o-mini",
                }
            )
        finally:
            web_app.urllib_request.urlopen = original_urlopen
            web_app.AEGIS_CLOUD_GENERATE_URL = old_url

        assert status == 200
        assert response["ok"] is True
        forwarded = captured["body"]
        assert "sk-user-owned" in forwarded
        assert "https://api.openai.com/v1" in forwarded
        assert "gpt-4o-mini" in forwarded

    def test_local_web_server_exposes_render_proxy_routes(self) -> None:
        assert "if route == \"/api/render\":" in Path(web_app.__file__).read_text(encoding="utf-8")
        assert "if route == \"/api/vision/analyze\":" in Path(web_app.__file__).read_text(encoding="utf-8")
        html = web_app.make_index_html()

        assert "const RENDER_BACKEND_API_KEY" not in html
        assert '"X-API-Key": RENDER_BACKEND_API_KEY' not in html
        assert '"/api/render/status/' in html
        assert "/api/render/download/${jobId}" in html
        assert "retryCount < 1" in html
        assert "渲染实例刚重启，正在自动重提一次" in html

    def test_web_ui_searches_community_before_generating_and_can_submit_repository_review(self) -> None:
        html = web_app.make_index_html()

        assert 'fetch("/api/community/search?' in html
        assert "applyCommunityWork" in html
        assert "已复用社区高分或精选作品" in html
        assert 'fetch(`/api/community/works/${communityWorkId}/reuse`' in html
        assert 'fetch(`/api/community/works/${communityWorkId}/rating`' in html
        assert 'id="communityHub"' in html
        assert "作品仓库" in html
        assert 'id="communitySearchInput"' in html
        assert 'id="communitySearchBtn"' in html
        assert 'id="communitySearchList"' in html
        assert "renderCommunitySearchResults" in html
        assert "searchCommunityRepository" in html
        assert "复用这个动画" in html
        assert 'id="communityActions"' in html
        assert "提交入库审阅" in html
        assert "已提交到候选仓库，审阅通过后进入社区复用库。" in html
        assert 'id="reviewPanel"' in html
        assert "管理员审阅队列" in html
        assert "候选仓库审阅" in html
        assert "通过公开" in html
        assert "设为精选" in html
        assert "退回观察" in html
        assert 'fetch(`/api/community/review/queue?' in html
        assert 'fetch(`/api/community/works/${workId}/review`' in html
        assert "aegis.community.reviewToken" in html
        assert 'data-rating="5"' in html
        assert 'data-rating="1"' in html

    def test_local_render_proxy_accepts_snake_case_scene_name_and_detects_code_class(self) -> None:
        render_payload, error_payload = web_app.build_render_backend_submit_payload(
            {
                "code": (
                    "from manim import *\n"
                    "class ParetoOptimalScene(Scene):\n"
                    "    def construct(self):\n"
                    "        self.play(Write(Text('帕累托最优')))\n"
                ),
                "scene_name": "GeneratedScene",
                "render_mode": "auto",
            }
        )

        assert error_payload is None
        assert render_payload is not None
        assert render_payload["scene_name"] == "ParetoOptimalScene"
        assert render_payload["render_mode"] == "auto"

    def test_windows_local_launcher_uses_cloud_generation_and_local_rendering(self) -> None:
        launcher = PROJECT_ROOT / "scripts" / "start_aegis_local_windows.bat"
        content = launcher.read_text(encoding="utf-8")

        assert "AEGIS_CLOUD_GENERATE_URL=https://manim-main.vercel.app/api/generate" in content
        assert "RENDER_BACKEND_URL=http://127.0.0.1:%RENDER_PORT%" in content
        assert "render_backend\\requirements.txt" in content
        assert "winget install Gyan.FFmpeg" in content
        assert "Get-NetTCPConnection -LocalPort %RENDER_PORT%" in content
        assert "SUPABASE" not in content
        assert "SERVICE_KEY" not in content

    def test_teaching_brief_requires_chinese_visible_language(self) -> None:
        brief = web_app.build_teaching_brief("解释 $MP_L < 0$ 的经济含义")

        assert "默认使用中文标题" in brief
        assert "变量符号可以保留英文缩写" in brief
        assert "不使用 Tex/MathTex" in brief
        assert "每个镜头只引入一个新经济对象" in brief
        assert "认知锚点" in brief
        assert "辅助标注长期堆在主图上" in brief
        assert "半透明或小图例复现" in brief
        assert "先呈现基准状态" in brief
        assert "45-120 秒中等复杂度视频" in brief
        assert "8-20 个 self.play" in brief


if __name__ == "__main__":
    unittest.main()

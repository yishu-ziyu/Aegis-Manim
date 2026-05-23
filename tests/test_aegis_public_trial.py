from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path
from urllib.error import URLError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api import index as gateway  # noqa: E402

APP_SPEC = importlib.util.spec_from_file_location("aegis_vercel_asgi_app", PROJECT_ROOT / "app.py")
assert APP_SPEC and APP_SPEC.loader
vercel_asgi = importlib.util.module_from_spec(APP_SPEC)
APP_SPEC.loader.exec_module(vercel_asgi)


class FakeUrlopenResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body
        self.headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


async def call_asgi_app(
    method: str,
    path: str,
    *,
    body: bytes = b"",
    query_string: bytes = b"",
) -> tuple[int, dict[str, object]]:
    messages = [{"type": "http.request", "body": body, "more_body": False}]
    events: list[dict[str, object]] = []

    async def receive() -> dict[str, object]:
        if messages:
            return messages.pop(0)
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, object]) -> None:
        events.append(message)

    await vercel_asgi.app(
        {"type": "http", "method": method, "path": path, "query_string": query_string},
        receive,
        send,
    )

    status = next(event["status"] for event in events if event["type"] == "http.response.start")
    response_body = b"".join(
        event.get("body", b"") for event in events if event["type"] == "http.response.body"
    )
    return int(status), json.loads(response_body.decode("utf-8")) if response_body else {}


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

        assert config["defaultProvider"] == "trial-minimax-direct"
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

    def test_trial_response_uses_detected_scene_name(self) -> None:
        def fake_generate_code_with_llm(**kwargs: object) -> tuple[str, object, str]:
            provider = gateway.resolve_provider(str(kwargs["provider_id"]))
            return (
                "from manim import *\nclass ParetoOptimalityScene(Scene):\n    pass\n",
                provider,
                "hidden",
            )

        original = gateway.generate_code_with_llm
        os.environ["KIMI_CODE_API_KEY"] = "server-kimi-key"
        gateway.generate_code_with_llm = fake_generate_code_with_llm
        try:
            status, response = gateway.generate_manim_code_for_gateway(
                {
                    "prompt": "将帕累托最优的过程可视化。",
                    "provider": "trial-kimi-priority",
                    "sceneName": "GeneratedScene",
                }
            )
        finally:
            gateway.generate_code_with_llm = original

        assert status == 200
        assert response["sceneName"] == "ParetoOptimalityScene"
        assert response["sceneNameInput"] == "GeneratedScene"

    def test_trial_regenerates_when_generated_code_exceeds_hosted_render_budget(self) -> None:
        calls: list[str] = []

        def fake_generate_code_with_llm(**kwargs: object) -> tuple[str, object, str]:
            calls.append(str(kwargs["user_prompt"]))
            provider = gateway.resolve_provider(str(kwargs["provider_id"]))
            if len(calls) == 1:
                heavy = "\n".join("        self.play(Write(Text('x', font_size=24)))" for _ in range(30))
                return (
                    "from manim import *\nclass GeneratedScene(Scene):\n    def construct(self):\n"
                    + heavy
                    + "\n",
                    provider,
                    "hidden",
                )
            return (
                "from manim import *\nclass GeneratedScene(Scene):\n    def construct(self):\n"
                "        self.play(Write(Text('短例子', font_size=24)))\n",
                provider,
                "hidden",
            )

        original = gateway.generate_code_with_llm
        os.environ["KIMI_CODE_API_KEY"] = "server-kimi-key"
        gateway.generate_code_with_llm = fake_generate_code_with_llm
        try:
            status, response = gateway.generate_manim_code_for_gateway(
                {
                    "prompt": "将帕累托最优的过程可视化。",
                    "provider": "trial-kimi-priority",
                    "sceneName": "GeneratedScene",
                }
            )
        finally:
            gateway.generate_code_with_llm = original

        assert status == 200
        assert response["ok"] is True
        assert len(calls) == 2
        assert "Hosted render budget correction" in calls[1]
        assert "at most 14 self.play" in calls[1]
        assert str(response["code"]).count("self.play(") == 1

    def test_trial_uses_stable_template_when_repair_still_exceeds_budget(self) -> None:
        def fake_generate_code_with_llm(**kwargs: object) -> tuple[str, object, str]:
            provider = gateway.resolve_provider(str(kwargs["provider_id"]))
            heavy = "\n".join("        self.play(Write(Text('x', font_size=24)))" for _ in range(30))
            return (
                "from manim import *\nclass GeneratedScene(Scene):\n    def construct(self):\n"
                + heavy
                + "\n",
                provider,
                "hidden",
            )

        original = gateway.generate_code_with_llm
        os.environ["MINIMAX_API_KEY"] = "server-minimax-key"
        gateway.generate_code_with_llm = fake_generate_code_with_llm
        try:
            status, response = gateway.generate_manim_code_for_gateway(
                {
                    "prompt": "可视化帕累托最优过程。",
                    "provider": "trial-minimax-direct",
                    "sceneName": "GeneratedScene",
                }
            )
        finally:
            gateway.generate_code_with_llm = original

        assert status == 200
        assert response["model"] == "stable-template-fallback"
        assert "不能让一人更好" in str(response["code"])

    def test_trial_returns_stable_template_when_server_models_are_unavailable(self) -> None:
        def fake_generate_code_with_llm(**kwargs: object) -> tuple[str, object, str]:
            raise TimeoutError("provider timed out")

        original = gateway.generate_code_with_llm
        os.environ["MINIMAX_API_KEY"] = "server-minimax-key"
        gateway.generate_code_with_llm = fake_generate_code_with_llm
        try:
            status, response = gateway.generate_manim_code_for_gateway(
                {
                    "prompt": "解释线性增长为什么会累积差距",
                    "sceneName": "GeneratedScene",
                }
            )
        finally:
            gateway.generate_code_with_llm = original

        assert status == 200
        assert response["ok"] is True
        assert response["model"] == "stable-template-fallback"
        assert response["endpoint"] == "server-managed-fallback"
        assert "class GeneratedScene(Scene)" in str(response["code"])
        assert "_AEGIS_CJK_FONT" in str(response["code"])
        assert "稳定模板" in "\n".join(response["warnings"])

    def test_pareto_fallback_uses_topic_specific_teaching_scene(self) -> None:
        code = gateway.build_fallback_manim_code("可视化帕累托最优过程。", "GeneratedScene")
        patched, notes = gateway.apply_runtime_compatibility_fixes(code)

        assert "不能让一人更好" in patched
        assert "Axes(" in patched
        assert "frontier" in patched
        assert patched.count("self.play(") >= 6
        assert "_AEGIS_CJK_FONT" in patched
        assert any("CJK-capable" in note for note in notes)

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

    def test_public_html_contains_render_poll_and_playback_flow(self) -> None:
        html = gateway.build_index_html()

        assert 'fetch("/api/render"' in html
        assert "/api/render/status/" in html
        assert "/api/render/download/" in html
        assert "video_url" in html
        assert 'dlResp.headers.get("content-type")' in html
        assert "if (!statusResp.ok)" in html
        assert "渲染失败" in html

    def test_render_proxy_accepts_snake_case_scene_name_and_detects_code_class(self) -> None:
        render_payload, error_payload = gateway.build_render_backend_submit_payload(
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

    def test_community_search_proxy_forwards_query_to_render_backend(self) -> None:
        calls: list[tuple[str, str, dict[str, object] | None]] = []

        def fake_proxy(path, method="GET", payload=None, timeout=15):
            calls.append((path, method, payload))
            return 200, {"ok": True, "hit": False, "items": []}

        original = gateway._proxy_to_render_backend
        gateway._proxy_to_render_backend = fake_proxy
        try:
            status, response = gateway.proxy_community_request(
                "/api/community/search",
                query="q=%E5%B8%95%E7%B4%AF%E6%89%98&limit=1",
            )
        finally:
            gateway._proxy_to_render_backend = original

        assert status == 200
        assert response["ok"] is True
        assert calls == [("/community/search?q=%E5%B8%95%E7%B4%AF%E6%89%98&limit=1", "GET", None)]

    def test_community_write_proxy_forwards_safe_payload_to_render_backend(self) -> None:
        calls: list[tuple[str, str, dict[str, object] | None]] = []

        def fake_proxy(path, method="GET", payload=None, timeout=15):
            calls.append((path, method, payload))
            return 200, {"ok": True, "work": {"workId": "work-1"}}

        original = gateway._proxy_to_render_backend
        gateway._proxy_to_render_backend = fake_proxy
        try:
            status, response = gateway.proxy_community_request(
                "/api/community/works/work-1/rating",
                method="POST",
                payload={"rating": 5, "raterKey": "anon-1"},
            )
        finally:
            gateway._proxy_to_render_backend = original

        assert status == 200
        assert response["ok"] is True
        assert calls == [
            ("/community/works/work-1/rating", "POST", {"rating": 5, "raterKey": "anon-1"})
        ]

    def test_vercel_asgi_forwards_community_search_query(self) -> None:
        calls: list[tuple[str, str, str, dict[str, object] | None]] = []

        def fake_community_proxy(route, query="", method="GET", payload=None):
            calls.append((route, query, method, payload))
            return 200, {"ok": True, "hit": True, "items": [{"workId": "work-1"}]}

        original = vercel_asgi.proxy_community_request
        vercel_asgi.proxy_community_request = fake_community_proxy
        try:
            status, response = asyncio.run(
                call_asgi_app(
                    "GET",
                    "/api/community/search",
                    query_string=b"q=%E5%B8%95%E7%B4%AF%E6%89%98&limit=1",
                )
            )
        finally:
            vercel_asgi.proxy_community_request = original

        assert status == 200
        assert response["hit"] is True
        assert calls == [
            ("/api/community/search", "q=%E5%B8%95%E7%B4%AF%E6%89%98&limit=1", "GET", None)
        ]

    def test_vercel_asgi_forwards_community_write_payload(self) -> None:
        calls: list[tuple[str, str, dict[str, object] | None]] = []

        def fake_community_proxy(route, query="", method="GET", payload=None):
            calls.append((route, method, payload))
            return 200, {"ok": True, "reuseCount": 2}

        original = vercel_asgi.proxy_community_request
        vercel_asgi.proxy_community_request = fake_community_proxy
        try:
            status, response = asyncio.run(
                call_asgi_app(
                    "POST",
                    "/api/community/works/work-1/reuse",
                    body=b'{"userKey":"anon-1"}',
                )
            )
        finally:
            vercel_asgi.proxy_community_request = original

        assert status == 200
        assert response["ok"] is True
        assert calls == [("/api/community/works/work-1/reuse", "POST", {"userKey": "anon-1"})]

    def test_download_proxy_extracts_safe_video_redirect_url(self) -> None:
        url = "https://example.supabase.co/storage/v1/object/public/manim-videos/job/video.mp4"

        assert gateway._extract_download_video_url({"video_url": url}) == url
        assert gateway._extract_download_video_url({"video_url": "javascript:alert(1)"}) is None
        assert gateway._extract_download_video_url({"video_url": "/relative/video.mp4"}) is None

    def test_render_proxy_retries_after_cold_start_connection_error(self) -> None:
        old_url = gateway.RENDER_BACKEND_URL
        gateway.RENDER_BACKEND_URL = "https://render.example"
        calls: list[str] = []

        def fake_urlopen(req, timeout=15):
            calls.append(req.full_url)
            if len(calls) == 1:
                raise URLError("cold")
            return FakeUrlopenResponse(202, b'{"job_id":"job-1","status":"pending"}')

        original_urlopen = gateway.urllib_request.urlopen
        original_sleep = gateway.time.sleep
        gateway.urllib_request.urlopen = fake_urlopen
        gateway.time.sleep = lambda *_: None
        try:
            status, response = gateway._proxy_to_render_backend(
                "/render-async",
                method="POST",
                payload={"code": "from manim import *", "scene_name": "GeneratedScene"},
            )
        finally:
            gateway.urllib_request.urlopen = original_urlopen
            gateway.time.sleep = original_sleep
            gateway.RENDER_BACKEND_URL = old_url

        assert status == 202
        assert response["job_id"] == "job-1"
        assert calls == [
            "https://render.example/render-async",
            "https://render.example/health",
            "https://render.example/render-async",
        ]

    def test_render_proxy_returns_friendly_error_when_cold_start_retry_fails(self) -> None:
        old_url = gateway.RENDER_BACKEND_URL
        gateway.RENDER_BACKEND_URL = "https://render.example"

        def fail_urlopen(*args, **kwargs):
            raise URLError("still cold")

        original_urlopen = gateway.urllib_request.urlopen
        original_sleep = gateway.time.sleep
        gateway.urllib_request.urlopen = fail_urlopen
        gateway.time.sleep = lambda *_: None
        try:
            status, response = gateway._proxy_to_render_backend("/status/job-1")
        finally:
            gateway.urllib_request.urlopen = original_urlopen
            gateway.time.sleep = original_sleep
            gateway.RENDER_BACKEND_URL = old_url

        assert status == 502
        assert response["ok"] is False
        assert "冷启动" in response["error"]


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import io
import unittest
from unittest import mock
from pathlib import Path

from scripts import production_vision_economics_acceptance as acceptance


class ProductionVisionEconomicsAcceptanceTest(unittest.TestCase):
    def test_vision_payload_is_usable_for_chinese_economics_prompt(self) -> None:
        usable, reason = acceptance.vision_payload_is_usable(
            {
                "ok": True,
                "recognizedContent": "图片是一道关于需求曲线、供给曲线和均衡价格的题。",
                "keyElements": ["需求曲线", "供给曲线"],
                "uncertainties": [],
                "visualizationPlan": "画出供需曲线并标出均衡数量。",
                "suggestedPrompt": "请用中文动画解释供给需求均衡。",
            }
        )

        assert usable is True
        assert reason == ""

    def test_vision_payload_rejects_empty_suggested_prompt(self) -> None:
        usable, reason = acceptance.vision_payload_is_usable(
            {
                "ok": True,
                "recognizedContent": "图片是一道关于需求曲线的题。",
                "suggestedPrompt": "",
            }
        )

        assert usable is False
        assert reason == "suggestedPrompt is empty"

    def test_vision_payload_accepts_nested_analysis_shape(self) -> None:
        payload = {
            "ok": True,
            "analysis": {
                "recognized_content": "图片是一道关于垄断厂商 MR、MC、价格和数量选择的考研题。",
                "key_elements": ["边际收益曲线", "边际成本曲线", "垄断价格"],
                "visualization_plan": "先画需求曲线和 MR 曲线，再标出 MR=MC 的产量。",
                "recommended_prompt": "请用中文 Manim 动画解释垄断定价与无谓损失。",
            },
        }

        usable, reason = acceptance.vision_payload_is_usable(payload)

        assert usable is True
        assert reason == ""
        assert acceptance.extract_suggested_prompt(payload) == "请用中文 Manim 动画解释垄断定价与无谓损失。"

    def test_infer_mime_supports_public_image_formats(self) -> None:
        assert acceptance.infer_mime(Path("question.png")) == "image/png"
        assert acceptance.infer_mime(Path("question.jpg")) == "image/jpeg"
        assert acceptance.infer_mime(Path("question.jpeg")) == "image/jpeg"
        assert acceptance.infer_mime(Path("question.webp")) == "image/webp"

    def test_post_json_sends_optional_vision_api_key_header(self) -> None:
        class FakeResponse:
            status = 200

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self) -> bytes:
                return b'{"ok": true}'

        with mock.patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
            status, payload = acceptance.post_json(
                "https://example.test/api/vision/analyze",
                {"ok": True},
                timeout=10,
                api_key="secret-key",
            )

        request = urlopen.call_args.args[0]
        assert status == 200
        assert payload == {"ok": True}
        assert request.get_header("X-api-key") == "secret-key"

    def test_post_json_retries_transient_http_error_and_preserves_detail(self) -> None:
        class FakeResponse:
            status = 200

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self) -> bytes:
                return b'{"ok": true}'

        attempts = {"count": 0}

        def fake_urlopen(req, timeout=10):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise acceptance.error.HTTPError(
                    req.full_url,
                    502,
                    "Bad Gateway",
                    hdrs=None,
                    fp=io.BytesIO(b'{"error":"upstream model timeout"}'),
                )
            return FakeResponse()

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen), mock.patch("time.sleep"):
            status, payload = acceptance.post_json(
                "https://example.test/api/vision/analyze",
                {"ok": True},
                timeout=10,
                retries=1,
                retry_backoff=0,
            )

        assert attempts["count"] == 2
        assert status == 200
        assert payload == {"ok": True}

    def test_post_json_exposes_response_body_after_final_http_error(self) -> None:
        with mock.patch(
            "urllib.request.urlopen",
            side_effect=acceptance.error.HTTPError(
                "https://example.test/api/vision/analyze",
                429,
                "Too Many Requests",
                hdrs=None,
                fp=io.BytesIO(b'{"error":"quota exceeded"}'),
            ),
        ), mock.patch("time.sleep"):
            with self.assertRaises(acceptance.error.HTTPError) as raised:
                acceptance.post_json(
                    "https://example.test/api/vision/analyze",
                    {"ok": True},
                    timeout=10,
                    retries=0,
                )

        assert "quota exceeded" in raised.exception.aegis_detail


if __name__ == "__main__":
    unittest.main()

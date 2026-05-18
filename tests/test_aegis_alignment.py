from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORE_DIR = PROJECT_ROOT / "core"
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

import alignment  # noqa: E402


class AegisAlignmentTest(unittest.TestCase):
    def test_extract_alignment_signals_orders_play_and_wait_calls(self) -> None:
        code = """
from manim import *

class GeneratedScene(Scene):
    def construct(self):
        self.play(Create(Circle()), run_time=2)
        self.wait(0.5)
        self.play(FadeOut(Circle()))
"""
        signals = alignment.extract_alignment_signals(
            code=code,
            scene_name="GeneratedScene",
            video_duration=None,
        )

        assert signals["sceneName"] == "GeneratedScene"
        assert [event["kind"] for event in signals["events"]] == ["play", "wait", "play"]
        assert signals["events"][0]["startTime"] == 0
        assert signals["events"][0]["endTime"] == 2
        assert signals["events"][1]["startTime"] == 2
        assert signals["events"][1]["endTime"] == 2.5
        assert signals["events"][2]["startTime"] == 2.5
        assert signals["events"][2]["endTime"] == 3.5

    def test_extract_alignment_signals_scales_to_known_video_duration(self) -> None:
        code = """
from manim import *

class GeneratedScene(Scene):
    def construct(self):
        self.play(Create(Square()), run_time=2)
        self.wait(2)
"""
        signals = alignment.extract_alignment_signals(
            code=code,
            scene_name="GeneratedScene",
            video_duration=10,
        )

        assert signals["duration"] == 10
        assert signals["events"][0]["endTime"] == 5
        assert signals["events"][1]["startTime"] == 5
        assert signals["events"][1]["endTime"] == 10
        assert any("Scaled" in warning for warning in signals["warnings"])

    def test_validate_alignment_marks_estimated_timing_as_not_high_confidence(self) -> None:
        raw = {
            "mode": "posthoc_metadata",
            "confidence": "high",
            "warnings": ["Timing estimated from metadata."],
            "segments": [
                {
                    "id": "seg_1",
                    "title": "建立直觉",
                    "script": "解释画面中的初始关系。",
                    "visualIntent": "展示初始对象。",
                    "startTime": 0,
                    "endTime": 10,
                    "confidence": "high",
                }
            ],
        }

        normalized = alignment.validate_alignment(raw, video_duration=12, timing_is_estimated=True)

        assert normalized["confidence"] == "medium"
        assert normalized["segments"][0]["confidence"] == "medium"
        assert any("estimated" in warning.lower() for warning in normalized["warnings"])

    def test_build_fallback_alignment_is_visible_low_confidence(self) -> None:
        signals = {"duration": 20, "events": [], "warnings": ["No play/wait calls found."]}

        fallback = alignment.build_fallback_alignment(
            prompt="解释税收楔子如何导致无谓损失",
            scene_name="GeneratedScene",
            signals=signals,
        )

        assert fallback["confidence"] == "low"
        assert fallback["segments"][0]["startTime"] == 0
        assert fallback["segments"][0]["endTime"] == 20
        assert fallback["warnings"]

    def test_parse_alignment_json_extracts_fenced_json(self) -> None:
        text = '''```json
{"mode":"posthoc_metadata","confidence":"medium","warnings":[],"segments":[{"id":"seg_1","title":"直觉","script":"解释直觉。","visualIntent":"显示对象。","startTime":0,"endTime":5,"confidence":"medium"}]}
```'''

        parsed = alignment.parse_alignment_json(text)

        assert parsed["segments"][0]["title"] == "直觉"

    def test_generate_alignment_uses_injected_llm_and_validates_output(self) -> None:
        code = """
from manim import *

class GeneratedScene(Scene):
    def construct(self):
        self.play(Create(Circle()), run_time=2)
"""

        def fake_llm(_system_prompt: str, _user_prompt: str) -> str:
            return """
{
  "mode": "posthoc_metadata",
  "confidence": "high",
  "warnings": [],
  "segments": [
    {
      "id": "seg_1",
      "title": "圆形出现",
      "script": "这一段解释圆形如何把抽象对象具体化。",
      "visualIntent": "创建一个圆形。",
      "startTime": 0,
      "endTime": 2,
      "confidence": "high"
    }
  ]
}
"""

        result = alignment.generate_alignment(
            prompt="解释圆形如何代表集合边界",
            code=code,
            scene_name="GeneratedScene",
            video_duration=2,
            llm_call=fake_llm,
        )

        assert result["confidence"] == "high"
        assert result["segments"][0]["title"] == "圆形出现"


if __name__ == "__main__":
    unittest.main()

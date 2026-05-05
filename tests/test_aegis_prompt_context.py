from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORE_DIR = PROJECT_ROOT / "core"
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

import manim_agent  # noqa: E402


class AegisPromptContextTest(unittest.TestCase):
    def test_load_system_prompt_appends_manim_knowledge_pack(self) -> None:
        prompt = manim_agent.load_system_prompt()

        assert "# Role" in prompt
        assert "# Manim Knowledge Pack" in prompt
        assert "Manim Community Edition 0.19.2" in prompt
        assert "ValueTracker" in prompt
        assert "axes.c2p" in prompt
        assert "Text Lifecycle" in prompt
        assert "ReplacementTransform(old_text, new_text)" in prompt
        assert "FadeOut(section_group)" in prompt

    def test_load_system_prompt_tolerates_missing_knowledge_pack(self) -> None:
        with patch.object(manim_agent, "MANIM_KNOWLEDGE_PATH", PROJECT_ROOT / "prompts" / "missing.md"):
            prompt = manim_agent.load_system_prompt()

        assert "# Role" in prompt
        assert "# Manim Knowledge Pack" not in prompt
        assert "Text Lifecycle" in prompt


if __name__ == "__main__":
    unittest.main()

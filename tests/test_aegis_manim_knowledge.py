from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORE_DIR = PROJECT_ROOT / "core"
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

import manim_knowledge  # noqa: E402


class AegisManimKnowledgeTest(unittest.TestCase):
    def test_precheck_flags_missing_scene_structure(self) -> None:
        issues = manim_knowledge.precheck_manim_code("print('hello')", "GeneratedScene")

        categories = {issue.category for issue in issues}
        assert "scene-structure" in categories
        assert any(issue.severity == "error" for issue in issues)

    def test_precheck_flags_latex_and_unsupported_axes_api(self) -> None:
        code = """
from manim import *

class GeneratedScene(Scene):
    def construct(self):
        axes = Axes()
        label = MathTex("x")
        line = axes.get_h_line(axes.c2p(1, 2))
"""

        issues = manim_knowledge.precheck_manim_code(code, "GeneratedScene")

        categories = {issue.category for issue in issues}
        assert "latex" in categories
        assert "axes-api" in categories
        assert any(issue.category == "latex" and issue.severity == "error" for issue in issues)

    def test_precheck_flags_repeated_text_without_cleanup(self) -> None:
        code = """
from manim import *

class GeneratedScene(Scene):
    def construct(self):
        self.play(Write(Text("第一段很长的解释")))
        self.wait(1)
        self.play(Write(Text("第二段继续写在同一片画面上")))
"""

        issues = manim_knowledge.precheck_manim_code(code, "GeneratedScene")

        assert any(issue.category == "layout-fit" and issue.severity == "error" for issue in issues)

    def test_precheck_flags_text_without_explicit_font_size(self) -> None:
        code = """
from manim import *

class GeneratedScene(Scene):
    def construct(self):
        title = Text("市场均衡")
        self.play(Write(title))
"""

        issues = manim_knowledge.precheck_manim_code(code, "GeneratedScene")

        assert any(issue.category == "layout-fit" and "font_size" in issue.technical_message for issue in issues)

    def test_classifies_latex_render_failures_with_recipe(self) -> None:
        classification = manim_knowledge.classify_render_error("LaTeX Error: File `standalone.cls' not found")

        assert classification.category == "latex"
        assert "Text" in classification.repair_prompt
        assert classification.recipe_ids == ("latex-to-text",)

    def test_build_repair_feedback_includes_precheck_and_error_category(self) -> None:
        issues = [
            manim_knowledge.PrecheckIssue(
                category="axes-api",
                severity="warn",
                student_message="student",
                technical_message="line_config is unsupported",
                repair_hint="Use stroke_width directly.",
                source_ids=("local-bug-log",),
            )
        ]
        classification = manim_knowledge.classify_render_error("NameError: name 'curve' is not defined")

        feedback = manim_knowledge.build_repair_feedback(
            original_prompt="Explain tax wedge.",
            render_error="NameError: name 'curve' is not defined",
            classification=classification,
            precheck_issues=issues,
            attempt=2,
        )

        assert "Error category: undefined-symbol" in feedback
        assert "line_config is unsupported" in feedback
        assert "Explain tax wedge" in feedback


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import unittest
from http import HTTPStatus
from pathlib import Path
from unittest.mock import Mock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORE_DIR = PROJECT_ROOT / "core"
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

import manim_agent  # noqa: E402
import web_app  # noqa: E402


class AegisRuntimeCompatibilityTest(unittest.TestCase):
    def test_axes_short_line_aliases_are_rewritten_for_current_manim_api(self) -> None:
        code = """
from manim import *

class GeneratedScene(Scene):
    def construct(self):
        axes = Axes()
        h = axes.get_h_line(axes.coords_to_point(3.5, 4.5))
        v = axes.get_v_line(axes.coords_to_point(3.5, 4.5), color=YELLOW)
"""

        patched, notes = manim_agent.apply_runtime_compatibility_fixes(code)

        assert "axes.get_horizontal_line(axes.coords_to_point(3.5, 4.5))" in patched
        assert "axes.get_vertical_line(axes.coords_to_point(3.5, 4.5), color=YELLOW)" in patched
        assert "get_h_line" not in patched
        assert "get_v_line" not in patched
        assert any("Axes get_h_line/get_v_line" in note for note in notes)

    def test_axes_short_line_aliases_are_rewritten_even_when_latex_exists(self) -> None:
        code = "axes.get_h_line(axes.coords_to_point(1, 2))"

        with patch.object(manim_agent, "LATEX_AVAILABLE", True):
            patched, _notes = manim_agent.apply_runtime_compatibility_fixes(code)

        assert patched == "axes.get_horizontal_line(axes.coords_to_point(1, 2))"

    def test_tex_is_rewritten_even_when_latex_exists(self) -> None:
        code = 'title = Tex("Short-run Production Function")\nlabel = MathTex("MP_L")'

        with patch.object(manim_agent, "LATEX_AVAILABLE", True):
            patched, notes = manim_agent.apply_runtime_compatibility_fixes(code)

        assert "Tex(" not in patched
        assert "MathTex(" not in patched
        assert 'title = Text("Short-run Production Function")' in patched
        assert 'label = Text("MP_L")' in patched
        assert any("LaTeX-free product path" in note for note in notes)

    def test_unsupported_stroke_dash_style_call_is_removed(self) -> None:
        code = "h_line_tax.set_style(stroke_dash=[5, 5])\nself.play(Create(h_line_tax))"

        patched, notes = manim_agent.apply_runtime_compatibility_fixes(code)

        assert "stroke_dash" not in patched
        assert "self.play(Create(h_line_tax))" in patched
        assert any("stroke_dash" in note for note in notes)

    def test_text_default_font_is_injected_for_cloud_chinese_rendering(self) -> None:
        code = """
from manim import *

class GeneratedScene(Scene):
    def construct(self):
        title = Text("帕累托最优", font_size=32)
        self.play(Write(title))
"""

        patched, notes = manim_agent.apply_runtime_compatibility_fixes(code)

        assert "_AEGIS_CJK_FONT" in patched
        assert 'Text.set_default(font=_AEGIS_CJK_FONT)' in patched
        assert 'title = Text("帕累托最优", font_size=32)' in patched
        assert any("CJK-capable" in note for note in notes)

        patched_again, notes_again = manim_agent.apply_runtime_compatibility_fixes(patched)
        assert patched_again == patched
        assert not any("CJK-capable" in note for note in notes_again)

    def test_axes_camel_case_line_helpers_are_rewritten(self) -> None:
        code = """
axes.getHorizontalLine(axes.c2p(3, 4), color=BLUE)
axes.getVerticalLine(axes.c2p(3, 4), color=GREEN)
"""

        patched, notes = manim_agent.apply_runtime_compatibility_fixes(code)

        assert "axes.get_horizontal_line(axes.c2p(3, 4), color=BLUE)" in patched
        assert "axes.get_vertical_line(axes.c2p(3, 4), color=GREEN)" in patched
        assert "getHorizontalLine" not in patched
        assert "getVerticalLine" not in patched
        assert any("camelCase" in note for note in notes)

    def test_axes_plot_line_config_is_converted_to_supported_kwargs(self) -> None:
        code = """
demand = axes.plot(
    lambda x: 10 - x,
    color=BLUE,
    x_range=[0, 8],
    line_config={"stroke_width": 3}
)
supply = axes.plot(lambda x: 2 + x, line_config={"stroke_opacity": 0.5})
"""

        patched, notes = manim_agent.apply_runtime_compatibility_fixes(code)

        assert "stroke_width=3" in patched
        assert "stroke_opacity=0.5" in patched
        assert "line_config" not in patched
        assert any("line_config" in note for note in notes)

    def test_sector_outer_radius_is_rewritten_to_radius_keyword(self) -> None:
        code = """
cake_slice1 = Sector(outer_radius=1.5, angle=PI, color="#E76F51")
ring = AnnularSector(inner_radius=1, outer_radius=2, angle=PI / 2)
"""

        patched, notes = manim_agent.apply_runtime_compatibility_fixes(code)

        assert 'Sector(radius=1.5, angle=PI, color="#E76F51")' in patched
        assert "AnnularSector(inner_radius=1, outer_radius=2, angle=PI / 2)" in patched
        assert "Sector(outer_radius" not in patched
        assert any("Sector outer_radius" in note for note in notes)

    def test_add_coordinates_is_removed_without_latex(self) -> None:
        code = "axes = Axes()\naxes.add_coordinates()\nself.play(Create(axes))"

        with patch.object(manim_agent, "LATEX_AVAILABLE", False):
            patched, notes = manim_agent.apply_runtime_compatibility_fixes(code)

        assert "add_coordinates" not in patched
        assert "self.play(Create(axes))" in patched
        assert any("add_coordinates" in note for note in notes)

    def test_axis_label_strings_use_text_to_avoid_latex(self) -> None:
        code = 'labels = axes.get_axis_labels(x_label="Alice收益", y_label="Bob收益")'

        patched, notes = manim_agent.apply_runtime_compatibility_fixes(code)

        assert 'axes.get_axis_labels(Text(\'Alice收益\', font_size=20), Text(\'Bob收益\', font_size=20))' in patched
        assert "x_label=" not in patched
        assert "y_label=" not in patched
        assert any("get_axis_labels" in note for note in notes)

    def test_brace_label_uses_text_when_latex_is_unavailable(self) -> None:
        code = 'brace = BraceLabel(Line(LEFT, RIGHT), "所有帕累托最优点", brace_direction=UP)'

        with patch.object(manim_agent, "LATEX_AVAILABLE", False):
            patched, notes = manim_agent.apply_runtime_compatibility_fixes(code)

        assert patched == 'brace = BraceLabel(Line(LEFT, RIGHT), "所有帕累托最优点", brace_direction=UP, label_constructor=Text)'
        assert any("BraceLabel" in note for note in notes)

    def test_latex_detection_requires_standalone_class(self) -> None:
        def fake_which(name: str) -> str | None:
            return f"/usr/bin/{name}"

        missing_standalone = Mock(returncode=1, stdout="")

        with patch.object(manim_agent.shutil, "which", side_effect=fake_which), patch.object(
            manim_agent.subprocess,
            "run",
            return_value=missing_standalone,
        ):
            assert not manim_agent.detect_latex_available()

    def test_latex_detection_accepts_complete_toolchain(self) -> None:
        def fake_which(name: str) -> str | None:
            return f"/usr/bin/{name}"

        found_standalone = Mock(returncode=0, stdout="/texmf/standalone.cls\n")

        with patch.object(manim_agent.shutil, "which", side_effect=fake_which), patch.object(
            manim_agent.subprocess,
            "run",
            return_value=found_standalone,
        ):
            assert manim_agent.detect_latex_available()

    def test_json_response_broken_pipe_does_not_escape_render_success_path(self) -> None:
        class BrokenPipeWriter:
            def write(self, _body: bytes) -> None:
                raise BrokenPipeError("client closed")

        class FakeHandler:
            wfile = BrokenPipeWriter()

            def send_response(self, _status: int) -> None:
                pass

            def send_header(self, _name: str, _value: str) -> None:
                pass

            def end_headers(self) -> None:
                pass

        with patch.object(web_app, "append_runtime_log") as append_log:
            web_app.AegisWebHandler._send_json(FakeHandler(), HTTPStatus.OK, {"ok": True})

        append_log.assert_called_once()
        assert append_log.call_args.args[0] == "CLIENT_DISCONNECT"

    def test_json_response_header_disconnect_does_not_escape_render_success_path(self) -> None:
        class FakeHandler:
            wfile = Mock()

            def send_response(self, _status: int) -> None:
                pass

            def send_header(self, _name: str, _value: str) -> None:
                pass

            def end_headers(self) -> None:
                raise BrokenPipeError("client closed during headers")

        with patch.object(web_app, "append_runtime_log") as append_log:
            web_app.AegisWebHandler._send_json(FakeHandler(), HTTPStatus.OK, {"ok": True})

        append_log.assert_called_once()
        assert append_log.call_args.args[0] == "CLIENT_DISCONNECT"

    def test_job_events_keep_student_and_technical_layers_separate(self) -> None:
        job_id = web_app.create_job("解释税收楔子")

        try:
            web_app.emit_job_event(
                job_id,
                status="running",
                stage="repair",
                student_message="这版画面还不够清楚，正在重新组织表达。",
                technical_message="Render failed: NameError curve",
                severity="warn",
                attempt=1,
            )
            snapshot = web_app.job_snapshot(job_id)
        finally:
            with web_app.JOB_STORE_LOCK:
                web_app.JOB_STORE.pop(job_id, None)

        assert snapshot is not None
        assert snapshot["status"] == "running"
        assert snapshot["currentStudentMessage"] == "这版画面还不够清楚，正在重新组织表达。"
        assert snapshot["events"][-1]["studentMessage"] == "这版画面还不够清楚，正在重新组织表达。"
        assert snapshot["technicalEvents"][-1]["technicalMessage"] == "Render failed: NameError curve"

    def test_finish_job_stores_result_for_polling(self) -> None:
        job_id = web_app.create_job("解释税收楔子")

        try:
            web_app.finish_job(job_id, {"ok": True, "code": "from manim import *"})
            snapshot = web_app.job_snapshot(job_id)
        finally:
            with web_app.JOB_STORE_LOCK:
                web_app.JOB_STORE.pop(job_id, None)

        assert snapshot is not None
        assert snapshot["status"] == "succeeded"
        assert snapshot["result"]["ok"] is True

    def test_complex_prompt_is_converted_to_teaching_brief(self) -> None:
        prompt = (
            "此均衡状态。也可以定义游戏者 $i$ 在给定 $s_{-i}$ 时的最优反应集为 "
            "$B_i(s_{-i}) = {s_i^* \\in S_i, U(s_i^*, s_{-i}^*) \\ge U(s_i, s_{-i}^*) "
            "\\mid \\forall s_i' \\in S_i}$。请用动画讲清楚纳什均衡。"
        )

        brief = web_app.build_teaching_brief(prompt)

        assert "教学目标" in brief
        assert "不要把原始公式整段塞进画面" in brief
        assert "画面段落" in brief
        assert "$B_i" not in brief

    def test_model_timeout_retries_with_teaching_brief_before_failure(self) -> None:
        prompt = (
            "此均衡状态。也可以定义游戏者 $i$ 在给定 $s_{-i}$ 时的最优反应集为 "
            "$B_i(s_{-i}) = {s_i^* \\in S_i, U(s_i^*, s_{-i}^*) \\ge U(s_i, s_{-i}^*) "
            "\\mid \\forall s_i' \\in S_i}$。请用动画讲清楚纳什均衡。"
        )
        job_id = web_app.create_job(prompt)
        payload = {
            "provider": "minimax-coding-cn",
            "apiKey": "real-test-key",
            "prompt": prompt,
            "model": "MiniMax-M2.7",
            "sceneName": "GeneratedScene",
            "temperature": 0.2,
            "noRender": True,
        }

        generated_code = "from manim import *\n\nclass GeneratedScene(Scene):\n    def construct(self):\n        self.add(Text('Nash'))\n"

        try:
            with patch.object(
                web_app,
                "generate_code_with_llm",
                side_effect=[RuntimeError("The read operation timed out"), (generated_code, "MiniMax", "https://api.test/messages")],
            ) as generate:
                web_app.run_generate_job(job_id, payload)
            snapshot = web_app.job_snapshot(job_id)
        finally:
            with web_app.JOB_STORE_LOCK:
                web_app.JOB_STORE.pop(job_id, None)

        assert generate.call_count == 2
        assert "教学 brief" in generate.call_args_list[0].kwargs["user_prompt"]
        assert generate.call_args_list[1].kwargs["model"] == "MiniMax-M2.7-highspeed"
        assert snapshot is not None
        assert snapshot["status"] == "succeeded"
        assert any(event["stage"] == "repair" for event in snapshot["events"])


if __name__ == "__main__":
    unittest.main()

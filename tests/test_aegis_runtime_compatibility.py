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

    def test_unsupported_stroke_dash_style_call_is_removed(self) -> None:
        code = "h_line_tax.set_style(stroke_dash=[5, 5])\nself.play(Create(h_line_tax))"

        patched, notes = manim_agent.apply_runtime_compatibility_fixes(code)

        assert "stroke_dash" not in patched
        assert "self.play(Create(h_line_tax))" in patched
        assert any("stroke_dash" in note for note in notes)

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

    def test_add_coordinates_is_removed_without_latex(self) -> None:
        code = "axes = Axes()\naxes.add_coordinates()\nself.play(Create(axes))"

        with patch.object(manim_agent, "LATEX_AVAILABLE", False):
            patched, notes = manim_agent.apply_runtime_compatibility_fixes(code)

        assert "add_coordinates" not in patched
        assert "self.play(Create(axes))" in patched
        assert any("add_coordinates" in note for note in notes)

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


if __name__ == "__main__":
    unittest.main()

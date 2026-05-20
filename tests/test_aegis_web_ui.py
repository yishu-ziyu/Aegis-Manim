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

    def test_teaching_brief_requires_chinese_visible_language(self) -> None:
        brief = web_app.build_teaching_brief("解释 $MP_L < 0$ 的经济含义")

        assert "默认使用中文标题" in brief
        assert "变量符号可以保留英文缩写" in brief
        assert "不使用 Tex/MathTex" in brief


if __name__ == "__main__":
    unittest.main()

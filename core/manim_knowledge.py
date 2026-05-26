from __future__ import annotations

import ast
import re
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class KnowledgeSource:
    id: str
    title: str
    kind: str
    url: str


@dataclass(frozen=True)
class PrecheckIssue:
    category: str
    severity: str
    student_message: str
    technical_message: str
    repair_hint: str
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class ErrorClassification:
    category: str
    severity: str
    student_message: str
    technical_message: str
    repair_prompt: str
    recipe_ids: tuple[str, ...]


KNOWLEDGE_SOURCES: tuple[KnowledgeSource, ...] = (
    KnowledgeSource(
        id="manim-scenes",
        title="Manim Community scenes and construct flow",
        kind="official",
        url="https://docs.manim.community/en/stable/tutorials/building_blocks.html",
    ),
    KnowledgeSource(
        id="manim-mobjects",
        title="Manim Community mobjects and animations",
        kind="official",
        url="https://docs.manim.community/en/stable/reference.html",
    ),
    KnowledgeSource(
        id="manim-text",
        title="Manim Community text and LaTeX mobjects",
        kind="official",
        url="https://docs.manim.community/en/stable/guides/using_text.html",
    ),
    KnowledgeSource(
        id="local-bug-log",
        title="Aegis local render failures and retry traces",
        kind="local",
        url="logs/bug_trace.jsonl",
    ),
)


REPAIR_RECIPES: dict[str, dict[str, Any]] = {
    "scene-structure": {
        "student": "正在把讲解整理成 Manim 能执行的场景结构。",
        "prompt": "Return one complete Python file with `from manim import *`, one Scene subclass, and a construct(self) method.",
        "sourceIds": ("manim-scenes",),
    },
    "latex-to-text": {
        "student": "正在把依赖 LaTeX 的文字换成更稳定的普通文本表达。",
        "prompt": "Avoid Tex and MathTex. Use Text for labels and set BraceLabel(label_constructor=Text) when labels are needed.",
        "sourceIds": ("manim-text", "local-bug-log"),
    },
    "axes-api": {
        "student": "正在把坐标轴和曲线写法调整为当前 Manim 版本支持的形式。",
        "prompt": "Use supported Axes methods such as axes.c2p, axes.plot, get_horizontal_line, and get_vertical_line. Do not use camelCase helpers or line_config.",
        "sourceIds": ("manim-mobjects", "local-bug-log"),
    },
    "layout-fit": {
        "student": "正在重新安排画面位置，避免标签或图形挤出画面。",
        "prompt": "Group related mobjects, scale groups to fit the frame, use arrange/buff, and place labels with next_to or to_edge. Do not write a new Text object over an old one; use FadeOut or ReplacementTransform before changing explanations.",
        "sourceIds": ("manim-mobjects", "local-bug-log"),
    },
    "undefined-symbol": {
        "student": "正在补齐动画对象之间的引用关系。",
        "prompt": "Define every mobject before it is used in play/add/transform calls. Keep variable names consistent.",
        "sourceIds": ("manim-scenes", "local-bug-log"),
    },
}


def knowledge_sources_for_ui() -> list[dict[str, Any]]:
    return [asdict(source) for source in KNOWLEDGE_SOURCES]


def repair_recipes_for_ui() -> list[dict[str, Any]]:
    return [
        {"id": recipe_id, **recipe}
        for recipe_id, recipe in REPAIR_RECIPES.items()
    ]


def precheck_manim_code(code: str, expected_scene_name: str) -> list[PrecheckIssue]:
    issues: list[PrecheckIssue] = []
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [
            PrecheckIssue(
                category="syntax",
                severity="error",
                student_message="生成的动画脚本还不是完整可执行的 Python，正在重新整理。",
                technical_message=f"Python syntax error at line {exc.lineno}: {exc.msg}",
                repair_hint="Return valid Python only, with no markdown or prose outside the code.",
                source_ids=("manim-scenes",),
            )
        ]

    has_manim_import = any(_is_manim_import(node) for node in tree.body)
    if not has_manim_import:
        issues.append(
            PrecheckIssue(
                category="scene-structure",
                severity="warn",
                student_message="正在补齐 Manim 场景需要的基础导入。",
                technical_message="Missing `from manim import *` or `import manim`.",
                repair_hint=REPAIR_RECIPES["scene-structure"]["prompt"],
                source_ids=("manim-scenes",),
            )
        )

    scene_classes = [_scene_class_name(node) for node in tree.body if isinstance(node, ast.ClassDef)]
    scene_classes = [name for name in scene_classes if name]
    if not scene_classes:
        issues.append(
            PrecheckIssue(
                category="scene-structure",
                severity="error",
                student_message="还没有形成可播放的 Manim 场景，正在重写场景结构。",
                technical_message="No class inheriting from Scene was found.",
                repair_hint=REPAIR_RECIPES["scene-structure"]["prompt"],
                source_ids=("manim-scenes",),
            )
        )
    elif expected_scene_name and expected_scene_name not in scene_classes:
        issues.append(
            PrecheckIssue(
                category="scene-structure",
                severity="warn",
                student_message="正在统一场景名称，确保渲染器能找到正确动画。",
                technical_message=f"Expected scene `{expected_scene_name}`, found {', '.join(scene_classes)}.",
                repair_hint="Keep the Scene class name consistent with the requested scene name or the detected render target.",
                source_ids=("manim-scenes",),
            )
        )

    for class_node in [node for node in tree.body if isinstance(node, ast.ClassDef)]:
        if _scene_class_name(class_node) and not _has_construct_method(class_node):
            issues.append(
                PrecheckIssue(
                    category="scene-structure",
                    severity="error",
                    student_message="场景缺少实际演示步骤，正在补写动画过程。",
                    technical_message=f"Scene class `{class_node.name}` has no construct(self) method.",
                    repair_hint="Put all mobject creation and self.play/self.wait calls inside construct(self).",
                    source_ids=("manim-scenes",),
                )
            )

    if re.search(r"\b(MathTex|Tex)\s*\(", code):
        issues.append(
            PrecheckIssue(
                category="latex",
                severity="error",
                student_message="检测到视频脚本依赖 LaTeX，正在改成普通文字公式以保证中文教学视频稳定产出。",
                technical_message="Tex/MathTex usage is blocked in the default product path; use Text(...) formula labels instead.",
                repair_hint=REPAIR_RECIPES["latex-to-text"]["prompt"],
                source_ids=("manim-text", "local-bug-log"),
            )
        )

    if _has_text_without_font_size(tree):
        issues.append(
            PrecheckIssue(
                category="layout-fit",
                severity="warn",
                student_message="检测到部分文字没有显式字号，正在降低文字挤压和遮挡风险。",
                technical_message="Text(...) call without explicit font_size; default text can become too large for dense teaching scenes.",
                repair_hint="Set font_size on every Text object, usually 18-32 for labels and 32-40 for short titles.",
                source_ids=("manim-text", "local-bug-log"),
            )
        )

    if _has_repeated_direct_text_without_cleanup(tree):
        issues.append(
            PrecheckIssue(
                category="layout-fit",
                severity="error",
                student_message="检测到连续文字可能叠在同一区域，正在要求模型先清场或替换旧文字。",
                technical_message="Multiple direct Write(Text(...)) or add(Text(...)) calls appear without FadeOut/ReplacementTransform cleanup.",
                repair_hint=REPAIR_RECIPES["layout-fit"]["prompt"],
                source_ids=("manim-text", "local-bug-log"),
            )
        )

    unsupported_patterns = (
        (r"\.get_h_line\s*\(", "Use get_horizontal_line instead of get_h_line."),
        (r"\.get_v_line\s*\(", "Use get_vertical_line instead of get_v_line."),
        (r"\.getHorizontalLine\s*\(", "Use get_horizontal_line instead of camelCase helpers."),
        (r"\.getVerticalLine\s*\(", "Use get_vertical_line instead of camelCase helpers."),
        (r"line_config\s*=", "Pass supported stroke kwargs directly instead of line_config."),
        (r"stroke_dash\s*=", "Avoid unsupported stroke_dash style calls."),
    )
    for pattern, message in unsupported_patterns:
        if re.search(pattern, code):
            issues.append(
                PrecheckIssue(
                    category="axes-api",
                    severity="warn",
                    student_message="检测到旧版或不稳定的坐标轴写法，正在改成当前 Manim 支持的形式。",
                    technical_message=message,
                    repair_hint=REPAIR_RECIPES["axes-api"]["prompt"],
                    source_ids=("manim-mobjects", "local-bug-log"),
                )
            )

    if _has_axes_label_constructor_mismatch(tree):
        issues.append(
            PrecheckIssue(
                category="axes-api",
                severity="warn",
                student_message="检测到坐标轴标签可能触发 LaTeX 或旧版参数，正在改成稳定的 Text 标签。",
                technical_message="Axes labels must use supported Manim Community APIs: no x_label/y_label kwargs on Axes(...), and get_axis_labels(...) should receive Text(...) mobjects.",
                repair_hint=REPAIR_RECIPES["axes-api"]["prompt"],
                source_ids=("manim-mobjects", "manim-text", "local-bug-log"),
            )
        )

    return issues


def classify_render_error(detail: str) -> ErrorClassification:
    text = detail or ""
    lowered = text.lower()

    if "latex" in lowered or "tex" in lowered or "standalone.cls" in lowered:
        return _classification(
            "latex",
            "这版动画的文字渲染依赖 LaTeX，正在改成更稳定的文本表达。",
            "Render failed in LaTeX/Text rendering.",
            "latex-to-text",
        )
    if "nameerror" in lowered or "is not defined" in lowered:
        return _classification(
            "undefined-symbol",
            "这版动画里有对象引用没有接上，正在补齐画面元素之间的关系。",
            "Render failed because a Python symbol was not defined.",
            "undefined-symbol",
        )
    if "syntaxerror" in lowered or "invalid syntax" in lowered:
        return ErrorClassification(
            category="syntax",
            severity="error",
            student_message="动画脚本语法不完整，正在重新整理成可执行代码。",
            technical_message="Generated Python has syntax errors.",
            repair_prompt="Return valid Python code only. Do not include markdown fences or explanation text.",
            recipe_ids=("scene-structure",),
        )
    if "attributeerror" in lowered or "unexpected keyword" in lowered or "got an unexpected" in lowered:
        return _classification(
            "manim-api",
            "这版动画调用了当前 Manim 不支持的写法，正在改成官方 API 支持的形式。",
            "Render failed because the generated code used an unsupported Manim API.",
            "axes-api",
        )
    if "indexerror" in lowered or "valueerror" in lowered or "x_range" in lowered:
        return _classification(
            "geometry-range",
            "这版图形的坐标或范围设置不稳定，正在调整画面尺度。",
            "Render failed because a geometry/range value was invalid.",
            "layout-fit",
        )
    if "not found" in lowered and "scene" in lowered:
        return _classification(
            "scene-structure",
            "渲染器没有找到正确场景，正在统一场景名称和入口。",
            "Render failed because the requested Scene was not found.",
            "scene-structure",
        )

    return ErrorClassification(
        category="unknown-render",
        severity="error",
        student_message="这版画面还没有成功渲染，正在根据错误信息重新组织表达。",
        technical_message="Render failed with an unclassified error.",
        repair_prompt=(
            "Use only conservative Manim Community APIs. Prefer Text over LaTeX, simple Axes/Line/Dot/Polygon, "
            "and keep all objects inside the frame."
        ),
        recipe_ids=("scene-structure", "layout-fit"),
    )


def build_repair_feedback(
    *,
    original_prompt: str,
    render_error: str,
    classification: ErrorClassification,
    precheck_issues: list[PrecheckIssue],
    attempt: int,
) -> str:
    issue_lines = [
        f"- [{issue.category}/{issue.severity}] {issue.technical_message} Repair: {issue.repair_hint}"
        for issue in precheck_issues[:6]
    ]
    recipes = [REPAIR_RECIPES[recipe_id]["prompt"] for recipe_id in classification.recipe_ids if recipe_id in REPAIR_RECIPES]
    return "\n".join(
        [
            "# Aegis Manim repair context",
            f"Attempt: {attempt}",
            f"Original learning request: {original_prompt}",
            f"Error category: {classification.category}",
            f"Student-facing repair meaning: {classification.student_message}",
            "Relevant precheck issues:",
            *(issue_lines or ["- None"]),
            "Repair recipes:",
            *(f"- {recipe}" for recipe in recipes),
            "Renderer error excerpt:",
            render_error[-1800:],
            "Regenerate the full Manim scene using the recipes above. Keep the teaching idea intact.",
        ]
    )


def summarize_precheck_for_prompt(issues: list[PrecheckIssue]) -> str:
    if not issues:
        return ""
    lines = [
        "# Aegis pre-render rule check",
        "The generated code triggered these Manim rule checks before rendering:",
    ]
    for issue in issues[:8]:
        lines.append(f"- {issue.category}/{issue.severity}: {issue.technical_message} Repair: {issue.repair_hint}")
    lines.append("Regenerate the full scene and fix these issues before rendering.")
    return "\n".join(lines)


def _classification(category: str, student: str, technical: str, recipe_id: str) -> ErrorClassification:
    recipe = REPAIR_RECIPES[recipe_id]
    return ErrorClassification(
        category=category,
        severity="error",
        student_message=student,
        technical_message=technical,
        repair_prompt=str(recipe["prompt"]),
        recipe_ids=(recipe_id,),
    )


def _is_manim_import(node: ast.stmt) -> bool:
    if isinstance(node, ast.ImportFrom):
        return node.module == "manim"
    if isinstance(node, ast.Import):
        return any(alias.name == "manim" for alias in node.names)
    return False


def _scene_class_name(node: ast.ClassDef) -> str | None:
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id.endswith("Scene"):
            return node.name
        if isinstance(base, ast.Attribute) and base.attr.endswith("Scene"):
            return node.name
    return None


def _has_construct_method(node: ast.ClassDef) -> bool:
    return any(isinstance(item, ast.FunctionDef) and item.name == "construct" for item in node.body)


def _is_call_named(node: ast.AST, names: set[str]) -> bool:
    if not isinstance(node, ast.Call):
        return False
    if isinstance(node.func, ast.Name):
        return node.func.id in names
    if isinstance(node.func, ast.Attribute):
        return node.func.attr in names
    return False


def _has_text_without_font_size(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if not _is_call_named(node, {"Text"}):
            continue
        assert isinstance(node, ast.Call)
        if not any(keyword.arg == "font_size" for keyword in node.keywords):
            return True
    return False


def _call_contains_text(node: ast.AST) -> bool:
    return any(_is_call_named(child, {"Text"}) for child in ast.walk(node))


def _call_contains_cleanup(node: ast.AST) -> bool:
    return any(
        _is_call_named(child, {"FadeOut", "ReplacementTransform", "Transform"})
        for child in ast.walk(node)
    )


def _is_direct_text_write_or_add(node: ast.AST) -> bool:
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
        return False
    call = node.value
    if isinstance(call.func, ast.Attribute) and call.func.attr in {"play", "add"}:
        return _call_contains_text(call)
    return False


def _has_repeated_direct_text_without_cleanup(tree: ast.AST) -> bool:
    for class_node in [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]:
        for item in class_node.body:
            if not isinstance(item, ast.FunctionDef) or item.name != "construct":
                continue
            pending_text = False
            for statement in item.body:
                if _call_contains_cleanup(statement):
                    pending_text = False
                    continue
                if _is_direct_text_write_or_add(statement):
                    if pending_text:
                        return True
                    pending_text = True
    return False


def _has_axes_label_constructor_mismatch(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _is_call_named(node, {"Axes"}) and any(
            keyword.arg in {"x_label", "y_label"} for keyword in node.keywords
        ):
            return True
        if isinstance(node.func, ast.Attribute) and node.func.attr == "get_axis_labels":
            if any(isinstance(arg, ast.Constant) and isinstance(arg.value, str) for arg in node.args):
                return True
    return False

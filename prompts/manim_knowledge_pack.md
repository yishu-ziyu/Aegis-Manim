# Manim Knowledge Pack

Target runtime: Manim Community Edition 0.19.2 in this local project. Treat newer documentation as guidance only; prefer APIs verified by this runtime, the local `docs/source` tree, and repository tests.

Refresh sources: local Manim docs under `docs/source`, official Manim Community documentation, official examples/gallery, and high-signal repository tests under `tests/test_graphical_units`, `tests/module`, and `tests/test_scene_rendering`.

## Core scene contract

- Write one complete Python file starting with `from manim import *`.
- Put all animation logic inside `class GeneratedScene(Scene): def construct(self):`.
- Create mobjects first, then display them with `self.add(...)` or `self.play(...)`.
- Use stable, common animations: `Create`, `Write`, `FadeIn`, `FadeOut`, `Transform`, `ReplacementTransform`, `TransformFromCopy`, `Indicate`, `Circumscribe`, `MoveAlongPath`.
- Use `self.wait(0.5)` or `self.wait(1)` after key visual steps so the video has readable pacing.

## Text and labels

- This environment may not have a complete LaTeX toolchain. Do not use `Tex`, `MathTex`, `DecimalTable`, `MathTable`, or default numeric axis labels unless the user explicitly asks for LaTeX and the runtime confirms it.
- Use `Text("x^2", font_size=24)` for formulas and labels.
- For axis labels, prefer `axes.get_axis_labels(x_label=Text("x"), y_label=Text("y"))`.
- For braces, use `BraceLabel(..., label_constructor=Text)`.
- Keep text short and place it with `to_edge`, `next_to`, `move_to`, or `arrange`; avoid overlapping labels.
- Every `Text(...)` must set explicit `font_size`; use 18-28 for dense labels/captions and reserve 30-40 for short titles.
- Manage every transient text object explicitly. If a caption, paragraph, or bullet group is only needed for one step, store it in a variable and remove it with `FadeOut(...)` before the next text appears.
- When two explanations occupy the same region, fade out the old explanation before fading in the new one. Use `ReplacementTransform` for shapes or regions, not for Chinese sentences.
- At a scene or section boundary, fade out the temporary explanation group with `self.play(FadeOut(section_group))`. Leave only persistent visual anchors such as axes, frontier curves, or a main title.
- Do not create multiple `Text(...)` objects at the same `to_edge`, `next_to`, or `move_to` position without first removing or transforming the previous one.
- For paragraph-like explanations, split text into multiple short `Text` rows in a `VGroup(...).arrange(DOWN, aligned_edge=LEFT, buff=0.18)` and call `scale_to_fit_width(...)` before placing the group.
- Default visible scene language is Chinese. Keep formula symbols compact, but write titles, captions, axis explanations, stage labels, and conclusions in Chinese unless the user explicitly requests another language.
- If a model draft uses English prose, translate it before constructing visible `Text(...)` objects. Keep compact symbols only when paired with Chinese labels such as `价格 P`, `数量 Q`, `需求 D`, `供给 S`, `边际成本 MC`, or `边际收益 MR`.
- Do not animate one Chinese sentence into another with `Transform` or `ReplacementTransform`; use `FadeOut(old_caption)` followed by `FadeIn(new_caption)` so intermediate frames do not show mixed Chinese glyphs.
- When the user provides LaTeX-style formulas, show them as readable plain-text formula labels with `Text(..., font_size=...)`; do not introduce `Tex` or `MathTex` just because the prompt contains `$...$`, `\\(...)`, or `\\[...]`.

## Layout patterns

- Build related objects with `VGroup(...)`, then use `.arrange(DOWN, buff=...)`, `.next_to(...)`, `.to_edge(...)`, `.shift(...)`, or `.scale(...)`.
- For repeated cards or rows, create the shape and text together in a `VGroup` so transforms keep alignment.
- Use a constrained camera-safe layout: title near `UP`, explanatory labels near objects, summary near `DOWN`.
- Treat each explanatory phase as a `VGroup` when possible, for example `intro_group = VGroup(label, arrow, caption)`, so it can exit with one `FadeOut(intro_group)`.
- Use dark backgrounds sparingly and set text color for contrast when `self.camera.background_color` changes.

## Axes and graphs

- Use `Axes(x_range=[min, max, step], y_range=[min, max, step], x_length=..., y_length=..., axis_config={"include_numbers": False})`.
- Use `axes.plot(lambda x: ..., x_range=[...], color=...)` for functions.
- Use `axes.c2p(x, y)` to position dots, arrows, labels, or polygons in graph coordinates.
- Avoid `add_coordinates()` and `include_numbers=True` unless LaTeX is available.
- For helper lines, use `axes.get_horizontal_line(point)` and `axes.get_vertical_line(point)`.
- When drawing feasible regions, use `Polygon(*points, fill_opacity=..., stroke_width=...)`.

## Dynamic animation patterns

- Use `ValueTracker` for scalar state and animate it with `self.play(tracker.animate.set_value(...))`.
- Use `always_redraw(lambda: ...)` when a mobject must update from a tracker every frame.
- If a `ValueTracker` itself has an updater, add it to the scene with `self.add(tracker)`.
- For explanatory movement, prefer moving visible dots/arrows along a path over complex custom updater logic.

## Community-quality composition patterns

- Tell the concept as a sequence: introduce visual vocabulary, show the initial state, animate the mechanism, then summarize the invariant.
- Between sequence steps, clean the stage: use `ReplacementTransform` for evolving explanations and `FadeOut` for obsolete text before adding the next paragraph.
- Prefer simple primitives that render reliably: `Dot`, `Circle`, `Square`, `Rectangle`, `RoundedRectangle`, `Line`, `Arrow`, `DoubleArrow`, `Polygon`, `Brace`, `VGroup`, `Axes`.
- Use color semantically: one color for the moving state, one for constraints/frontiers, one for final conclusion.
- Avoid brittle advanced features unless necessary: external images, SVG files, plugins, OpenGL-only objects, custom shaders, complex 3D camera moves, and LaTeX-heavy scenes.

## Common failure avoidance

- Do not call methods that are not stable across Manim versions, such as camelCase helpers or old aliases.
- Do not create text so large that it leaves the frame; keep most labels between font sizes 18 and 32.
- Do not output explanations, markdown fences, or extra prose outside the Python code.
- Do not rely on network, local asset files, fonts, or images unless explicitly provided by the user.
- Keep generated scenes segmented-render friendly: a clear multi-step visual explanation, 8-20 animations, no dense object swarms, no long chained waits, no `BraceLabel`, and no `LaggedStart` on hosted renders.

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
- Bottom summaries must not collide with the x-axis caption: keep the conclusion `to_edge(DOWN, buff=0.5)` or higher, limit it to at most 2 lines, and if numeric derivations are shown place them in a right-side `VGroup` column instead of stacking under the axes.
- Bottom-summary hard layout: the conclusion is ONE `VGroup` of at most 2 short `Text` lines with NO separate title line, placed with `.to_edge(DOWN, buff=0.4)`. Never build "title + numbered list" stacks at the bottom — with `buff=1.2` or a third line the text leaves the frame and clips. If the frame already has axes, shift the whole axes group up first (e.g. `axes_group.shift(UP * 0.5)`) so the bottom 1.2 units stay free, and `FadeOut` any bottom annotation arrows (like `产出↑`) before writing the summary.
- Marked equilibrium/intersection points must be computed IN PYTHON CODE, never hand-typed literals. Define curve parameters as named constants, then derive every crossing from them so the interpreter does the arithmetic:
  ```
  # D: P = 9 - 0.6q, S: P = 1 + 0.4q  =>  9 - 0.6q = 1 + 0.4q
  Qm = (9 - 1) / (0.6 + 0.4)          # = 8.0
  Pm = 9 - 0.6 * Qm                    # reuse the SAME parameters
  mkt_dot = Dot(axes.c2p(Qm, Pm), ...)
  ```
  Hand-typed pairs like `Qm, Pm = 8.0, 5.0` (Pm should be 4.2) are the #1 source of dots visibly floating off the crossing. If you must state numbers, put the derivation in a comment — but the Dot always uses the computed variables.
- Closing summaries may only claim what the scene actually demonstrated: name exactly the mechanism shown (e.g. monetary expansion shifts LM) and never broaden it into sibling mechanisms that were not animated (fiscal policy shifts IS, not LM).
- Policy magnitudes must be calibrated to the claim: if the narration says a tax/subsidy restores the social optimum, set the per-unit policy to the exact vertical gap between the two cost curves at the optimal quantity and show the new equilibrium landing ON that point (compute and substitute-check it). Never circle two points together unless they truly coincide — a highlight box around visibly separate dots reads as a contradiction.
- When 3+ curve labels would land in the same corner via `next_to(curve, RIGHT/LEFT)`, stack them deliberately: collect them in a `VGroup().arrange(DOWN, aligned_edge=LEFT, buff=0.15)` pinned to that corner, or tag each label at a different height along its own curve with `move_to(axes.c2p(x, y_of_curve)+OFFSET)`. Overlapping corner labels are unreadable. The same applies to axis max-value labels vs point coordinate labels sharing a corner (e.g. a "10" tick label under a "(0,10)" point label renders as garbled overlap) — offset one or drop the tick label.
- To attach a square/shape to a polygon side, center it at the side's MIDPOINT offset along the outward direction: `mid = (P1 + P2) / 2; outward = <unit normal>; shape.move_to(mid + outward * (side_length / 2))`. Never anchor to an endpoint with `endpoint + LEFT/DOWN * (size/2)` unless the side is axis-aligned AND the shape spans exactly from that endpoint — a missing half-side offset makes squares slide off the triangle and overlap each other. Derive each square's `side_length` from the SAME endpoints (e.g. `side = np.linalg.norm(P2 - P1)`) so the size can never be bound to the wrong leg.
- An ad-hoc normal `(-dy, dx)` may point INWARD depending on vertex order. Always disambiguate with the centroid: `centroid = (P1+P2+P3)/3; mid = (P1+P2)/2; n = <perpendicular of P2-P1>; if np.dot(n, mid - centroid) < 0: n = -n`. Apply this to every side's normal independently — never assume one flip works for all sides.
- Numeric text values must be computed in the f-string from the same variables used for geometry: `Text(f"a² = {a*a}")` — never hand-typed `Text("a² = 9")` beside `a, b = 4, 3`.

## Classic proof template: Pythagorean rotating squares (勾股定理)

For any prompt about 勾股定理 / 旋转拼合 / 正方形面积证明, COPY this construction and only change the labels/wording — do not reinvent the geometry (models repeatedly misplace these squares):

```python
a, b = 3.0, 4.0
c = np.sqrt(a * a + b * b)
A = np.array([0.0, 0.0, 0.0])   # 直角顶点
B = np.array([a, 0.0, 0.0])
C = np.array([0.0, b, 0.0])
triangle = Polygon(A, B, C, color=WHITE, fill_opacity=0.2)
centroid = (A + B + C) / 3

def outward_square(P1, P2, color):
    side = np.linalg.norm(P2 - P1)          # 边长由同一对端点推导
    mid = (P1 + P2) / 2
    d = (P2 - P1) / side
    n = np.array([-d[1], d[0], 0.0])        # 候选法向
    if np.dot(n, mid - centroid) < 0:       # 质心点积消歧，保证朝外
        n = -n
    sq = Square(side_length=side, color=color, fill_opacity=0.3)
    sq.move_to(mid + n * (side / 2))        # 先居中
    sq.rotate(angle_of_vector(P2 - P1))     # 再旋转对齐边（绕中心，不影响位置）
    return sq

sq_a = outward_square(A, B, BLUE)    # a² 水平腿外侧
sq_b = outward_square(A, C, GREEN)   # b² 竖直腿外侧
sq_c = outward_square(B, C, YELLOW)  # c² 斜边外侧
```

Then label each square with computed values (`Text(f"a² = {a*a}")`) and animate the squares appearing one by one.
- Never annotate an area/rectangle ABOVE its top edge when that edge sits in the upper half of the axes — the label collides with the title zone. Put value labels INSIDE the rectangle (`.move_to(rect.get_center())`, white or contrasting color) or beside it at mid-height. Reserve `to_edge(UP)` exclusively for the title and at most one caption row.
- Treat each explanatory phase as a `VGroup` when possible, for example `intro_group = VGroup(label, arrow, caption)`, so it can exit with one `FadeOut(intro_group)`.
- Use dark backgrounds sparingly and set text color for contrast when `self.camera.background_color` changes.

## Axes and graphs

- Use `Axes(x_range=[min, max, step], y_range=[min, max, step], x_length=..., y_length=..., axis_config={"include_numbers": False})`.
- Use `axes.plot(lambda x: ..., x_range=[...], color=...)` for functions.
- Use `axes.c2p(x, y)` to position dots, arrows, labels, or polygons in graph coordinates.
- Avoid `add_coordinates()` and `include_numbers=True` unless LaTeX is available.
- For helper lines, use `axes.get_horizontal_line(point)` and `axes.get_vertical_line(point)`.
- For regions bounded by plotted curves (area under/ between curves), use `axes.get_area(graph, x_range=[a, b], bounded_graph=boundary_plot)` so the fill follows the real curve. Do NOT approximate a curved boundary with a straight-edged `Polygon` — the fill edge will visibly diverge from the plotted line.
- Use `Polygon(*points, fill_opacity=..., stroke_width=...)` only for genuinely straight-edged regions such as rectangles or step areas, with every vertex from `axes.c2p(...)`.

## Welfare and surplus regions (economics correctness)

- Compute all equilibria analytically first (solve demand = supply, or MR = MC) and derive exact prices/quantities before drawing; never eyeball intersection points.
- Shade each welfare region with the curves as real boundaries. Consumer surplus above price Pc: `axes.get_area(demand_plot, x_range=[0, Qe], bounded_graph=axes.plot(lambda x: Pc, x_range=[0, Qe]))`. Producer surplus: mirror it against the supply curve.
- When a policy (tax, monopoly) changes the equilibrium, decompose the change truthfully: the transfer rectangle between old and new price over the new quantity, and the deadweight-loss triangle bounded by the demand and supply/MC curves between the old and new quantities. Draw them as separate regions with separate labels — never merge them into one arbitrary triangle.
- Label each shaded region with a short Chinese label (e.g. `消费者剩余`, `无谓损失`, `税收转移`) placed inside the region, and reference the same color in the closing summary.

## Game theory payoff matrices

- Build each cell at least 2.4 units wide and tall so payoffs never feel cramped; keep payoff text `font_size` >= 22 with player A's payoff on the first line and player B's on the second.
- Assemble `matrix_group = VGroup(grid, row_header, col_header, legend).arrange(DOWN, buff=0.35)` then `matrix_group.move_to(ORIGIN)` — the matrix must be horizontally centered in the frame, never hugging the left edge with empty space on the right.
- Place the legend UNDER the matrix inside that group (`.arrange(DOWN).next_to(grid, DOWN)`). Never pin a side legend with `to_edge(RIGHT)` next to a centered grid — the two compete for width and the legend clips at the frame edge.
- Highlight best responses with a rounded `SurroundingRectangle` in one accent color and the Nash equilibrium cell in another; state the equilibrium as `(策略A, 策略B)` in a caption below the matrix.

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

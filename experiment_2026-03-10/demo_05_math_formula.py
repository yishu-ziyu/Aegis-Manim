from manim import *


class Demo5_FormulaAnimation(Scene):
    def construct(self):
        title = Text("公式动画", font_size=48).to_edge(UP)
        self.add(title)

        formula = Text("E = mc^2", font_size=72)
        self.play(Write(formula))
        self.wait(1)

        parts = VGroup(
            formula[0:1],
            formula[1:3],
            formula[3:6]
        )
        self.play(parts[0].animate.set_color(YELLOW))
        self.wait(0.5)
        self.play(parts[1].animate.set_color(BLUE))
        self.wait(0.5)
        self.play(parts[2].animate.set_color(RED))
        self.wait(2)

        result = Text("E = mc^2", font_size=36).to_edge(DOWN)
        self.play(Write(result))
        self.wait(2)

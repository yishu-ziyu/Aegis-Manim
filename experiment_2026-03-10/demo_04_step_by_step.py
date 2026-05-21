from manim import *


class Demo4_StepByStep(Scene):
    def construct(self):
        title = Text("解题步骤", font_size=48).to_edge(UP)
        self.add(title)

        steps = VGroup(
            Text("1. 理解题意", font_size=36),
            Text("2. 列出已知条件", font_size=36),
            Text("3. 分析问题", font_size=36),
            Text("4. 求解答案", font_size=36),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.8)

        self.play(Write(steps[0]))
        self.wait(0.8)

        arrow1 = Arrow(start=LEFT, end=RIGHT, color=YELLOW).next_to(steps[0], RIGHT)
        self.play(Create(arrow1))
        self.wait(0.5)

        self.play(Write(steps[1]))
        self.wait(0.8)

        arrow2 = Arrow(start=LEFT, end=RIGHT, color=YELLOW).next_to(steps[1], RIGHT)
        self.play(Create(arrow2))
        self.wait(0.5)

        self.play(Write(steps[2]))
        self.wait(0.8)

        arrow3 = Arrow(start=LEFT, end=RIGHT, color=YELLOW).next_to(steps[2], RIGHT)
        self.play(Create(arrow3))
        self.wait(0.5)

        self.play(Write(steps[3]))
        self.wait(1)

        highlight = SurroundingRectangle(steps[3], color=RED, buff=0.2)
        self.play(Create(highlight))
        self.wait(2)

from manim import *


class Demo6_ArrowAnnotation(Scene):
    def construct(self):
        title = Text("箭头与标注", font_size=48).to_edge(UP)
        self.add(title)

        line = Line(LEFT * 4, RIGHT * 4, color=WHITE)
        self.play(Create(line))

        points = [
            Dot(point=LEFT * 2, color=BLUE),
            Dot(point=ORIGIN, color=GREEN),
            Dot(point=RIGHT * 2, color=RED),
        ]

        for dot in points:
            self.play(FadeIn(dot))

        arrow1 = Arrow(line.get_top(), points[0].get_top(), color=BLUE)
        arrow2 = Arrow(line.get_top(), points[1].get_top(), color=GREEN)
        arrow3 = Arrow(line.get_top(), points[2].get_top(), color=RED)

        self.play(GrowArrow(arrow1))
        self.wait(0.3)
        self.play(GrowArrow(arrow2))
        self.wait(0.3)
        self.play(GrowArrow(arrow3))
        self.wait(1)

        label1 = Text("A", font_size=36, color=BLUE).next_to(arrow1, UP)
        label2 = Text("B", font_size=36, color=GREEN).next_to(arrow2, UP)
        label3 = Text("C", font_size=36, color=RED).next_to(arrow3, UP)

        self.play(Write(label1), Write(label2), Write(label3))
        self.wait(2)

        brace = Brace(Line(LEFT * 2, ORIGIN), DOWN, color=YELLOW)
        brace_label = Text("距离 2", font_size=24, color=YELLOW).next_to(brace, DOWN)

        self.play(GrowFromCenter(brace), Write(brace_label))
        self.wait(2)

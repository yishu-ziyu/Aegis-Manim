from manim import *


class Demo2_GeometryAnimation(Scene):
    def construct(self):
        title = Text("几何图形组合", font_size=48).to_edge(UP)
        self.add(title)

        circle = Circle(radius=1.5, color=BLUE)
        square = Square(side_length=1.5, color=RED).shift(LEFT * 2.5)
        triangle = Triangle(color=GREEN).shift(RIGHT * 2.5)

        self.play(Create(circle))
        self.wait(0.5)
        self.play(Create(square))
        self.wait(0.5)
        self.play(Create(triangle))
        self.wait(1)

        self.play(
            circle.animate.set_fill(BLUE, opacity=0.3),
            square.animate.set_fill(RED, opacity=0.3),
            triangle.animate.set_fill(GREEN, opacity=0.3)
        )
        self.wait(1)

        label_c = Text("圆", font_size=36).next_to(circle, DOWN)
        label_s = Text("正方形", font_size=36).next_to(square, DOWN)
        label_t = Text("三角形", font_size=36).next_to(triangle, DOWN)

        self.play(Write(label_c), Write(label_s), Write(label_t))
        self.wait(2)

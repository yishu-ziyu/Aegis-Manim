from manim import *


class Demo3_FunctionGraph(Scene):
    def construct(self):
        title = Text("函数图像：y = x^2", font_size=48).to_edge(UP)
        self.add(title)

        axes = Axes(
            x_range=[-3, 3, 1],
            y_range=[0, 9, 2],
            x_length=6,
            y_length=5,
            axis_config={"include_tip": True}
        )

        self.play(Create(axes))
        self.wait(0.5)

        parabola = axes.plot(lambda x: x**2, x_range=[-3, 3], color=YELLOW)
        self.play(Create(parabola))
        self.wait(1)

        dot = Dot(color=RED).move_to(axes.c2p(1, 1))
        label = Text("(1, 1)", font_size=24).next_to(dot, RIGHT)
        self.play(FadeIn(dot), Write(label))
        self.wait(2)

        self.play(
            parabola.animate.set_color(ORANGE),
            run_time=2
        )
        self.wait(2)

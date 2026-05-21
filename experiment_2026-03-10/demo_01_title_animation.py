from manim import *


class Demo1_TitleAnimation(Scene):
    def construct(self):
        title = Text("欢迎学习", font_size=60)
        subtitle = Text("数学之美：函数与图像", font_size=36, color=BLUE)

        self.play(Write(title))
        self.wait(0.5)
        self.play(FadeIn(subtitle, shift=UP))
        self.wait(1)

        self.play(title.animate.scale(0.5).to_edge(UP), subtitle.animate.to_edge(DOWN))
        self.wait(2)

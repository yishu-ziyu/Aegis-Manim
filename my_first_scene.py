from manim import *

class HelloManim(Scene):
    def construct(self):
        # 1. 创建文本
        # Text allows simple text using available fonts
        text = Text("Hello, Manim!", font_size=48)
        
        # 2. 创建一个正方形
        # Mobjects are the basic building blocks
        square = Square()
        square.set_fill(BLUE, opacity=0.5)  # Set color and opacity
        square.next_to(text, DOWN)  # Position relative to text
        
        # 3. 播放入场动画
        self.play(Write(text))  # Write animation for text
        self.play(DrawBorderThenFill(square))  # Fancy creation for square
        self.wait(1)  # Pause for 1 second
        
        # 4. 变换动画 (Transform)
        circle = Circle()
        circle.set_fill(RED, opacity=0.5)
        circle.next_to(text, DOWN)
        
        # Transform square into circle
        self.play(Transform(square, circle))
        self.wait(0.5)
        
        # 5. 退场动画
        self.play(FadeOut(text), FadeOut(square))

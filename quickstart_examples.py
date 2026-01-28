from manim import *

class SquareAndCircle(Scene):
    def construct(self):
        circle = Circle() # create a circle
        circle.set_fill(PINK, opacity=0.5) # set the color and transparency

        square = Square() # create a square
        square.set_fill(BLUE, opacity=0.5) # set the color and transparency

        # positioned to the right of the circle with a buffer
        square.next_to(circle, RIGHT, buff=0.5) # set the position

        self.play(Create(circle), Create(square)) # show the shapes on screen
        self.wait()

class AnimatedSquareToCircle(Scene):
    def construct(self):
        circle = Circle() # create a circle
        square = Square() # create a square

        self.play(Create(square)) # show the square on screen
        self.play(square.animate.rotate(PI / 4)) # rotate the square
        self.play(Transform(square, circle)) # transform the square into a circle
        
        # color the circle on screen
        # Note: We use .animate here to animate the change of a property
        self.play(
            square.animate.set_fill(PINK, opacity=0.5)
        ) 
        self.wait()

class DifferentRotations(Scene):
    def construct(self):
        left_square = Square(color=BLUE, fill_opacity=0.7).shift(2 * LEFT)
        right_square = Square(color=GREEN, fill_opacity=0.7).shift(2 * RIGHT)

        self.play(
            # .animate interpolation: Manim tries to interpolate between start and end states.
            # For 180 degree rotation, start and end look the same, so it might shrink weirdly.
            left_square.animate.rotate(PI), 
            
            # Rotate method: Explicitly handles the rotation path.
            Rotate(right_square, angle=PI), 
            
            run_time=2
        )
        self.wait()

class TwoTransforms(Scene):
    def transform(self):
        a = Circle()
        b = Square()
        c = Triangle()
        self.play(Transform(a, b))
        self.play(Transform(a, c))
        self.play(FadeOut(a))

    def replacement_transform(self):
        a = Circle()
        b = Square()
        c = Triangle()
        self.play(ReplacementTransform(a, b))
        self.play(ReplacementTransform(b, c))
        self.play(FadeOut(c))

    def construct(self):
        self.transform()
        self.wait(0.5)  # wait for 0.5 seconds
        self.replacement_transform()

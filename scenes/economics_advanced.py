from manim import *

class ProductionPossibilityFrontier(Scene):
    def construct(self):
        # 1. Setup Axes
        axes = Axes(
            x_range=[0, 10, 1],
            y_range=[0, 10, 1],
            x_length=6,
            y_length=6,
            axis_config={"include_numbers": False, "tip_shape": ArrowTriangleFilledTip},
        )
        labels = axes.get_axis_labels(
            x_label=Text("Guns", font_size=24), 
            y_label=Text("Butter", font_size=24)
        )

        # 2. Draw PPF Curve (Concave)
        # Equation: x^2 + y^2 = 100 (Quarter circle usually, but let's make it concave)
        # y = sqrt(100 - x^2)
        ppf_curve = axes.plot(lambda x: (100 - x**2)**0.5, x_range=[0, 10], color=BLUE)
        ppf_label = axes.get_graph_label(ppf_curve, Text("PPF", font_size=24), x_val=2)

        # 3. Points
        # Efficient (On curve)
        pt_efficient = Dot(axes.c2p(6, 8), color=GREEN)
        lbl_efficient = Text("Efficient", font_size=20, color=GREEN).next_to(pt_efficient, UP+RIGHT)

        # Inefficient (Inside)
        pt_inefficient = Dot(axes.c2p(3, 4), color=YELLOW)
        lbl_inefficient = Text("Inefficient", font_size=20, color=YELLOW).next_to(pt_inefficient, DOWN)

        # Impossible (Outside)
        pt_impossible = Dot(axes.c2p(8, 8), color=RED)
        lbl_impossible = Text("Impossible", font_size=20, color=RED).next_to(pt_impossible, UP)

        # 4. Animation
        self.play(Create(axes), Write(labels))
        self.play(Create(ppf_curve), Write(ppf_label))
        self.wait(0.5)
        
        self.play(FadeIn(pt_efficient), Write(lbl_efficient))
        self.wait(0.5)
        self.play(FadeIn(pt_inefficient), Write(lbl_inefficient))
        self.wait(0.5)
        self.play(FadeIn(pt_impossible), Write(lbl_impossible))
        self.wait(2)


class UtilityMaximization(Scene):
    def construct(self):
        # 1. Setup Axes
        axes = Axes(
            x_range=[0, 10, 1],
            y_range=[0, 10, 1],
            x_length=6,
            y_length=6,
            axis_config={"include_numbers": False, "tip_shape": ArrowTriangleFilledTip},
        )
        labels = axes.get_axis_labels(
            x_label=Text("Good X", font_size=24), 
            y_label=Text("Good Y", font_size=24)
        )

        # 2. Budget Constraint: 2x + y = 10 => y = 10 - 2x
        budget_line = axes.plot(lambda x: 10 - 2*x, x_range=[0, 5], color=GREEN)
        budget_label = axes.get_graph_label(budget_line, Text("Budget", font_size=20), x_val=0.5)

        # 3. Indifference Curves (Utility = x * y)
        # y = U / x
        # Optimal point? MRS = Px/Py. y/x = 2 => y = 2x.
        # Substitute into budget: 2x + 2x = 10 => 4x = 10 => x = 2.5
        # y = 5. Utility = 12.5.
        
        # IC1 (Lower Utility, U=8) => y=8/x
        ic1 = axes.plot(lambda x: 8/x, x_range=[1, 8], color=BLUE_C)
        
        # IC2 (Optimal Utility, U=12.5) => y=12.5/x
        ic2 = axes.plot(lambda x: 12.5/x, x_range=[1.5, 8], color=BLUE)
        ic2_label = axes.get_graph_label(ic2, Text("U_max", font_size=20), x_val=8)

        # IC3 (Higher Utility, U=18) => y=18/x
        ic3 = axes.plot(lambda x: 18/x, x_range=[2, 9], color=BLUE_A)

        # 4. Tangency Point
        opt_point = Dot(axes.c2p(2.5, 5), color=YELLOW)
        opt_label = Text("Optimal", font_size=20).next_to(opt_point, UP+RIGHT)

        # 5. Animation
        self.play(Create(axes), Write(labels))
        self.play(Create(budget_line), Write(budget_label))
        self.wait(0.5)

        self.play(Create(ic1), run_time=1) # Too low
        self.play(Create(ic3), run_time=1) # Too high (unaffordable)
        self.wait(0.5)
        
        self.play(Create(ic2), Write(ic2_label), run_time=1.5) # Just right
        self.play(FadeIn(opt_point), Write(opt_label))
        
        # Flash to emphasize tangency
        self.play(Indicate(opt_point, scale_factor=1.5, color=YELLOW))
        self.wait(2)


class LafferCurve(Scene):
    def construct(self):
        # 1. Setup Axes
        axes = Axes(
            x_range=[0, 100, 10],
            y_range=[0, 100, 10],
            x_length=6,
            y_length=5,
            axis_config={"include_numbers": False, "tip_shape": ArrowTriangleFilledTip},
        )
        labels = axes.get_axis_labels(
            x_label=Text("Tax Rate (%)", font_size=24), 
            y_label=Text("Tax Revenue", font_size=24)
        )

        # 2. Curve: R = T * (100 - T) (Parabola)
        # Peak at T=50. Max R = 2500. Scale to fit 0-100 y-range.
        # Let y = (x * (100 - x)) / 25
        laffer_func = lambda x: (x * (100 - x)) / 25
        curve = axes.plot(laffer_func, x_range=[0, 100], color=GOLD)
        
        # 3. Peak Point
        peak_point = Dot(axes.c2p(50, 100), color=RED)
        peak_label = Text("Max Revenue", font_size=20).next_to(peak_point, UP)
        
        # Dashed line to x-axis (Optimal Rate)
        v_line = axes.get_vertical_line(axes.c2p(50, 100), line_config={"dashed_ratio": 0.5})
        opt_rate_label = Text("Optimal Rate", font_size=20).next_to(v_line, DOWN)

        # 4. Animation
        self.play(Create(axes), Write(labels))
        self.play(Create(curve), run_time=2)
        self.wait(0.5)
        
        self.play(FadeIn(peak_point), Write(peak_label))
        self.play(Create(v_line))
        self.play(Write(opt_rate_label))
        
        self.wait(2)

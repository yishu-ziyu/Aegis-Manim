from manim import *

class SupplyDemandScene(Scene):
    def construct(self):
        # 1. Setup Axes
        axes = Axes(
            x_range=[0, 12, 1],
            y_range=[0, 10, 1],
            x_length=7,
            y_length=6,
            axis_config={"include_numbers": False, "tip_shape": ArrowTriangleFilledTip},
            x_axis_config={"numbers_to_include": []},
            y_axis_config={"numbers_to_include": []},
        )
        labels = axes.get_axis_labels(
            x_label=Text("Quantity (Q)", font_size=24), 
            y_label=Text("Price (P)", font_size=24)
        )

        # 2. Define Functions for Curves
        # Demand: P = 10 - Q
        def demand_func(x):
            return 10 - x
        
        # Supply: P = 2 + Q
        def supply_func(x):
            return 2 + x

        # 3. Create Curves
        demand_curve = axes.plot(demand_func, color=BLUE, x_range=[0, 10])
        demand_label = axes.get_graph_label(
            demand_curve, Text("Demand (D)", font_size=20), x_val=9, direction=RIGHT
        )

        supply_curve = axes.plot(supply_func, color=RED, x_range=[0, 8])
        supply_label = axes.get_graph_label(
            supply_curve, Text("Supply (S)", font_size=20), x_val=7.5, direction=RIGHT
        )

        # 4. Equilibrium Point calculation
        # 10 - Q = 2 + Q => 8 = 2Q => Q* = 4
        # P* = 10 - 4 = 6
        equilibrium_q = 4
        equilibrium_p = 6
        
        # Point on graph coordinates
        eq_point_coords = axes.coords_to_point(equilibrium_q, equilibrium_p)
        eq_dot = Dot(eq_point_coords, color=YELLOW)
        eq_label = Text("E", font_size=24).next_to(eq_dot, UP + RIGHT, buff=0.1)

        # Dashed lines to axes
        h_line = axes.get_horizontal_line(eq_point_coords, line_config={"dashed_ratio": 0.5})
        v_line = axes.get_vertical_line(eq_point_coords, line_config={"dashed_ratio": 0.5})
        
        p_label = axes.get_y_axis_label(Text("P*", font_size=24), edge=LEFT, direction=LEFT, buff=0.1)
        p_label.move_to(axes.c2p(0, equilibrium_p) + LEFT * 0.5)
        
        q_label = axes.get_x_axis_label(Text("Q*", font_size=24), edge=DOWN, direction=DOWN, buff=0.1)
        q_label.move_to(axes.c2p(equilibrium_q, 0) + DOWN * 0.5)


        # --- Animation Sequence ---
        
        # Draw Axes
        self.play(Create(axes), Write(labels))
        self.wait(0.5)

        # Draw Curves
        self.play(Create(demand_curve), Write(demand_label))
        self.play(Create(supply_curve), Write(supply_label))
        self.wait(0.5)

        # Show Equilibrium
        self.play(Create(h_line), Create(v_line))
        self.play(FadeIn(eq_dot, scale=0.5), Write(eq_label))
        self.play(Write(p_label), Write(q_label))
        self.wait(1)

        # Extension: Demand Shift
        # New Demand: P = 12 - Q (Shift Right)
        def new_demand_func(x):
            return 12 - x
        
        new_demand_curve = axes.plot(new_demand_func, color=BLUE_A, x_range=[2, 10])
        new_demand_label = axes.get_graph_label(
             new_demand_curve, Text("D'", font_size=20), x_val=10, direction=RIGHT
        )

        self.play(
            Transform(demand_curve, new_demand_curve),
            Transform(demand_label, new_demand_label),
            run_time=2
        )
        self.wait(1)
        
        # Show new equilibrium trace (Optional)
        # New Eq: 12 - Q = 2 + Q => 10 = 2Q => Q = 5, P = 7
        new_q = 5
        new_p = 7
        new_point_coords = axes.coords_to_point(new_q, new_p)
        
        # Create dashed lines for new equilibrium dynamically
        new_v_line = axes.get_vertical_line(new_point_coords, line_config={"dashed_ratio": 0.5})
        new_h_line = axes.get_horizontal_line(new_point_coords, line_config={"dashed_ratio": 0.5})
        
        self.play(
            h_line.animate.become(new_h_line),
            v_line.animate.become(new_v_line),
            eq_dot.animate.move_to(new_point_coords),
            eq_label.animate.next_to(new_point_coords, UP+RIGHT, buff=0.1)
        )
        self.wait(2)


class CostCurvesScene(Scene):
    def construct(self):
        # 1. Setup Axes
        axes = Axes(
            x_range=[0, 10, 1],
            y_range=[0, 20, 2],
            x_length=7,
            y_length=6,
            axis_config={"include_numbers": False},
        )
        labels = axes.get_axis_labels(
            x_label=Text("Output (Q)", font_size=24), 
            y_label=Text("Cost ($)", font_size=24)
        )

        # 2. Define Cost Functions
        # ATC = Q^2 - 8Q + 20 (Parabola opening up, vertex at Q=4, P=4)
        # However, typically ATC = TC/Q. Let's use a simple quadratic for visual representation.
        # Let's use: ATC = 0.5*(Q-5)^2 + 4
        # Min at Q=5, Cost=4
        def atc_func(q):
            return 0.5 * (q - 5)**2 + 4
        
        # MC curve usually cuts ATC at its minimum.
        # Let's construct an MC curve that passes through (5, 4).
        # And it should be steeper.
        # MC = (Q-5) + 4 = Q - 1 ? No, usually MC is also somewhat curved or linear upward.
        # Let's simplify: MC = Q - 1 (Linear) -> cuts if slope is right?
        # Let's try quadratic MC: MC = 0.8*(Q-5)^2 - something? 
        # Actually standard theory: If TC = aQ^3 + bQ^2 + cQ + d
        # MC = 3aQ^2 + 2bQ + c
        # ATC = aQ^2 + bQ + c + d/Q
        # Let's just fit a visual curve for "Sketchy" style.
        # MC passes through min of ATC (5, 4).
        # Let MC be a line passing (5,4) with positive slope. y - 4 = 2(x - 5) => y = 2x - 10 + 4 = 2x - 6.
        # Let's check ranges. at Q=8, ATC=0.5*9+4=8.5. MC=16-6=10. MC > ATC after intersect.
        # at Q=2, ATC=0.5*9+4=8.5. MC=4-6=-2 (Problem, negative cost).
        
        # Better visual functions:
        # ATC: 10/Q + 0.5Q (High at low Q, high at high Q)
        # Let's use: f(x) = (x-4)^2 + 3
        def atc_visual(x):
            return 0.5 * (x - 4)**2 + 3

        # MC must pass through (4, 3).
        # Let MC be steeper quadratic or linear.
        # Let MC = x - 1. At x=4, y=3. Correct.
        def mc_visual(x):
            return x - 1

        # 3. Create Plots
        atc_curve = axes.plot(atc_visual, color=GREEN, x_range=[1, 8])
        atc_label = axes.get_graph_label(atc_curve, Text("ATC", font_size=20), x_val=7.5)

        mc_curve = axes.plot(mc_visual, color=RED, x_range=[1, 8])
        mc_label = axes.get_graph_label(mc_curve, Text("MC", font_size=20), x_val=7.5)

        # Intersection Dot
        intersect_point = axes.coords_to_point(4, 3)
        dot = Dot(intersect_point, color=YELLOW)

        # 4. Animation
        self.play(Create(axes), Write(labels))
        
        self.play(Create(atc_curve), Write(atc_label), run_time=2)
        
        self.play(Create(mc_curve), Write(mc_label), run_time=2)
        
        # Highlight intersection
        self.play(FadeIn(dot, scale=0.5))
        self.play(Indicate(dot, scale_factor=1.5))
        
        note = Text("MC cuts ATC at min", font_size=24).next_to(dot, UP, buff=0.5)
        self.play(Write(note))
        
        self.wait(2)

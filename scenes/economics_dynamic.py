from manim import *
import numpy as np

class MicroOptimization(Scene):
    def construct(self):
        # --- 1. Setup Environment ---
        axes = Axes(
            x_range=[0, 10, 1], y_range=[0, 10, 1],
            x_length=6, y_length=6,
            axis_config={"include_numbers": False, "tip_shape": ArrowTriangleFilledTip}
        )
        labels = axes.get_axis_labels(x_label=Text("x1"), y_label=Text("x2"))
        self.add(axes, labels)

        # --- 2. Budget Constraint (The Wall) ---
        # P1*x1 + P2*x2 = I. Let's say x1 + x2 = 8 => x2 = 8 - x1
        # Normal Vector = (P1, P2) = (1, 1) direction
        budget_func = lambda x: 8 - x
        budget_line = axes.plot(budget_func, x_range=[0, 8], color=GREEN, stroke_width=4)
        budget_label = Text("Budget Constraint", font_size=20, color=GREEN).next_to(budget_line, UP+RIGHT)
        
        # Constraint Region (Feasible Set)
        region = axes.get_area(budget_line, x_range=[0, 8], color=GREEN, opacity=0.2)
        
        self.play(Create(budget_line), FadeIn(region), Write(budget_label))

        # --- 3. Indifference Curves (The Expansion) ---
        # Utility U = x1 * x2.  x2 = U / x1.
        # Gradients: (dU/dx1, dU/dx2) = (x2, x1).
        
        # We simulate a "Probe" point moving along the budget line
        # x1 goes from 1 to 7. Optimal is at x1=4, x2=4.
        t_tracker = ValueTracker(1.5) # Initial x1 position (suboptimal)

        # Dynamic Point
        def get_probe_coords():
            x1 = t_tracker.get_value()
            x2 = budget_func(x1)
            return axes.c2p(x1, x2)

        probe_dot = always_redraw(lambda: Dot(get_probe_coords(), color=YELLOW, radius=0.12))

        # Dynamic Indifference Curve passing through the probe
        def get_ic_graph():
            x1_current = t_tracker.get_value()
            x2_current = budget_func(x1_current)
            u_current = x1_current * x2_current
            # Plot x2 = u / x1
            return axes.plot(
                lambda x: u_current / x, 
                x_range=[0.5, 9.5], 
                color=BLUE_C
            )
        
        ic_curve = always_redraw(get_ic_graph)

        # --- 4. Gradient Engines (The Vectors) ---
        
        # Price Vector (Normal to Budget Line) - Fixed Direction (1, 1)
        # Normalized direction: (0.707, 0.707)
        price_vector = always_redraw(lambda: Arrow(
            start=get_probe_coords(),
            end=get_probe_coords() + np.array([0.5, 0.5, 0]) * 1.5, # Scale for visibility
            color=GREEN, buff=0, tip_length=0.2
        ))
        
        # Utility Gradient Vector (MRS direction)
        # Gradient of U=xy is (y, x). At (x1, x2), vector points (x2, x1).
        util_vector = always_redraw(lambda: Arrow(
            start=get_probe_coords(),
            end=get_probe_coords() + self.get_gradient_vec(t_tracker.get_value()) * 0.8, # Scale
            color=RED, buff=0, tip_length=0.2
        ))

        self.play(Create(ic_curve), FadeIn(probe_dot))
        self.play(GrowArrow(price_vector), GrowArrow(util_vector))
        
        # Labels for vectors
        p_vec_label = Text("Price Vec", font_size=16, color=GREEN).next_to(price_vector, UP)
        u_vec_label = Text("Gradient", font_size=16, color=RED).next_to(util_vector, RIGHT)
        # Hack to make labels follow (simplified, usually need always_redraw for position too)
        
        # --- 5. The Optimization Process ---
        
        # Step 1: Suboptimal (MRS != Price Ratio)
        self.wait(1)
        
        # Step 2: Slide towards optimum
        self.play(
            t_tracker.animate.set_value(4), # Optimal point (4, 4)
            run_time=4,
            rate_func=linear
        )
        
        # Step 3: Flash on Alignment
        # At x=4, y=4. Variance = (1/sqrt(2), 1/sqrt(2)) vs (4, 4)->(1,1). They align!
        # Flash the dot
        success_circle = Circle(radius=0.5, color=YELLOW).move_to(axes.c2p(4, 4))
        self.play(
            ShowPassingFlash(success_circle), 
            probe_dot.animate.scale(1.5).set_color(GREEN)
        )
        
        opt_text = Text("OPTIMAL!", font_size=36, color=YELLOW).next_to(probe_dot, UP+RIGHT)
        self.play(Write(opt_text))
        
        # Step 4: Overshoot to show divergence again
        self.play(t_tracker.animate.set_value(6.5), run_time=2)
        self.wait(1)

    def get_gradient_vec(self, x1):
        # U = x * (8-x). 
        # Actually gradient is (du/dx, du/dy) = (y, x). 
        # At (x1, 8-x1), gradient is (8-x1, x1).
        # We need to map this data vector to screen vector scaling
        x2 = 8 - x1
        
        # Normalize
        mag = np.sqrt(x2**2 + x1**2)
        v_x = (x2 / mag) 
        v_y = (x1 / mag)
        
        # Manim Axes scaling usually matches, but let's be safe visually
        return np.array([v_x, v_y, 0])


class MacroSaddlePath(Scene):
    def construct(self):
        # --- 1. Vector Field (The Flow) ---
        axes = Axes(
            x_range=[0, 6, 1], y_range=[0, 6, 1],
            x_length=6, y_length=6,
            axis_config={"include_numbers": False, "tip_shape": ArrowTriangleFilledTip}
        )
        labels = axes.get_axis_labels(x_label=Text("Capital (k)"), y_label=Text("Consumption (c)"))
        
        # Differential Eq: Simple Saddle Point at (3, 3)
        # dk/dt = c - 3
        # dc/dt = k - 3
        # Eigenvalues: lambda^2 - 1 = 0 => lambda = 1, -1. Saddle!
        # Eigenvectors: v1=(1,1) [Unstable], v2=(1,-1) [Stable/Saddle Path]
        
        def vector_field_func(pos):
            # pos is [x, y, z] in manim coordinates
            # We need to map back to axes coords if scaling is different, 
            # but here axes roughly map to units. Let's simplify and use axes.p2c
            c_point = axes.p2c(pos)
            k, c = c_point[0], c_point[1]
            
            dk = k - 3
            dc = c - 3 # This is actually a source/sink? Wait.
            # Stable manifold is y = x (if both positive). 
            # Let's use: dk = k - 3, dc = 3 - c -> Stable at k=3, c=3?
            # Let's use standard Ramsey linearized:
            # dk = k - 3
            # dc = c - 3  -> If k>3, k grows. If c>3, c grows. Source (Unstable node)?
            # We want Saddle.
            # dk = c - 3
            # dc = k - 3
            # Jacobian = [[0, 1], [1, 0]]. Det = -1. Saddle! 
            # Evals: 1, -1.
            # Evecs: (1,1) for 1 (Unstable manifold y=x), (1,-1) for -1 (Stable manifold y = -x + 6).
            
            dk = c - 3
            dc = k - 3
            
            # Map back to vector
            return np.array([dk, dc, 0])

        vector_field = ArrowVectorField(
            lambda pos: vector_field_func(pos) * 0.5, # Scale down arrows
            x_range=[0, 6], y_range=[0, 6],
            colors=[BLUE_C, BLUE_E, RED]
        )
        
        self.add(axes, labels)
        self.play(Create(vector_field), run_time=2)
        
        # --- 2. Nullclines and Steady State ---
        # dk=0 => c=3. dc=0 => k=3.
        start_k = axes.c2p(0, 3)
        end_k = axes.c2p(6, 3)
        null_k = DashedLine(start_k, end_k, color=GREY)

        start_c = axes.c2p(3, 0)
        end_c = axes.c2p(3, 6)
        null_c = DashedLine(start_c, end_c, color=GREY)
        
        ss_dot = Dot(axes.c2p(3, 3), color=WHITE)
        ss_label = Text("Steady State", font_size=20).next_to(ss_dot, UP+RIGHT)
        
        self.play(Create(null_k), Create(null_c))
        self.play(FadeIn(ss_dot), Write(ss_label))

        # --- 3. The Saddle Path (Stable Manifold) ---
        # For this system, stable manifold corresponds to eigenvalue -1 -> vector (1, -1). 
        # Line passing through (3,3) with slope -1: c - 3 = -1(k - 3) => c = 6 - k.
        
        saddle_path = axes.plot(lambda k: 6 - k, x_range=[0, 6], color=GREEN, stroke_width=4)
        saddle_label = Text("Saddle Path", font_size=20, color=GREEN).next_to(saddle_path.get_start(), RIGHT)
        
        self.play(Create(saddle_path), Write(saddle_label))
        self.wait(1)

        # --- 4. Particle Simulation (The Balance) ---
        
        # Case 1: Too High (Consumption Overshoot)
        # Start at k=1. Saddle c should be 5. Let's pick c=5.5
        p1 = Dot(axes.c2p(1, 4), color=RED) # Below saddle path? 6-1=5. 4 is below.
        # Flow logic:
        # At (1, 4): dk = 4-3=1 (>0), dc = 1-3=-2 (<0). k increases, c decreases.
        # Wait, eigenvecs (1,1) unstable -> slope 1. (1,-1) stable -> slope -1.
        # If we are below slope -1 line, do we crash? 
        # Let's just animate TracePath
        
        path_diverge = TracedPath(p1.get_center, stroke_color=RED, stroke_width=3)
        self.add(p1, path_diverge)
        
        # Animate p1 moving along field
        # We manually simulate a simplified path for visualization instead of real ODE solving
        # It goes south-east
        self.play(p1.animate.move_to(axes.c2p(5, 0.5)), run_time=3)
        crash_text = Text("Capital Accumulation (Crash)", font_size=16, color=RED).next_to(p1, RIGHT)
        self.play(Write(crash_text))
        self.wait(1)
        self.play(FadeOut(p1), FadeOut(path_diverge), FadeOut(crash_text))
        
        # Case 2: The Perfect Balance
        p_optimal = Dot(axes.c2p(0.5, 5.5), color=GREEN) # On line c=6-k
        path_optimal = TracedPath(p_optimal.get_center, stroke_color=GREEN, stroke_width=3)
        self.add(p_optimal, path_optimal)
        
        # It should glide to (3,3)
        self.play(p_optimal.animate.move_to(axes.c2p(3, 3)), run_time=4, rate_func=rate_functions.ease_out_quad)
        
        success_text = Text("Convergence!", font_size=24, color=GREEN).next_to(ss_dot, UP)
        self.play(Write(success_text))
        self.wait(2)


class SurplusDynamics(Scene):
    def construct(self):
        # --- 1. Setup Environment ---
        axes = Axes(
            x_range=[0, 10, 1], y_range=[0, 10, 1],
            x_length=6, y_length=6,
            axis_config={"include_numbers": False, "tip_shape": ArrowTriangleFilledTip}
        )
        labels = axes.get_axis_labels(x_label=Text("Quantity (Q)"), y_label=Text("Price (P)"))
        self.add(axes, labels)

        # --- 2. Dynamic Parameters ---
        # Demand: P = a - bQ
        # Supply: P = c + dQ
        a = ValueTracker(8) # Demand Intercept
        b = 1               # Demand Slope (Fixed)
        c = ValueTracker(2) # Supply Intercept
        d = 1               # Supply Slope (Fixed)

        # Helper to get equilibrium
        def get_eq():
            # a - bQ = c + dQ => Q(b+d) = a - c
            q_star = (a.get_value() - c.get_value()) / (b + d)
            p_star = a.get_value() - b * q_star
            return q_star, p_star

        # --- 3. Dynamic Visuals ---
        
        # Curves
        demand_curve = always_redraw(lambda: axes.plot(
            lambda q: a.get_value() - b * q, 
            x_range=[0, 10], color=BLUE
        ))
        
        supply_curve = always_redraw(lambda: axes.plot(
            lambda q: c.get_value() + d * q, 
            x_range=[0, 10], color=RED
        ))

        # Equilibrium Dot & Dashed Lines
        def get_eq_group():
            q, p = get_eq()
            # Clamp for safety if needed, but logic holds for positive ranges
            point = axes.c2p(q, p)
            
            dot = Dot(point, color=WHITE)
            
            line_h = DashedLine(axes.c2p(0, p), point, color=GREY)
            line_v = DashedLine(axes.c2p(q, 0), point, color=GREY)
            
            lbl_p = Text(f"P*={p:.1f}", font_size=16).next_to(axes.c2p(0, p), LEFT)
            lbl_q = Text(f"Q*={q:.1f}", font_size=16).next_to(axes.c2p(q, 0), DOWN)
            
            return VGroup(dot, line_h, line_v, lbl_p, lbl_q)

        eq_group = always_redraw(get_eq_group)

        # Surplus Areas (Polygons)
        # CS: Triangle (0, a), (Q*, P*), (0, P*)
        def get_cs_area():
            q, p = get_eq()
            p_intercept = a.get_value()
            
            points = [
                axes.c2p(0, p_intercept), # Top Left
                axes.c2p(q, p),           # Eq Point
                axes.c2p(0, p)            # Bottom Left
            ]
            return Polygon(*points, color=BLUE, fill_opacity=0.3, stroke_width=0)

        # PS: Triangle (0, c), (Q*, P*), (0, P*)
        def get_ps_area():
            q, p = get_eq()
            p_intercept = c.get_value()
            
            points = [
                axes.c2p(0, p_intercept), # Bottom Left
                axes.c2p(q, p),           # Eq Point
                axes.c2p(0, p)            # Top Left
            ]
            return Polygon(*points, color=RED, fill_opacity=0.3, stroke_width=0)
            
        cs_poly = always_redraw(get_cs_area)
        ps_poly = always_redraw(get_ps_area)
        
        # Labels for Areas
        cs_label = always_redraw(lambda: Text("CS", font_size=20, color=BLUE).move_to(
            axes.c2p(get_eq()[0]/3, (a.get_value() + get_eq()[1])/2) 
            # Simple heuristic position
        ))
        
        ps_label = always_redraw(lambda: Text("PS", font_size=20, color=RED).move_to(
            axes.c2p(get_eq()[0]/3, (c.get_value() + get_eq()[1])/2)
        ))

        # --- 4. Animation Sequence ---
        self.play(Create(axes), Write(labels))
        self.play(Create(demand_curve), Create(supply_curve))
        self.play(FadeIn(cs_poly), FadeIn(ps_poly))
        self.play(FadeIn(eq_group), Write(cs_label), Write(ps_label))
        self.wait(1)

        # Action: Demand Shock (Increase Demand)
        # a increases from 8 to 9.5
        shock_text = Text("Demand Shift (a: 8 -> 9.5)", font_size=24).to_edge(UP)
        self.play(Write(shock_text))
        
        self.play(
            a.animate.set_value(9.5),
            run_time=3,
            rate_func=linear
        )
        self.wait(1)
        
        # Action: Supply Shock (Decrease Supply / Cost Increase)
        # c increases from 2 to 3.5
        shock_text_2 = Text("Supply Shift (c: 2 -> 3.5)", font_size=24).to_edge(UP)
        self.play(Transform(shock_text, shock_text_2))
        
        self.play(
            c.animate.set_value(3.5),
            run_time=3,
            rate_func=linear
        )
        
        self.wait(2)


class TaxWelfareScene(Scene):
    def construct(self):
        # 1. Setup Environment
        axes = Axes(
            x_range=[0, 10, 1], y_range=[0, 10, 1],
            x_length=6, y_length=6,
            axis_config={"include_numbers": False, "tip_shape": ArrowTriangleFilledTip}
        )
        labels = axes.get_axis_labels(x_label=Text("Quantity (Q)"), y_label=Text("Price (P)"))
        self.add(axes, labels)

        # 2. Parameters
        # Demand: P = 9 - Q
        # Supply: P = 1 + Q
        # Initial Eq: 9-Q = 1+Q => 2Q=8 => Q=4, P=5
        a, b = 9, 1
        c, d = 1, 1
        
        # Tax Tracker (T)
        tax = ValueTracker(0)

        # Helper to get current state
        def get_state():
            t = tax.get_value()
            # New Equilibrium: Demand Price = Supply Price + Tax
            # a - bQ = (c + dQ) + t
            # a - c - t = Q(b+d)
            q_new = (a - c - t) / (b + d)
            p_consumer = a - b * q_new
            p_producer = c + d * q_new # or p_consumer - t
            return q_new, p_consumer, p_producer

        # 3. Visuals
        
        # Static Base Curves
        demand_curve = axes.plot(lambda q: a - b*q, x_range=[0, 9], color=BLUE)
        supply_curve = axes.plot(lambda q: c + d*q, x_range=[0, 9], color=GREY, stroke_opacity=0.5)
        
        # Dynamic Effective Supply Curve (S + Tax)
        eff_supply_curve = always_redraw(lambda: axes.plot(
            lambda q: c + d*q + tax.get_value(),
            x_range=[0, 9], color=RED
        ))
        
        # Indicators
        def get_indicators():
            q, pc, pp = get_state()
            pt_c = axes.c2p(q, pc)
            pt_p = axes.c2p(q, pp)
            
            # The Wedge Line
            wedge = Line(pt_c, pt_p, color=YELLOW, stroke_width=4)
            
            # Dashed Projections
            dash_c = DashedLine(axes.c2p(0, pc), pt_c, color=BLUE)
            dash_p = DashedLine(axes.c2p(0, pp), pt_p, color=RED)
            dash_q = DashedLine(axes.c2p(q, 0), pt_p, color=WHITE) # From bottom point down
            
            # Labels
            lbl_pc = Text(f"Pc={pc:.1f}", font_size=16, color=BLUE).next_to(axes.c2p(0, pc), LEFT)
            lbl_pp = Text(f"Pp={pp:.1f}", font_size=16, color=RED).next_to(axes.c2p(0, pp), LEFT)
            
            return VGroup(wedge, dash_c, dash_p, dash_q, lbl_pc, lbl_pp)
            
        indicators = always_redraw(get_indicators)

        # Areas (DWL & Revenue)
        
        # Deadweight Loss Triangle
        # Vertices: (Q_new, Pc), (Q_new, Pp), (Q_old, P_old)
        # Q_old = 4, P_old = 5
        def get_dwl():
            q, pc, pp = get_state()
            q_old, p_old = 4, 5
            
            points = [
                axes.c2p(q, pc),
                axes.c2p(q, pp),
                axes.c2p(q_old, p_old)
            ]
            return Polygon(*points, color=GREY, fill_opacity=0.5, stroke_width=0)
            
        dwl_poly = always_redraw(get_dwl)
        
        # Tax Revenue Rectangle
        # (0, Pc) -> (Q, Pc) -> (Q, Pp) -> (0, Pp)
        def get_revenue():
            q, pc, pp = get_state()
            points = [
                axes.c2p(0, pc),
                axes.c2p(q, pc),
                axes.c2p(q, pp),
                axes.c2p(0, pp)
            ]
            return Polygon(*points, color=GREEN, fill_opacity=0.3, stroke_width=0)
            
        revenue_poly = always_redraw(get_revenue)
        
        # Text Labels for Areas
        dwl_text = always_redraw(lambda: Text("DWL", font_size=16, color=WHITE).move_to(
            axes.c2p(
                (get_state()[0] + 4)/2 + 0.3, # Slightly right of center of Q space
                5 # Center P
            )
        ))
        
        rev_text = always_redraw(lambda: Text("Tax Revenue", font_size=20, color=GREEN).move_to(
            axes.c2p(get_state()[0]/2, (get_state()[1] + get_state()[2])/2)
        ))

        # 4. Animation
        self.play(Create(axes), Write(labels))
        self.play(Create(demand_curve), Create(supply_curve))
        self.wait(1)
        
        # Introduce Tax
        self.play(Create(eff_supply_curve))
        self.play(FadeIn(indicators))
        self.play(FadeIn(dwl_poly), FadeIn(revenue_poly))
        self.play(Write(dwl_text), Write(rev_text))
        
        # Animate Tax Increase (T: 0 -> 3)
        self.play(
            tax.animate.set_value(3),
            run_time=4,
            rate_func=linear
        )
        self.wait(1)
        
        # Decrease back
        self.play(
            tax.animate.set_value(1),
            run_time=2
        )
        self.wait(2)



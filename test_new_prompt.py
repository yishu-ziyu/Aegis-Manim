from manim import *

class GeneratedScene(Scene):
    def construct(self):
        # Scene plan:
        # 1. Hook with a concrete market: show a coffee stall and buyers, then add more buyers.
        # 2. Bridge to the abstract supply-demand graph using color continuity.
        # 3. Show the initial equilibrium as the intersection of demand and supply.
        # 4. Increase demand by shifting the demand curve right and reveal the new equilibrium.
        # 5. Highlight the insight: both equilibrium price and quantity rise.
        # 6. End with a clean summary image.

        self.camera.background_color = BLACK

        def make_person(color=BLUE):
            head = Circle(radius=0.16, color=color, stroke_width=2).set_fill(color, opacity=0.25)
            body = RoundedRectangle(
                corner_radius=0.08,
                width=0.28,
                height=0.42,
                color=color,
                stroke_width=2,
            ).set_fill(color, opacity=0.18)
            body.next_to(head, DOWN, buff=0.02)
            return VGroup(head, body)

        title = Text("供需均衡", font_size=38, color=WHITE).to_edge(UP)
        self.play(Write(title))
        self.wait(0.8)

        # === Section 1: Hook ===
        coffee_card = RoundedRectangle(
            corner_radius=0.18,
            width=2.0,
            height=1.2,
            color=YELLOW,
            stroke_width=3,
        ).set_fill(YELLOW, opacity=0.12)
        coffee_text = Text("咖啡", font_size=26, color=YELLOW).move_to(coffee_card.get_center())
        coffee_group = VGroup(coffee_card, coffee_text).move_to(ORIGIN + UP * 0.2)

        buyers = VGroup(*[make_person(BLUE) for _ in range(3)]).arrange(RIGHT, buff=0.22)
        buyers.move_to(LEFT * 4 + DOWN * 1.3)

        stall_base = Rectangle(width=1.4, height=0.9, color=GREEN, stroke_width=3).set_fill(GREEN, opacity=0.12)
        stall_roof = Polygon(
            LEFT * 0.85 + UP * 0.45,
            RIGHT * 0.85 + UP * 0.45,
            RIGHT * 0.55 + UP * 0.85,
            LEFT * 0.55 + UP * 0.85,
            color=GREEN,
            stroke_width=3,
        ).set_fill(GREEN, opacity=0.15)
        stall_text = Text("店家", font_size=22, color=GREEN).move_to(stall_base.get_center())
        seller_group = VGroup(stall_base, stall_roof, stall_text).move_to(RIGHT * 4 + DOWN * 1.2)

        hook_text = VGroup(
            Text("人忽然多", font_size=24, color=RED),
            Text("会怎样", font_size=24, color=YELLOW),
        ).arrange(DOWN, buff=0.12).to_edge(DOWN)

        self.play(
            LaggedStart(
                Create(coffee_card),
                Write(coffee_text),
                FadeIn(buyers, shift=UP),
                FadeIn(seller_group, shift=UP),
                lag_ratio=0.18,
            ),
            run_time=2.5,
        )
        self.wait(1.0)

        self.play(Write(hook_text))
        self.wait(1.8)

        extra_buyers = VGroup(*[make_person(BLUE) for _ in range(2)]).arrange(RIGHT, buff=0.22)
        extra_buyers.next_to(buyers, RIGHT, buff=0.25)

        self.play(FadeIn(extra_buyers, shift=RIGHT), run_time=1.2)
        self.wait(0.8)

        self.play(Indicate(coffee_group, scale_factor=1.08), run_time=1.0)
        self.wait(0.8)

        # === Section 2: Setup ===
        bridge_text = Text("画成曲线", font_size=24, color=WHITE).to_edge(DOWN)

        self.play(ReplacementTransform(hook_text, bridge_text), run_time=1.0)
        self.wait(0.8)

        concrete_group = VGroup(coffee_group, buyers, extra_buyers, seller_group)

        axes = Axes(
            x_range=[0, 10, 2],
            y_range=[0, 10, 2],
            x_length=7.2,
            y_length=5.2,
            axis_config={"include_numbers": False, "color": GREY},
        ).shift(DOWN * 0.15)
        axes.set_opacity(0.35)

        x_label = Text("数量 Q", font_size=22, color=GREY)
        y_label = Text("价格 P", font_size=22, color=GREY)
        axis_labels = axes.get_axis_labels(x_label=x_label, y_label=y_label)

        self.play(Create(axes), Write(axis_labels), run_time=2.0)
        self.wait(1.0)

        demand_label = Text("需求", font_size=24, color=BLUE).move_to(axes.c2p(1.0, 8.5) + LEFT * 0.6)
        supply_label = Text("供给", font_size=24, color=GREEN).move_to(axes.c2p(8.6, 7.4) + RIGHT * 0.5)

        self.play(
            TransformFromCopy(VGroup(buyers, extra_buyers), demand_label),
            TransformFromCopy(seller_group, supply_label),
            run_time=1.8,
        )
        self.wait(1.0)

        self.play(FadeOut(concrete_group, shift=DOWN), run_time=1.0)
        self.wait(0.8)

        demand_curve = axes.plot(
            lambda x: 8 - 0.6 * x,
            x_range=[1, 9],
            color=BLUE,
            stroke_width=5,
        )
        supply_curve = axes.plot(
            lambda x: 1.5 + 0.6 * x,
            x_range=[1, 9],
            color=GREEN,
            stroke_width=5,
        )

        curve_text = VGroup(
            Text("蓝是需求", font_size=22, color=BLUE),
            Text("绿是供给", font_size=22, color=GREEN),
        ).arrange(DOWN, buff=0.12).to_edge(DOWN)

        self.play(Create(demand_curve), Create(supply_curve), run_time=2.2)
        self.wait(1.0)

        self.play(ReplacementTransform(bridge_text, curve_text), run_time=1.0)
        self.wait(1.2)

        # === Section 3: Initial equilibrium ===
        eq0_x = 5.4167
        eq0_y = 4.75

        eq0_dot = Dot(axes.c2p(eq0_x, eq0_y), color=YELLOW, radius=0.08)
        eq0_h = DashedLine(axes.c2p(0, eq0_y), axes.c2p(eq0_x, eq0_y), color=YELLOW, stroke_opacity=0.75)
        eq0_v = DashedLine(axes.c2p(eq0_x, 0), axes.c2p(eq0_x, eq0_y), color=YELLOW, stroke_opacity=0.75)
        p0_label = Text("P0", font_size=20, color=YELLOW).next_to(axes.c2p(0, eq0_y), LEFT, buff=0.15)
        q0_label = Text("Q0", font_size=20, color=YELLOW).next_to(axes.c2p(eq0_x, 0), DOWN, buff=0.15)
        e0_label = Text("E0", font_size=20, color=YELLOW).next_to(eq0_dot, UR, buff=0.12)
        eq0_group = VGroup(eq0_h, eq0_v, eq0_dot, p0_label, q0_label, e0_label)

        eq_text = Text("交点是均衡", font_size=24, color=YELLOW).to_edge(DOWN)

        self.play(ReplacementTransform(curve_text, eq_text), run_time=1.0)
        self.wait(0.8)

        self.play(Create(eq0_group), run_time=2.0)
        self.wait(1.0)

        self.play(Circumscribe(eq0_dot, color=YELLOW, run_time=1.2))
        self.wait(1.0)

        # === Section 4: Demand increase ===
        demand_up_text = VGroup(
            Text("需求增加", font_size=24, color=ORANGE),
            Text("曲线右移", font_size=24, color=ORANGE),
        ).arrange(DOWN, buff=0.12).to_edge(DOWN)

        self.play(ReplacementTransform(eq_text, demand_up_text), run_time=1.0)
        self.wait(1.0)

        self.play(
            demand_curve.animate.set_color(GREY).set_opacity(0.45),
            eq0_group.animate.set_opacity(0.4),
            run_time=1.0,
        )
        self.wait(0.8)

        new_demand_curve = axes.plot(
            lambda x: 9 - 0.6 * x,
            x_range=[1, 9],
            color=BLUE,
            stroke_width=5,
        )
        new_demand_label = Text("需求+", font_size=24, color=BLUE).move_to(axes.c2p(1.0, 9.2) + LEFT * 0.65)
        shift_arrow = Arrow(
            axes.c2p(3.8, 5.7),
            axes.c2p(5.0, 5.7),
            color=ORANGE,
            buff=0.05,
            stroke_width=5,
        )

        self.play(
            Create(new_demand_curve),
            Transform(demand_label, new_demand_label),
            GrowArrow(shift_arrow),
            run_time=2.5,
        )
        self.wait(1.2)

        # === Section 5: New equilibrium and insight ===
        eq1_x = 6.25
        eq1_y = 5.25

        eq1_dot = Dot(axes.c2p(eq1_x, eq1_y), color=YELLOW, radius=0.09)
        eq1_h = DashedLine(axes.c2p(0, eq1_y), axes.c2p(eq1_x, eq1_y), color=YELLOW, stroke_opacity=0.85)
        eq1_v = DashedLine(axes.c2p(eq1_x, 0), axes.c2p(eq1_x, eq1_y), color=YELLOW, stroke_opacity=0.85)
        p1_label = Text("P1", font_size=20, color=YELLOW).next_to(axes.c2p(0, eq1_y), LEFT, buff=0.15)
        q1_label = Text("Q1", font_size=20, color=YELLOW).next_to(axes.c2p(eq1_x, 0), DOWN, buff=0.15)
        e1_label = Text("E1", font_size=20, color=YELLOW).next_to(eq1_dot, UR, buff=0.12)
        eq1_group = VGroup(eq1_h, eq1_v, eq1_dot, p1_label, q1_label, e1_label)

        self.play(Create(eq1_group), run_time=2.0)
        self.wait(1.0)

        self.play(Indicate(eq1_dot, scale_factor=1.25), run_time=1.0)
        self.wait(0.8)

        price_arrow = Arrow(
            axes.c2p(0, eq0_y) + LEFT * 0.45,
            axes.c2p(0, eq1_y) + LEFT * 0.45,
            color=YELLOW,
            buff=0.05,
            stroke_width=5,
        )
        qty_arrow = Arrow(
            axes.c2p(eq0_x, 0) + DOWN * 0.45,
            axes.c2p(eq1_x, 0) + DOWN * 0.45,
            color=YELLOW,
            buff=0.05,
            stroke_width=5,
        )
        price_text = Text("价上升", font_size=22, color=YELLOW).next_to(price_arrow, LEFT, buff=0.12)
        qty_text = Text("量上升", font_size=22, color=YELLOW).next_to(qty_arrow, DOWN, buff=0.12)

        self.play(
            GrowArrow(price_arrow),
            GrowArrow(qty_arrow),
            Write(price_text),
            Write(qty_text),
            run_time=2.0,
        )
        self.wait(1.2)

        self.play(
            Flash(eq1_dot.get_center(), color=YELLOW),
            Circumscribe(VGroup(price_text, qty_text), color=YELLOW, run_time=1.5),
            run_time=1.5,
        )
        self.wait(2.6)

        # === Section 6: Summary ===
        self.play(FadeOut(demand_up_text), run_time=0.8)
        self.wait(0.5)

        fade_group = VGroup(
            shift_arrow,
            eq0_group,
            price_arrow,
            qty_arrow,
            price_text,
            qty_text,
            demand_curve,
        )
        self.play(FadeOut(fade_group), run_time=1.2)
        self.wait(0.8)

        summary = VGroup(
            Text("需求右移", font_size=26, color=BLUE),
            Text("价量同升", font_size=28, color=YELLOW),
        ).arrange(DOWN, buff=0.18).to_edge(DOWN)
        summary_box = SurroundingRectangle(summary, color=YELLOW, buff=0.2)

        self.play(Write(summary), Create(summary_box), run_time=1.8)
        self.wait(1.5)

        self.play(Circumscribe(summary_box, color=YELLOW, run_time=1.4))
        self.wait(2.5)

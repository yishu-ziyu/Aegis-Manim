from manim import *

class AI_Economics_Story(Scene):
    def construct(self):
        # --- Section 1: Intro ---
        self.next_section(name="Intro")
        
        main_title = Text("The Economics of AI", font_size=48, color=BLUE)
        subtitle = Text("A Manim Story", font_size=24, color=GREY).next_to(main_title, DOWN)
        
        self.play(Write(main_title), FadeIn(subtitle))
        self.wait(1)
        self.play(FadeOut(main_title), FadeOut(subtitle))

        # --- Section 2: The Tech (Neural Network) ---
        self.next_section(name="The Tech")
        
        # Subtitle for simple storytelling
        story_text = Text("Chapter 1: The Tech", font_size=32).to_edge(UP)
        self.play(Write(story_text))
        
        # Draw simple NN
        layers = [3, 2] # Simplified for speed
        layer_groups = VGroup()
        for i, num_nodes in enumerate(layers):
            layer_nodes = VGroup()
            for j in range(num_nodes):
                node = Circle(radius=0.3, color=WHITE).move_to(
                    RIGHT * (i - 0.5) * 3 + UP * ((num_nodes - 1) / 2 - j) * 1.5
                )
                layer_nodes.add(node)
            layer_groups.add(layer_nodes)
            
        connections = VGroup()
        for u in layer_groups[0]:
            for v in layer_groups[1]:
                line = Line(u.get_center(), v.get_center(), color=GREY, stroke_width=1)
                line.set_z_index(-1)
                connections.add(line)
        
        nn_group = VGroup(layer_groups, connections).move_to(ORIGIN)
        
        self.play(FadeIn(nn_group))
        
        # Narration
        narration = Text("We built a powerful AI model...", font_size=24, color=YELLOW).to_edge(DOWN)
        self.play(Write(narration))
        self.wait(1)
        
        # Activation animation
        self.play(
            LaggedStart(*[
                ShowPassingFlash(line.copy().set_color(BLUE), time_width=0.5)
                for line in connections
            ], lag_ratio=0.1),
            run_time=2
        )
        
        # Transition out
        self.play(FadeOut(nn_group), FadeOut(narration), FadeOut(story_text))

        # --- Section 3: The Market (Supply & Demand) ---
        self.next_section(name="The Market")
        
        story_text = Text("Chapter 2: The Market", font_size=32).to_edge(UP)
        self.play(Write(story_text))
        
        # Setup Axes
        axes = Axes(
            x_range=[0, 10, 1], y_range=[0, 10, 1],
            x_length=6, y_length=5,
            axis_config={"include_numbers": False, "tip_shape": ArrowTriangleFilledTip}
        )
        labels = axes.get_axis_labels(x_label=Text("Q"), y_label=Text("P"))
        
        # Initial Curves
        demand = axes.plot(lambda x: 8 - 0.5*x, color=BLUE, x_range=[0, 10])
        supply = axes.plot(lambda x: 2 + 0.5*x, color=RED, x_range=[0, 10])
        d_label = axes.get_graph_label(demand, Text("D", font_size=24), x_val=9)
        s_label = axes.get_graph_label(supply, Text("S", font_size=24), x_val=9)
        
        graph_group = VGroup(axes, labels, demand, supply, d_label, s_label)
        self.play(Create(graph_group))
        
        narr_1 = Text("The market demand was stable.", font_size=24, color=YELLOW).to_edge(DOWN)
        self.play(Write(narr_1))
        self.wait(1)
        
        # Demand Shift Animation
        narr_2 = Text("Suddenly, AI interest exploded!", font_size=24, color=YELLOW).to_edge(DOWN)
        
        new_demand = axes.plot(lambda x: 10 - 0.5*x, color=BLUE_A, x_range=[0, 10])
        new_d_label = axes.get_graph_label(new_demand, Text("D'", font_size=24), x_val=9)
        
        self.play(FadeOut(narr_1), FadeIn(narr_2))
        self.play(
            Transform(demand, new_demand),
            Transform(d_label, new_d_label),
            run_time=2
        )
        self.wait(1)
        
        self.play(FadeOut(graph_group), FadeOut(narr_2), FadeOut(story_text))
        
        # --- Section 4: Outro ---
        self.next_section(name="Outro")
        
        final_text = Text("To be continued...", font_size=36)
        self.play(FadeIn(final_text))
        self.wait(2)
        self.play(FadeOut(final_text))

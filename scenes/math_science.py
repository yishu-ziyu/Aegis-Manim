from manim import *

class QuadraticScene(Scene):
    def construct(self):
        # 1. Setup Axes
        axes = Axes(
            x_range=[-5, 5, 1],
            y_range=[-2, 10, 2],
            x_length=7,
            y_length=6,
            axis_config={"include_numbers": False, "tip_shape": ArrowTriangleFilledTip},
        )
        labels = axes.get_axis_labels(
            x_label=Text("x", font_size=24), 
            y_label=Text("y", font_size=24)
        )

        # 2. Define Function: y = ax^2 + bx + c
        # Initial: a=1, b=0, c=0 -> y = x^2
        a = ValueTracker(1)
        
        def quad_func(x):
            return a.get_value() * x**2

        # 3. Create Curve
        # plot uses the tracker value dynamically
        graph = always_redraw(lambda: axes.plot(quad_func, color=BLUE, x_range=[-3, 3]))
        
        # 4. Labels
        func_label = always_redraw(lambda: Text(
            f"y = {a.get_value():.1f}x²", 
            font_size=24, color=BLUE
        ).next_to(graph, UP))

        # 5. Animation
        self.play(Create(axes), Write(labels))
        self.play(Create(graph), Write(func_label))
        self.wait(1)

        # Animate changing 'a' (Width/Direction)
        self.play(a.animate.set_value(0.5), run_time=2) # Wider
        self.wait(0.5)
        self.play(a.animate.set_value(2), run_time=2)   # Narrower
        self.wait(0.5)
        self.play(a.animate.set_value(-1), run_time=2)  # Flip
        self.wait(1)


class NeuralNetworkScene(Scene):
    def construct(self):
        # Simple MLP: 3 Input -> 4 Hidden -> 2 Output
        
        # 1. Create Layers
        layers = [3, 4, 2]
        layer_groups = VGroup()
        
        # Spacing
        layer_spacing = 2.5
        node_spacing = 0.8
        
        for i, num_nodes in enumerate(layers):
            layer_nodes = VGroup()
            for j in range(num_nodes):
                node = Circle(radius=0.2, color=WHITE, stroke_width=2)
                # Center nodes vertically
                node.move_to(
                    RIGHT * (i - 1) * layer_spacing + 
                    UP * ((num_nodes - 1) / 2 - j) * node_spacing
                )
                layer_nodes.add(node)
            layer_groups.add(layer_nodes)

        # 2. Create Weights (Connections)
        connections = VGroup()
        for i in range(len(layers) - 1):
            current_layer = layer_groups[i]
            next_layer = layer_groups[i+1]
            
            for u in current_layer:
                for v in next_layer:
                    line = Line(u.get_center(), v.get_center(), stroke_width=1, color=GREY)
                    # Put lines behind nodes
                    line.set_z_index(-1)
                    connections.add(line)

        # 3. Labels
        input_label = Text("Input", font_size=20).next_to(layer_groups[0], UP)
        hidden_label = Text("Hidden", font_size=20).next_to(layer_groups[1], UP)
        output_label = Text("Output", font_size=20).next_to(layer_groups[2], UP)
        labels = VGroup(input_label, hidden_label, output_label)

        # 4. Animation Sequence
        self.play(FadeIn(layer_groups), FadeIn(labels))
        self.play(Create(connections, lag_ratio=0.01), run_time=2)
        self.wait(1)

        # 5. Simulate Activation Flow
        # Highlight input nodes
        self.play(layer_groups[0].animate.set_fill(BLUE, opacity=1), run_time=0.5)
        
        # Flow to hidden
        self.play(
            LaggedStart(*[
                ShowPassingFlash(line.copy().set_color(YELLOW), time_width=0.5)
                for line in connections 
                if line.get_start()[0] < layer_groups[1][0].get_center()[0] # Only first layer connections
            ], lag_ratio=0),
            run_time=1
        )
        self.play(layer_groups[1].animate.set_fill(BLUE, opacity=1), run_time=0.5)
        
        # Flow to output
        self.play(
            LaggedStart(*[
                ShowPassingFlash(line.copy().set_color(YELLOW), time_width=0.5)
                for line in connections
                if line.get_start()[0] > layer_groups[0][0].get_center()[0] # Only second layer connections
            ], lag_ratio=0),
             run_time=1
        )
        self.play(layer_groups[2].animate.set_fill(RED, opacity=1), run_time=0.5)
        
        self.wait(2)

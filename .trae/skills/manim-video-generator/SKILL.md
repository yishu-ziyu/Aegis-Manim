---
name: "manim-video-generator"
description: "Generates educational animation videos using Manim. Invoke when user wants to create teaching videos with code, geometric animations, or math visualizations."
---

# Manim Video Generator

This skill generates educational animation videos using Manim, a Python-based animation engine.

## When to Use This Skill

Invoke this skill when the user:
- Wants to create teaching/explanation videos
- Needs geometric animations (circles, lines, graphs)
- Wants to explain math concepts with visual animations
- Asks to generate a video about a topic
- Needs to create animated presentations

## Prerequisites

### Environment Setup
```bash
# Activate virtual environment
cd /Users/mahaoxuan/Desktop/vibe/manim-main
source .venv/bin/activate

# Ensure LaTeX is available
eval "$(/usr/libexec/path_helper)"
```

### Working Directory
All projects should be created in: `experiment_YYYY-MM-DD/`

## Usage

### 1. Create a New Video Project

Create a Python file with Manim scenes:

```python
from manim import *

class MyScene(Scene):
    def construct(self):
        # Set background color
        self.camera.background_color = "#1a1a2e"

        # Add content
        title = Text("My Title", font_size=56)
        self.play(Write(title))
        self.wait(1)
```

### 2. Run the Video

```bash
cd experiment_YYYY-MM-DD
manim -ql filename.py -o output.mp4
```

Select scenes when prompted (e.g., "1,2,3" or "1,2,3,4,5").

### 3. Quality Options

| Flag | Quality | Speed |
|------|---------|-------|
| `-ql` | 480p15 | Fast (draft) |
| `-qm` | 720p30 | Medium |
| `-qh` | 1080p30 | High |

## Best Practices

### Text Animation
**Avoid** using `Write()` for multiple lines together - they will overlap and become blurry.

**Use** `FadeIn` instead:
```python
# Good - lines appear separately
self.play(FadeIn(title))
self.play(FadeIn(subtitle, shift=UP))

# Bad - will overlap
self.play(Write(title))
self.play(Write(subtitle))  # Overlaps with title!
```

### Layout
Always pre-position elements:
```python
title = Text("Title", font_size=56).to_edge(UP)
subtitle = Text("Subtitle", font_size=36).next_to(title, DOWN, buff=0.3)
```

### Background Colors
Recommended dark theme:
```python
self.camera.background_color = "#1a1a2e"  # Dark blue
```

### Color Scheme
```python
# Primary colors
RED = "#FF6B6B"
GREEN = "#4ECDC4"
YELLOW = "#FFE66D"
PURPLE = "#C9B1FF"
```

## Common Patterns

### Title Slide
```python
class TitleSlide(Scene):
    def construct(self):
        self.camera.background_color = "#1a1a2e"
        title = Text("Title", font_size=72, color="#FF6B6B")
        subtitle = Text("Subtitle", font_size=36, color="#4ECDC4")
        subtitle.next_to(title, DOWN, buff=0.3)
        self.play(FadeIn(title))
        self.play(FadeIn(subtitle, shift=UP))
        self.wait(2)
```

### Bullet Points
```python
class BulletPoints(Scene):
    def construct(self):
        self.camera.background_color = "#1a1a2e"
        title = Text("Key Points", font_size=56).to_edge(UP)
        self.add(title)

        points = VGroup(
            Text("• Point 1", font_size=32, color="#4ECDC4"),
            Text("• Point 2", font_size=32, color="#4ECDC4"),
            Text("• Point 3", font_size=32, color="#4ECDC4"),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.5)

        for point in points:
            self.play(FadeIn(point, shift=RIGHT * 0.5))
            self.wait(0.3)
```

### Geometry Animation
```python
class GeometryDemo(Scene):
    def construct(self):
        circle = Circle(radius=1.5, color=BLUE)
        square = Square(side_length=1.5, color=RED)

        self.play(Create(circle))
        self.play(Create(square))
        self.wait(1)
```

### Function Graph
```python
class FunctionGraph(Scene):
    def construct(self):
        axes = Axes(
            x_range=[-3, 3, 1],
            y_range=[0, 9, 2],
            x_length=6,
            y_length=5
        )
        graph = axes.plot(lambda x: x**2, color=YELLOW)

        self.play(Create(axes))
        self.play(Create(graph))
        self.wait(2)
```

## Troubleshooting

### LaTeX Not Found
If you see "latex not found":
```bash
brew install --cask basictex
eval "$(/usr/libexec/path_helper)"
```

### Missing LaTeX Packages
If standalone.cls is missing, simplify code to avoid complex LaTeX:
- Use `Text` instead of `MathTex`
- Avoid axis labels with get_axis_labels()

### Scene Selection
When Manim asks for scene selection:
```bash
# Single scene
echo "1" | manim -ql file.py

# Multiple scenes
echo "1,2,3" | manim -ql file.py
```

## Output Location

Generated videos are saved to:
```
experiment_YYYY-MM-DD/media/videos/[filename]/480p15/
```

## Related Skills

- **Remotion**: For React-based video generation (better for AI-generated content pipelines)
- **Video Editing**: For post-processing (adding audio, transitions)

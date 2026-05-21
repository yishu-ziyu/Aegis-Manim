from manim import *


class OpenClawIntro(Scene):
    def construct(self):
        self.camera.background_color = "#1a1a2e"
        
        title = Text("Open Claw", font_size=72, color="#FF6B6B")
        subtitle = Text("开源 AI 智能体", font_size=36, color="#4ECDC4")
        lobster = Text("🦞", font_size=120)
        
        lobster.to_edge(DOWN, buff=0.5)
        
        self.play(Write(title))
        self.wait(0.3)
        self.play(FadeIn(subtitle, shift=UP))
        self.wait(0.3)
        self.play(FadeIn(lobster))
        self.wait(2)
        
        self.play(
            title.animate.scale(0.6).to_edge(UP),
            subtitle.animate.scale(0.8).next_to(title, DOWN, buff=0.3),
            lobster.animate.shift(UP * 1.5),
            run_time=1.5
        )
        self.wait(1)


class WhatIsOpenClaw(Scene):
    def construct(self):
        self.camera.background_color = "#1a1a2e"
        
        title = Text("什么是 Open Claw？", font_size=56, color=WHITE).to_edge(UP)
        self.add(title)
        
        definition = VGroup(
            Text("• 开源 AI 智能体项目", font_size=32, color="#4ECDC4"),
            Text("• 可部署到个人电脑", font_size=32, color="#4ECDC4"),
            Text("• Logo 是一只龙虾", font_size=32, color="#4ECDC4"),
            Text("• 俗称「龙虾AI」", font_size=32, color="#4ECDC4"),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.6).shift(DOWN * 0.3)
        
        for item in definition:
            self.play(FadeIn(item, shift=RIGHT * 0.5))
            self.wait(0.3)
        
        self.wait(2)


class CoreFeatures(Scene):
    def construct(self):
        self.camera.background_color = "#1a1a2e"
        
        title = Text("核心特点", font_size=56, color=WHITE).to_edge(UP)
        self.add(title)
        
        features = VGroup(
            Text("1. 自主执行任务", font_size=30, color="#FF6B6B"),
            Text("2. 本地部署，隐私安全", font_size=30, color="#FFE66D"),
            Text("3. 从「只会对话」升级为", font_size=30, color="#4ECDC4"),
            Text("   「能干活、能落地」", font_size=30, color="#4ECDC4"),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.5).shift(DOWN * 0.3)
        
        for feature in features:
            self.play(FadeIn(feature, shift=RIGHT * 0.5))
            self.wait(0.3)
        
        self.wait(2)


class ApplicationScenario(Scene):
    def construct(self):
        self.camera.background_color = "#1a1a2e"
        
        title = Text("应用场景", font_size=56, color=WHITE).to_edge(UP)
        self.add(title)
        
        scenarios = VGroup(
            Text("🔹 自动化交易", font_size=32, color="#FF6B6B"),
            Text("🔹 任务执行", font_size=32, color="#FFE66D"),
            Text("🔹 生产力工具", font_size=32, color="#4ECDC4"),
            Text("🔹 AI 助手", font_size=32, color="#C9B1FF"),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.7).shift(DOWN * 0.2)
        
        for scenario in scenarios:
            self.play(FadeIn(scenario, shift=RIGHT * 0.5))
            self.wait(0.3)
        
        self.wait(2)


class Summary(Scene):
    def construct(self):
        self.camera.background_color = "#1a1a2e"
        
        title = Text("Open Claw", font_size=64, color="#FF6B6B")
        tagline = Text("让 AI 从「对话」到「干活」", font_size=36, color="#4ECDC4")
        lobster = Text("🦞", font_size=100)
        
        title.shift(UP * 0.5)
        tagline.next_to(title, DOWN, buff=0.3)
        lobster.to_edge(DOWN, buff=0.5)
        
        self.play(FadeIn(title))
        self.wait(0.3)
        self.play(FadeIn(tagline, shift=UP))
        self.wait(0.3)
        self.play(FadeIn(lobster))
        self.wait(2)

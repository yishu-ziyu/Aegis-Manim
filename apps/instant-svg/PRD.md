# 产品需求文档：Aegis 智能 Manim 教学视频生成器 (MVP)

## 1. 产品定义与核心价值

**背景：**
学生和教育者需要高质量的动态演示视频，但在 AI 生成技术完全成熟前，预设的高质量模板是更可靠的教学工具。

**产品定义：**
Aegis 是一个双模态的教学视频工具，包含 **"课程模板库" (Stable)** 和 **"AI 生成器" (Experimental)**。

**核心价值：**

- **所见即所得 (Pre-set)**: 提供经过验证的高质量课程模板，解决 AI 生成的不稳定性。
- **零代码视频制作**：学生无需学习 Manim，无需编写代码。
- **即时反馈**：几秒钟内生成脚本，分钟级渲染视频。

---

## 2. 产品模式 (Product Modes)

### 模式 A：课程模板库 (Template Library) - 🔴 当前 MVP 重点

学生直接从预设的“课程菜单”中选择知识点观看。

- **目录**：
  - 1. 基础篇：Manim 三大基石 (Placement, Styling)
  - 2. 数学篇：动态二次函数、神经网络
  - 3. 经济篇：供需曲线、生产可能性边界 (PPF)、拉弗曲线
  - 4. 叙事篇：AI 的经济学故事 (完整微电影)
- **交互**：运行 `python course_menu.py`，输入数字选择课程，自动播放/渲染。

### 模式 B：AI 生成器 (AI Generator) - 🔵 Beta 功能

用户输入自然语言，调用 LLM 生成定制化视频（见 `manim_agent.py`）。

- **工作流**：User Prompt -> System Prompt (Golden Samples) -> LLM -> Code -> Video.

---

## 3. 关键技术栈 (Tech Stack)

- **Frontend**: CLI Menu (`course_menu.py`)。
- **Core Engine**: Manim Community (Python 3.12)。
- **Template Assets**:
  - `building_blocks_examples.py`
  - `science_scenes.py`
  - `economics_scenes.py`
  - `advanced_economics_scenes.py`
  - `story_example.py`
- **Asset Management**:
  - `manage_videos.py`: 负责将 `media/` 中的临时文件清理，或将成品发布到 `final_video_warehouse/`。

---

## 4. 演示案例库 (Golden Samples)

为了保证生成质量，我们将以下仅仅完成的高质量脚本作为 AI 的“学习素材”：

| 类别            | 关键文件名                     | 用途                                      |
| --------------- | ------------------------------ | ----------------------------------------- |
| **基础操作**    | `building_blocks_examples.py`  | 学习如何定位、上色、基础动画              |
| **数学/逻辑**   | `science_scenes.py`            | 学习 `ValueTracker`、`Axes`、神经网络连线 |
| **叙事/多章节** | `story_example.py`             | 学习 `self.next_section`、字幕添加、转场  |
| **经济学**      | `advanced_economics_scenes.py` | 学习复杂曲线绘制、切点计算                |

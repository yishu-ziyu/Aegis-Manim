# Aegis: 智能 Manim 教学视频生成库

[![Manim Powered](https://img.shields.io/badge/Manim-Community-blue?logo=python)](https://www.manim.community/)
[![Status](https://img.shields.io/badge/Status-MVP-green)]()
[![License](https://img.shields.io/badge/License-MIT-yellow)]()

<div align="center">
  <h3>让数学与经济学的推导过程“跃然纸上”</h3>
  <p>一个面向未来的、AI 驱动的 Manim 教学视频生成引擎。</p>
</div>

---

## 📖 项目简介 (Introduction)

**Aegis** 是一个基于 [Manim Community](https://www.manim.community/) 开发的动态教学视频代码库。与传统的静态绘图不同，Aegis 致力于构建**“数学物理引擎”**——通过代码模拟经济学模型背后的**动态调整机制**（如市场均衡搜寻、梯度优化、福利变形等）。

本项目采用了模块化的 **Registry（注册表）** 架构，旨在连接人类创作者与未来的 AI Agent。

### 核心亮点

- **🎯 动态引擎**: 拒绝硬编码。所有的图表均由 ValueTracker 驱动，能够实时演示参数变化带来的系统性影响。
- **🧩 模块化架构**: 代码库通过 `scene_registry.json` 进行索引，实现了场景逻辑与管理系统的解耦。
- **🤖 AI Ready**: 规范化的目录结构和元数据标签，为接入 LLM（大语言模型）自动生成视频做好了完美准备。
- **📦 资产管理**: 内置视频发布与清理工具，轻松管理您的渲染产物。

## 📂 项目结构 (Structure)

```text
Aegis-Manim/
├── core/                    # [系统核心]
│   ├── course_menu.py       # 交互式课程菜单 (CLI)
│   ├── manage_videos.py     # 视频资产发布与清理工具
│   └── manim_agent.py       # (实验性) AI Agent 接口
├── scenes/                  # [场景源码库]
│   ├── basic_geometry.py    # 基础几何与布局
│   ├── math_science.py      # 数学函数与神经网络可视化
│   ├── economics_static.py  # 经典的静态经济学图表
│   ├── economics_advanced.py# 高级模型 (PPF, Utility, Laffer)
│   ├── economics_dynamic.py # 动态引擎 (极值搜寻, 鞍径稳定, 福利变形)
│   └── stories.py           # 叙事微电影 (完整脚本示例)
├── scene_registry.json      # [核心索引] 场景元数据注册表
├── final_video_warehouse/   # [成品仓库] 存放发布的最终视频
└── requirements.txt         # 依赖列表
```

## 🚀 快速上手 (Quick Start)

### 1. 环境准备

确保您已安装 Python 3.10+ 以及 Manim Community 的系统依赖 (ffmpeg, latex, etc.)。

```bash
# 安装 Python 依赖
pip install -r requirements.txt
```

### 2. 运行课程菜单 (The Menu)

Aegis 提供了一个注册表驱动的 CLI 菜单，让您可以一键渲染库中的所有经典场景。

```bash
python core/course_menu.py
```

您将看到如下界面，输入数字即可开始渲染：

```text
[4] 经济: 供需曲线 (Supply & Demand)
[9] 动态微观: 极值搜寻 (Micro Optimization)
[10] 动态宏观: 鞍径稳定性 (Macro Saddle Path)
...
```

### 3. 管理视频资产

Manim 会生成大量临时文件。使用内置工具来发布成品或清理缓存。

```bash
# 将刚刚渲染的微观场景发布到仓库，并重命名
python core/manage_videos.py publish MicroOptimization --rename 微观_极值搜寻演示

# 清理所有临时渲染文件
python core/manage_videos.py clean
```

## 🎨 演示案例 (Gallery)

本项目已实现以下核心场景（均可在 `scenes/` 目录下找到源码）：

### 动态经济学 (Dynamic Engines)

- **极值搜寻 (Micro Optimization)**: 可视化梯度向量 ($\nabla U$) 与价格向量 ($P$) 的对齐过程。
- **鞍径稳定性 (Macro Saddle Path)**: 在向量场中展示 Ramsey 模型的唯一收敛路径。
- **福利变形 (Surplus Dynamics)**: 需求移动导致消费者剩余 (CS) 和生产者剩余 (PS) 面积的实时几何形变。
- **税收楔子 (Tax Wedge)**: 动态展示税收如何撑开价格剪刀差并产生无谓损失 (DWL)。

### 基础与叙事

- **基础几何**: 演示 Mobject 的定位与对齐。
- **AI 经济学微电影**: 一个结合科技演示与市场分析的多章节完整视频示例 (`stories.py`)。

## 🔮 未来规划 (Roadmap)

- [ ] **V2: AI Generator**: 接入 LLM，允许用户通过自然语言描述（"画一个需求冲击导致通胀的图"）直接生成 Manim 代码。
- [ ] **Hand-drawn Style**: 引入手绘风格渲染器，降低数学图表的距离感。
- [ ] **Web UI**: 将 CLI 菜单升级为基于 Web 的交互界面。

---

_Created by **Aegis Team** | Powered by [Manim Community](https://www.manim.community/)_

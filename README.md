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
│   ├── manim_agent.py       # LLM 生成与渲染 CLI
│   └── web_app.py           # Web 交互入口（用户填写自己的 API Key）
├── scenes/                  # [场景源码库]
│   ├── basic_geometry.py    # 基础几何与布局
│   ├── math_science.py      # 数学函数与神经网络可视化
│   ├── economics_static.py  # 经典的静态经济学图表
│   ├── economics_advanced.py# 高级模型 (PPF, Utility, Laffer)
│   ├── economics_dynamic.py # 动态引擎 (极值搜寻, 鞍径稳定, 福利变形)
│   └── stories.py           # 叙事微电影 (完整脚本示例)
├── scene_registry.json      # [核心索引] 场景元数据注册表
├── final_video_warehouse/   # [成品仓库] 存放发布的最终视频
└── pyproject.toml          # Python 依赖与项目配置
```

## 🚀 快速上手 (Quick Start)

### 1. 环境准备

确保您已安装 Python 3.11+ 以及 Manim Community 的系统依赖 (ffmpeg, latex, etc.)。

```bash
# 安装 Python 依赖（推荐 editable 安装）
pip install -e .
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

### 4. 接入智谱 GLM-5（自然语言生成场景）

先在项目根目录配置 API Key（推荐使用 `.env`）：

```bash
cp .env.example .env
# 编辑 .env，填入你的 key
```

安全建议：
- `.env` 已被 `.gitignore` 忽略，不会进入仓库；请不要把真实 API Key 写进代码或 README。
- 仅提交 `.env.example` 占位符模板，让每位用户在本地自行填写。
- 尽量不用 `--api-key` 直接传参（可能进入 shell history），优先用 `.env` 或环境变量。

然后直接输入你的问题来生成 Manim 代码并渲染：

```bash
python core/manim_agent.py "我不理解需求曲线右移时价格和数量如何变化，请做动态演示"
```

常用参数：

```bash
# 仅生成代码，不渲染
python core/manim_agent.py "讲解拉弗曲线" --no-render

# 指定模型（默认 glm-5）
python core/manim_agent.py "讲解预算约束与最优消费点" --model glm-5
```

### 5. Web 端使用（用户输入自己的 API Key）

启动本地 Web 服务：

```bash
./scripts/web_server.sh start
```

查看状态 / 停止服务：

```bash
./scripts/web_server.sh status
./scripts/web_server.sh stop
```

如果你希望前台运行（便于看实时 stdout），请使用：

```bash
./.venv/bin/python core/web_app.py --host 127.0.0.1 --port 8000
```

说明：
- 某些系统没有 `python` 命令（只有 `python3`），会导致服务启动后立刻退出。
- `scripts/web_server.sh` 已内置解释器选择逻辑：优先 `.venv/bin/python`，其次 `python3`。

打开浏览器：

```text
http://127.0.0.1:8000
```

在页面中填写：
- 你自己的智谱 API Key（不会写入仓库）
- 你的学习困惑（自然语言）
- 模型参数（可选）

提交后，系统会：
1. 调用智谱模型生成 Manim 代码
2. 自动渲染视频（或仅生成代码）
3. 在页面中返回代码与视频
4. 返回诊断 ID（`requestId`），用于快速定位本次请求

常见报错排查：
- `Model request failed | ...401...令牌...`：API Key 无效、过期或被撤销。
- `Model request failed | ...404 NOT_FOUND...`：Endpoint 不完整，需包含 `/paas/v4/chat/completions`（系统会自动修正常见输入）。
- 页面会显示 `诊断ID`，把它发给协作者可精确定位该次请求。
- 快速查看最近错误：`GET /api/bugs/recent?limit=20`
- 按诊断ID精确查询：`GET /api/bugs/recent?requestId=<你的ID>&limit=20`
- 进一步定位请看：`logs/web_runtime.log` 与 `logs/bug_trace.jsonl`

### 6. 开发过程日志（持续更新）

项目根目录提供持续更新日志：

```text
PRODUCT_DEV_LOG.md
```

运行时诊断日志（Web调用与报错）：

```text
logs/web_runtime.log
logs/bug_trace.jsonl
```

读取最近 bug（人类可读）：

```bash
python core/bug_report.py --limit 20
```

读取最近 bug（JSON）：

```bash
python core/bug_report.py --limit 20 --json
```

按 requestId 精确查询：

```bash
python core/bug_report.py --request-id <你的ID> --limit 20
```

追加结构化日志条目（带时间戳）：

```bash
python core/dev_log.py \
  --step "步骤标题" \
  --problem "遇到的问题" \
  --solution "采用的方案" \
  --rationale "为什么选这个方案" \
  --prevention "下次如何识别与避免" \
  --result "本次结果与经验"
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

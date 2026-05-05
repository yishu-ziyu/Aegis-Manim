# Aegis-Manim

[![Manim Powered](https://img.shields.io/badge/Manim-Community-blue?logo=python)](https://www.manim.community/)
[![Status](https://img.shields.io/badge/Status-v0.1.0-green)](https://github.com/yishu-ziyu/Aegis-Manim/tags)
[![License](https://img.shields.io/badge/License-MIT-yellow)](./LICENSE)

让数学与经济学里的抽象概念，通过 Manim 动画和 LLM 自动代码生成变成可视化教学视频。

## 项目定位

Aegis-Manim 提供三条工作流：

- 场景库渲染：直接运行内置教学场景。
- LLM 生成渲染（CLI）：自然语言 -> Manim 代码 -> 视频。
- LLM 生成渲染（Web）：浏览器输入问题和自己的 API Key，返回代码和视频。

## 当前能力（v0.1.0）

- 基于 `scene_registry.json` 的课程菜单与场景管理。
- 基于多 Provider 适配层的代码生成（默认智谱 `glm-5`，可切换 OpenAI-Compatible、Codex 本地代理、MiniMax Token/Coding Plan）。
- Web 端支持“本次请求输入 API Key”，不写入仓库；Provider、模型与 Base URL 可在界面切换。
- Manim 语法知识包：生成前会注入本地 Manim 0.19.2、官方文档与高质量社区写法的约束，降低模型生成过期/不可渲染 API 的概率。
- 运行时自动兼容修复（例如 LaTeX 不可用、方向常量替换）。
- 请求级诊断链路：`requestId` + 结构化 bug 日志 + 查询接口。

## 项目结构

```text
Aegis-Manim/
├── core/
│   ├── course_menu.py      # 场景菜单（CLI）
│   ├── manim_agent.py      # LLM 生成与渲染（CLI）
│   ├── llm_providers.py    # 多模型 Provider 适配层
│   ├── web_app.py          # Web 服务入口
│   ├── manage_videos.py    # 视频发布/清理工具
│   ├── bug_report.py       # bug 日志读取工具
│   └── dev_log.py          # 产品过程日志追加工具
├── scenes/                 # 场景源码
├── prompts/                # 系统提示词与 Manim 语法知识包
├── scripts/
│   └── web_server.sh       # Web 服务 start/stop/status
├── generated/              # 生成代码输出目录（运行时）
├── logs/                   # 运行日志目录（运行时）
├── scene_registry.json
├── PRODUCT_DEV_LOG.md
└── README.md
```

## 环境要求

- Python `3.11+`
- Manim 依赖（建议提前安装）：`ffmpeg`，可选 `latex`/`dvisvgm`

## 快速开始

### 1) 安装依赖

```bash
cd /path/to/Aegis-Manim
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2) 配置 API Key（本地）

```bash
cp .env.example .env
# 在 .env 中填写你实际使用 Provider 的 Key
# 默认智谱：BIGMODEL_API_KEY
# OpenAI：OPENAI_API_KEY
# MiniMax Token/Coding Plan：MINIMAX_API_KEY
```

安全约定：

- `.env` 不提交到仓库。
- 不在代码、README、截图中暴露真实 Key。
- 优先使用 `.env`，避免命令行直传 key 写入 shell history。

### 3) 运行场景菜单（无需 LLM）

```bash
./.venv/bin/python core/course_menu.py
```

### 4) CLI：自然语言生成并渲染

```bash
./.venv/bin/python core/manim_agent.py "解释税收楔子如何导致无谓损失，并做动态演示"
```

切换 Provider 示例：

```bash
# OpenAI API
OPENAI_API_KEY=... ./.venv/bin/python core/manim_agent.py \
  "讲解拉弗曲线" \
  --provider openai \
  --model gpt-4o-mini \
  --base-url https://api.openai.com/v1

# MiniMax Token Plan（CN）
MINIMAX_API_KEY=... ./.venv/bin/python core/manim_agent.py \
  "解释比较优势" \
  --provider minimax-token-cn \
  --model MiniMax-M2.7

# Codex / 本地 OpenAI-Compatible 代理
./.venv/bin/python core/manim_agent.py \
  "解释消费者剩余" \
  --provider codex-local-proxy \
  --model claude-opus-4-6-thinking

# Codex CLI 登录态（本机，无需 API Key）
./.venv/bin/python core/manim_agent.py \
  "解释消费者剩余" \
  --provider codex-cli \
  --model gpt-5.5
```

只生成代码不渲染：

```bash
./.venv/bin/python core/manim_agent.py "讲解拉弗曲线" --no-render
```

### 5) Web：浏览器交互

启动服务：

```bash
./scripts/web_server.sh start
```

检查状态：

```bash
./scripts/web_server.sh status
curl http://127.0.0.1:8000/api/health
```

停止服务：

```bash
./scripts/web_server.sh stop
```

打开浏览器：

```text
http://127.0.0.1:8000
```

## Vercel 公开入口

Vercel 部署当前作为公开入口、健康检查网关和“只生成代码”界面，适合绑定 `manim.yishuziyu.cn`：

- `/`：项目入口页。
- `/api/health`：Vercel Function 健康检查。
- `/api/generate`：调用远程 Provider 生成 Manim 代码，不在 Vercel 渲染视频。

Vercel 入口由根目录 `app.py` 的 FastAPI 应用提供，安装依赖由 `vercel.json` 固定为 `python -m pip install -r requirements.txt`，避免部署时安装完整 Manim 运行时。

完整视频渲染仍建议运行本地/VPS/Render/Fly 后端，因为 Manim 需要 `ffmpeg`、系统图形/字体依赖、本地媒体目录和更长执行时间。Vercel 不负责长期运行 `core/web_app.py`，也不承载完整渲染链路。本机专用 Provider（`codex-cli`、`codex-local-proxy`）不会出现在云端界面中。

验证 Vercel 网关：

```bash
./.venv/bin/python scripts/verify_vercel_gateway.py
```

## 诊断与排障

Web 请求会返回 `requestId`，这是排障主键。

### 关键日志文件

- `logs/web_runtime.log`：流程日志（HTTP、模型调用、渲染阶段）
- `logs/bug_trace.jsonl`：结构化错误日志（stage/severity/requestId/context）
- `PRODUCT_DEV_LOG.md`：产品开发过程日志

### 快速查询

查询最近 bug：

```bash
curl "http://127.0.0.1:8000/api/bugs/recent?limit=20"
```

按 requestId 精确查询：

```bash
curl "http://127.0.0.1:8000/api/bugs/recent?requestId=<你的ID>&limit=20"
```

本地人类可读报告：

```bash
./.venv/bin/python core/bug_report.py --limit 20
./.venv/bin/python core/bug_report.py --request-id <你的ID> --limit 20
```

## Provider 支持

内置预设：

- `zhipu`：智谱 GLM，默认兼容旧配置。
- `openai`：OpenAI API，OpenAI-Compatible `/chat/completions`。
- `codex-local-proxy`：本机 OpenAI-Compatible 代理，适合接入本地 Codex/代理计划。
- `codex-cli`：本机 Codex CLI 登录态，调用 `codex exec`，不需要在 Web 页面粘贴 API Key。
- `minimax-token-global` / `minimax-token-cn`：MiniMax Token Plan，Anthropic-Compatible `/messages`。
- `minimax-coding-global` / `minimax-coding-cn`：MiniMax Coding Plan。
- `minimax-openai-cn`：MiniMax OpenAI-Compatible 备用路径。
- `custom-openai` / `custom-anthropic`：自定义兼容网关。

Web 端只会把 API Key 用在当前 `/api/generate` 请求中；不会写入 `.env`、日志或仓库。诊断日志只记录 Provider、模型、Endpoint 和 requestId。

模型接入的设计原则、Provider 选型矩阵、失败诊断清单与开源方案参考见：[Aegis 大模型接入方法论](docs/aegis_llm_integration_methodology.md)。

## 常见问题

- `curl: (7) Failed to connect 127.0.0.1:8000`
  - 服务未启动或已退出。执行 `./scripts/web_server.sh start` 后再查 health。

- `Model request failed ...401...`
  - API Key 无效/过期/额度异常，检查对应 Provider 的 `.env` 或 Web 输入。

- `Model request failed ...404 NOT_FOUND...`
  - Endpoint/Base URL 路径错误。OpenAI-Compatible 通常填根地址如 `https://api.openai.com/v1`；Anthropic-Compatible 通常填根地址如 `https://api.minimaxi.com/anthropic/v1`。

- `Render failed`
  - 优先用 `requestId` 查询 `bug_trace.jsonl` 定位具体阶段和原因。

## 开发日志追加

```bash
./.venv/bin/python core/dev_log.py \
  --step "步骤标题" \
  --problem "遇到的问题" \
  --solution "采用的方案" \
  --rationale "为什么选这个方案" \
  --prevention "下次如何识别与避免" \
  --result "本次结果与经验"
```

## 路线图

- [ ] 增加“导出诊断包”（按 requestId 打包错误上下文）
- [ ] 增加 Web 端“最近失败记录”可视化面板
- [ ] 提升生成代码可执行率（更多静态检查与自动修复规则）
- [ ] 增加可复用教学模板库（数学/经济学常用讲解骨架）

## License

MIT. See [`LICENSE`](./LICENSE).

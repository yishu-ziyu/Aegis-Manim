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
- 基于智谱兼容接口的代码生成（默认 `glm-5`）。
- Web 端支持“本次请求输入 API Key”，不写入仓库。
- 运行时自动兼容修复（例如 LaTeX 不可用、方向常量替换）。
- 请求级诊断链路：`requestId` + 结构化 bug 日志 + 查询接口。

## 项目结构

```text
Aegis-Manim/
├── core/
│   ├── course_menu.py      # 场景菜单（CLI）
│   ├── manim_agent.py      # LLM 生成与渲染（CLI）
│   ├── web_app.py          # Web 服务入口
│   ├── manage_videos.py    # 视频发布/清理工具
│   ├── bug_report.py       # bug 日志读取工具
│   └── dev_log.py          # 产品过程日志追加工具
├── scenes/                 # 场景源码
├── prompts/                # 系统提示词
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
# 在 .env 中填写 BIGMODEL_API_KEY
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

## 常见问题

- `curl: (7) Failed to connect 127.0.0.1:8000`
  - 服务未启动或已退出。执行 `./scripts/web_server.sh start` 后再查 health。

- `Model request failed ...401...`
  - API Key 无效/过期/额度异常，检查 `.env` 或 Web 输入。

- `Model request failed ...404 NOT_FOUND...`
  - Endpoint 路径错误。默认应为 `https://open.bigmodel.cn/api/paas/v4/chat/completions`。

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

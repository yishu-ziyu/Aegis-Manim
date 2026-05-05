# Aegis-Manim 项目开发日志（总览）

最后更新：2026-05-05 17:16:46 CST
文件位置：`/Users/mahaoxuan/Desktop/AI产品经理/实验探索/vibe/manim-main/PROJECT_DEVELOPMENT_LOG.md`

## 1. 文档目的

本文件用于沉淀“对外可读”的项目开发总览，聚焦里程碑、关键问题、解决方案与下一步计划。  
逐条流水记录请参考：`PRODUCT_DEV_LOG.md`。

## 2. 项目目标

构建一个开源教学可视化系统：将用户输入的自然语言问题（数学/经济学）转为 Manim 动画代码并渲染为视频。

核心链路：

1. 用户输入问题（CLI 或 Web）。
2. 模型生成 Manim Python 代码。
3. 系统进行代码净化与兼容修复。
4. Manim 渲染视频。
5. 返回代码、视频与诊断信息（requestId）。

## 3. 阶段里程碑

### 阶段 A：能力基线确认（2026-02-14）

- 完成仓库结构、场景注册表和最小渲染链路核验。
- 确认项目具备“代码 -> 可视化视频”的基础能力。

### 阶段 B：P0 稳定性修复（2026-02-14）

- 修复 `scene_registry.json` 类名映射问题。
- 修复 `core/manage_videos.py` 中 `clean --force` 行为。
- 更新 README 安装/运行说明。

### 阶段 C：CLI 模型接入（2026-02-14）

- 在 `core/manim_agent.py` 完成智谱兼容接口接入。
- 支持 `.env` / 环境变量读取 API Key。
- 增加 `--model`、`--endpoint`、`--no-render` 参数。

### 阶段 D：Web MVP 上线（2026-02-14 ~ 2026-02-15）

- 新增 `core/web_app.py`，提供：
  - 页面表单（用户自填 API Key）
  - `/api/generate`（生成 + 渲染）
  - `/api/video/<id>`（视频播放）
  - `/api/health`（健康与版本）

### 阶段 E：可观测性与可恢复性（2026-02-15）

- 增加运行日志：`logs/web_runtime.log`。
- 前端支持详细错误透传（`error + detail`）。
- 增加 endpoint 规范化逻辑。
- 增加代码净化与语法校验（`extract_python_only`）。
- 增加运行时兼容修复（LaTeX 不可用降级、方向常量替换）。

### 阶段 F：Web 体验重构（2026-02-15）

- 重做页面视觉与信息层级。
- 增加兼容修复提示区与“复制代码”功能。

### 阶段 G：服务稳定启动（2026-02-15）

- 定位 `127.0.0.1:8000 connection refused` 根因为 `python` 命令不可用。
- 新增 `scripts/web_server.sh`（`start|stop|status|restart`），自动选择解释器。

### 阶段 H：Bug 诊断链路（2026-02-16）

- `/api/generate` 全链路返回 `requestId`。
- 新增结构化 bug 日志：`logs/bug_trace.jsonl`。
- 新增查询接口：
  - `/api/bugs/recent?limit=...`
  - `/api/bugs/recent?requestId=...&limit=...`
- 新增读取工具：`core/bug_report.py`（人类可读/JSON）。

### 阶段 I：文档优化（2026-02-22）

- 重构 README，统一上手路径、排障路径与命令风格。

### 阶段 J：发布打包

- 已推送 `main` 到 GitHub。
- 已创建并推送版本标签：`v0.1.0`。

### 阶段 K：多 Provider 与本地 Codex CLI 登录态（2026-05-05）

- 将模型调用从单一智谱路径扩展为多 Provider 适配层。
- 保留 `codex-local-proxy` 作为旧 OpenAI-Compatible 本地代理预设。
- 新增 `codex-cli` provider：复用本机 `codex login` 登录态，通过 `codex exec` 调用模型，不需要 Web 页面填写 API Key 或 Base URL。
- Web 端根据 provider 自动切换 Key/Base URL 字段显示，避免用户继续误填已经失效的 8317 代理地址。

### 阶段 L：Manim 语法知识层（2026-05-05）

- 新增 `prompts/manim_knowledge_pack.md`。
- 目标运行时固定为本地 ManimCE `0.19.2`，优先参考本仓库 `docs/source`、官方 Manim Community 文档/示例，以及仓库测试中的稳定写法。
- `core/manim_agent.py` 新增 `load_system_prompt()`，统一拼接基础 prompt 与 Manim 知识包。
- Web 与 CLI 两条生成链路共用同一份增强 prompt，降低模型生成过期 API、LaTeX 依赖代码、不可渲染布局的概率。

### 阶段 M：大模型接入方法论沉淀（2026-05-05）

- 新增 `docs/aegis_llm_integration_methodology.md`。
- 将本项目已验证的 ProviderPreset、OpenAI-Compatible 适配、本地 Codex CLI 登录态、旧 8317 本地代理、Key 安全、requestId 可观测性、Manim 知识层和生成代码后处理沉淀为统一方法论。
- 补充 LiteLLM、LangChain、Vercel AI Gateway、Ollama、Continue、OpenAI Structured Outputs 等开源/官方方案中的可借鉴模式。
- README Provider 章节增加方法论文档入口。

## 4. 关键问题复盘（高影响）

### 问题 1：模型调用失败但前端提示过于笼统

- 现象：仅显示 `Model request failed`。
- 根因：错误细节未透出、可观测性不足。
- 方案：错误 detail 透传 + 运行日志。
- 预防：先看 `logs/web_runtime.log` 再做业务判断。

### 问题 2：渲染失败（代码噪声/环境不兼容）

- 现象：SyntaxError、NameError、LaTeX 相关错误。
- 根因：模型输出混入解释文本；环境能力差异。
- 方案：代码净化 + 渲染前兼容修复。
- 预防：保留执行前静态校验与降级策略。

### 问题 3：修复后仍复现同样错误

- 现象：代码已改但行为不变。
- 根因：旧进程未重启，未加载新逻辑。
- 方案：引入 `/api/health` 版本识别并规范重启。
- 预防：每次改动后先核验 health 版本。

### 问题 4：服务端口无法连接

- 现象：`curl: (7) Failed to connect`。
- 根因：启动命令依赖不存在的 `python` 可执行文件。
- 方案：统一使用 `./scripts/web_server.sh start`。
- 预防：禁止手写多版本启动命令，统一脚本入口。

### 问题 5：截图沟通效率低，难定位真实原因

- 现象：浏览器只看到表层报错，口述不完整。
- 根因：缺少请求级追踪主键。
- 方案：`requestId` + 结构化日志 + 查询工具。
- 预防：报错统一附带 requestId。

### 问题 6：旧本地代理不可达与模型 Manim 语法不稳定

- 现象：选择 `codex-local-proxy` 时请求 `127.0.0.1:8317` 返回 connection refused；即便模型可达，也可能生成不符合当前 ManimCE 版本的代码。
- 根因：8317 是旧本地代理路径，当前机器没有对应服务监听；模型默认知识可能来自不同 Manim 版本或泛化代码片段，不能保证本地可渲染。
- 方案：新增 `codex-cli` 本机登录态 provider；新增 Manim 语法知识包并注入生成链路；保留运行时兼容修复和 requestId 诊断链路。
- 预防：本机开发优先使用 `codex-cli`；升级 Manim 或引入新社区方案时同步更新 `prompts/manim_knowledge_pack.md` 并跑生成/渲染冒烟。

### 问题 7：模型接入经验分散，新增 Provider 易重复踩坑

- 现象：Provider、Key、Base URL、本地代理、Codex CLI、输出解析和 Manim 语法经验分散在代码与流水日志中。
- 根因：缺少一份从架构原则到接入模板的 durable 方法论文档。
- 方案：建立 `docs/aegis_llm_integration_methodology.md`，把项目经验和开源方案统一沉淀。
- 预防：后续新增 Provider 或本地模型服务时，先按方法论文档补齐 preset、认证、endpoint、验证和日志记录。

## 5. 当前状态（截至 2026-05-05）

- CLI 与 Web 两条核心链路可用。
- 用户自带 API Key 模式可用且不写入仓库。
- 已具备请求级诊断能力与结构化 bug 追踪能力。
- 已具备多 Provider 适配层，可切换智谱、OpenAI-Compatible、MiniMax、旧本地代理与本地 Codex CLI 登录态。
- `codex-cli` 真实链路已验证：Web 请求生成并渲染成功，requestId `20260505-141202-0070da25`。
- 已具备 Manim 语法知识包，生成前注入本地 ManimCE 0.19.2 与官方/社区稳定写法约束。
- 已具备大模型接入方法论文档，覆盖 Provider 抽象、认证边界、OpenAI-Compatible、本地模型/代理、结构化输出和失败诊断。
- 文档已更新到可开源协作状态。
- `v0.1.0` 已发布。

## 6. 下一阶段优先级

1. 将 Manim 知识包升级为可检索资料层：官方文档、精选社区样例、失败案例和修复策略分层管理。
2. 增加 Provider health-check：区分 CLI 登录态、HTTP 本地代理、远程 API Key、OpenAI/Anthropic-compatible endpoint。
3. 增加按 requestId 的“一键导出诊断包”。
4. 增加 Web 端“最近失败记录”可视化面板。
5. 补充数学/经济学常见讲解模板库。
6. 增加关键 API 的轻量冒烟测试，并覆盖 `codex-cli` no-render 路径。

## 7. 日志维护规范

每次关键变更建议同步更新两份日志：

- `PRODUCT_DEV_LOG.md`：记录细粒度过程（时间顺序）。
- `PROJECT_DEVELOPMENT_LOG.md`：沉淀里程碑与阶段结论。

建议记录字段：

- 问题现象
- 解决方案
- 方案原因
- 下次识别与避免
- 结果与经验

## 8. 关联文件

- `README.md`
- `docs/aegis_llm_integration_methodology.md`
- `core/web_app.py`
- `core/manim_agent.py`
- `core/llm_providers.py`
- `prompts/manim_knowledge_pack.md`
- `core/bug_report.py`
- `core/dev_log.py`
- `scripts/web_server.sh`
- `PRODUCT_DEV_LOG.md`
- `logs/web_runtime.log`
- `logs/bug_trace.jsonl`

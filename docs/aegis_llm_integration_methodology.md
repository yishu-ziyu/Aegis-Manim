# Aegis 大模型接入方法论

本文件沉淀 Aegis-Manim 当前接入大模型的工程经验，并用开源项目和官方文档中的成熟做法补充成可复用清单。目标不是记录某个模型厂商的调用示例，而是建立一套能持续扩展 Provider、诊断失败、保护密钥、提升 Manim 生成质量的接入方法。

## 1. 核心原则

### 1.1 Provider 抽象先于模型选择

不要把“模型名”直接写进业务链路。稳定做法是先定义 Provider 合约：

- `provider id`：如 `zhipu`、`openai`、`codex-cli`、`custom-openai`。
- `api_type`：如 `openai-compatible`、`anthropic-compatible`、`codex-cli`。
- `base_url`：只存根地址，由后端规范化到真实 endpoint。
- `default_model` 和候选模型列表：用于 UI 默认值和降级建议。
- `requires_api_key`：区分用户自带 Key、服务端环境变量、本机登录态。
- `doc`：记录厂商文档入口，便于后续排障。

Aegis 已将这个合约落在 `core/llm_providers.py` 的 `ProviderPreset` 中。后续新增模型时，应优先新增 preset 和接口适配，而不是在 `web_app.py` 或 `manim_agent.py` 中硬编码分支。

### 1.2 OpenAI-Compatible 是适配层，不是身份

许多网关和本地模型服务都暴露 OpenAI-compatible API，但它们的认证、模型名、速率限制、响应差异和错误语义不一样。因此：

- UI 可以展示 `openai-compatible`，但日志必须同时记录真实 `provider id`、模型、endpoint。
- Base URL 允许用户填根地址，后端负责把 `/chat/completions` 等路径规范化。
- `404` 优先判断 endpoint 路径错误；`401/403` 优先判断 Key、权限或网关鉴权；`connection refused` 优先判断本地进程或端口。

LiteLLM、Ollama、Continue 等开源方案都采用类似思路：对外提供统一接口，对内保留 Provider 差异。

### 1.3 认证通道分三类

Aegis 当前应明确保留三条认证通道：

1. 用户自带 Key：Web 页面只用于本次请求，不写入 `.env`、日志或仓库。
2. 服务端环境变量：CLI 或本机私有部署可从 `.env` / shell env 读取。
3. 本机登录态或本地代理：例如 `codex-cli` 使用 `codex login` 登录态，`codex-local-proxy` 使用 `127.0.0.1:8317` 代理。

这三类不要混在一个字段里。`requires_api_key=False` 的 Provider 仍可能需要本机登录态、代理进程或网关鉴权，所以 UI 文案和 preflight 检查要分别说明。

### 1.4 LLM 是可降级增强层，不应阻断产品主路径

模型调用可能慢、超时、不可达或返回不可执行代码。产品链路需要有明确降级策略：

- 模型超时：返回可解释错误，保留 requestId，不让页面无限等待。
- 本地代理不可达：提示端口和 Provider 选择错误，而不是泛化为 Key 错。
- 代码无效：先做代码提取、AST 校验和一次带错误上下文的重试。
- 渲染失败：进入 Manim 兼容修复和 requestId 诊断链路。

前端和日志都应该让用户知道失败发生在 `validation`、`model`、`code_extract` 还是 `render` 阶段。

## 2. Aegis 当前架构落点

### 2.1 Provider 层

文件：`core/llm_providers.py`

职责：

- 维护 Provider preset 矩阵。
- 根据 `api_type` 构造真实 endpoint。
- 支持 OpenAI-compatible、Anthropic-compatible、本地 Codex CLI。
- 将 provider 信息输出给 Web UI。

新增 Provider 时的最小步骤：

1. 增加 `ProviderPreset`。
2. 明确 `api_type` 和 endpoint 规范化规则。
3. 明确 Key 来源和 `requires_api_key`。
4. 增加最小 no-render 生成测试或手动验证记录。

### 2.2 Prompt 与 Manim 知识层

文件：

- `prompts/system_prompt.md`
- `prompts/manim_knowledge_pack.md`
- `core/manim_agent.py`

职责：

- `load_system_prompt()` 拼接基础系统提示词和 Manim 知识包。
- 知识包锁定本地 ManimCE 版本、稳定 API、布局规则和常见失败规避。
- 生成策略明确要求代码只输出 Python、避免文本遮挡、旧文字及时退出。

经验判断：对 Aegis 来说，模型“可调用”只是第一层，模型“懂当前 Manim 语法和教学动画写法”才决定最终视频质量。因此，Manim 文档、示例、失败案例和 prompt 约束应被当成项目资产，而不是临时聊天提示。

### 2.3 生成代码后处理

文件：`core/manim_agent.py`

职责：

- 去除 Markdown fence 和解释文本。
- `ast.parse` 校验 Python 有效性。
- 渲染前应用兼容修复，例如 LaTeX 不可用时替换 `MathTex/Tex`，修复方向常量和常见 plot 参数。
- 支持 `--no-render` 调试模式，先验证模型输出。

后续可升级为结构化输出 envelope：

```json
{
  "scene_class": "GeneratedScene",
  "code": "...",
  "assumptions": ["..."],
  "render_notes": ["..."]
}
```
OpenAI Structured Outputs 一类能力可以把这类 envelope 固定成 JSON Schema，降低“解释文本混入代码”的概率。

### 2.4 Web 与可观测性

文件：

- `core/web_app.py`
- `core/bug_report.py`
- `logs/web_runtime.log`
- `logs/bug_trace.jsonl`

职责：

- Web 表单只把 Key 用于本次 `/api/generate`。
- 每次请求生成 requestId。
- 结构化记录 Provider、模型、endpoint、错误阶段、渲染结果。
- 支持 `/api/bugs/recent` 和 `core/bug_report.py` 按 requestId 查询。

经验判断：模型接入项目的排障主键不应该是截图，而应该是 requestId。截图只说明表层现象，requestId 才能连接输入、Provider、模型、代码、渲染日志和错误阶段。

## 3. Provider 选型矩阵

| 路径 | 适合场景 | 优点 | 风险 | Aegis 做法 |
| --- | --- | --- | --- | --- |
| 厂商原生 API | 稳定线上能力、明确 SLA | 文档完整，错误语义清晰 | Key/额度/地区限制 | `zhipu`、`openai` preset |
| OpenAI-Compatible 网关 | 快速接多个模型或聚合商 | 统一调用面，迁移成本低 | 兼容不等于完全一致 | `custom-openai` + endpoint 规范化 |
| Anthropic-Compatible 网关 | Claude/MiniMax 族消息接口 | 适合 messages 风格模型 | 请求/响应结构不同 | `custom-anthropic`、MiniMax preset |
| 本地 HTTP 代理 | 本机聚合 CLI、私有网关 | UI 仍走 HTTP 标准路径 | 进程、端口、代理链易失效 | `codex-local-proxy` 保留但需 preflight |
| 本地 CLI 登录态 | 单机 demo、开发者工具 | 无需页面输入 Key，复用本机登录 | CLI 依赖、速度和 stdout 解析 | `codex-cli` |
| 本地模型服务 | 隐私、离线、低成本实验 | 数据不出本机 | 模型质量和 Manim 能力不稳定 | 可按 Ollama OpenAI-compatible 路径扩展 |

## 4. 失败诊断清单

### 4.1 模型不可达

- `connection refused`：先查本地进程和端口，例如旧 `127.0.0.1:8317` 代理是否真的在监听。
- `timeout`：检查网络、代理、模型响应时间；Web 路径应设置上限并给出 requestId。
- `DNS` 或 TLS 错误：检查地区、代理和证书，不要误判成 prompt 问题。

### 4.2 鉴权失败

- `401`：Key 无效、过期、格式错误或未传。
- `403`：权限、额度、模型白名单或组织权限问题。
- 本地 CLI Provider：检查 CLI 是否安装、是否已登录、是否能独立执行最小请求。

### 4.3 Endpoint 错误

- `404`：优先检查 Base URL 是否重复带了 `/chat/completions` 或 `/messages`。
- OpenAI-compatible：根地址通常规范化到 `/chat/completions`。
- Anthropic-compatible：根地址通常规范化到 `/messages`。

### 4.4 输出不是可执行代码

- 先清理 Markdown fence。
- 从 `from manim import` 起截取代码。
- 用 AST 校验。
- 如果失败，带错误片段重试一次。
- 长期方案是结构化输出，而不是不断扩大字符串清理规则。

### 4.5 Manim 渲染失败

- LaTeX 缺失：优先使用 `Text` 或兼容替换。
- API 版本漂移：查 `prompts/manim_knowledge_pack.md` 是否已覆盖当前 ManimCE 版本。
- 视觉遮挡：检查同一区域是否连续 `Write(Text(...))` 但缺少 `FadeOut`、`ReplacementTransform` 或 `VGroup` 清场。
- 坐标轴/对象越界：使用固定布局锚点和 `to_edge` / `next_to` / `arrange`，避免裸坐标堆叠。

## 5. 开源与官方方法补充

### 5.1 LiteLLM

可借鉴点：

- 把多模型接入统一到 OpenAI-compatible 调用面。
- 用代理层集中做 Provider 路由、fallback、重试、预算和日志。
- 对业务方暴露稳定接口，对模型供应商变化保持隔离。

Aegis 应用方式：

- 保持 `ProviderPreset` 作为本项目内的轻量版 provider registry。
- 下一步可增加 provider health-check 和 fallback policy，而不是在失败时只返回通用错误。

参考：https://docs.litellm.ai/docs/proxy_server

### 5.2 LangChain / Vercel AI SDK

可借鉴点：

- 用统一模型接口减少上层业务对具体厂商 SDK 的耦合。
- 把 provider、model、temperature、streaming、tool/structured output 能力拆成可替换配置。

Aegis 应用方式：

- 当前不必引入大型框架，但应保持接口边界清晰。
- `core/manim_agent.py` 不应直接理解每个厂商的 HTTP 细节；这些细节属于 provider 层。

参考：

- https://docs.langchain.com/oss/python/langchain/models
- https://vercel.com/docs/ai-gateway

### 5.3 Ollama / 本地模型服务

可借鉴点：

- 本地模型可以通过 OpenAI-compatible API 暴露给现有应用。
- 本地路径适合隐私、离线和低成本迭代，但要单独评估模型对 Manim 的代码能力。

Aegis 应用方式：

- 可新增 `ollama-local` provider preset，默认 `http://127.0.0.1:11434/v1`。
- 需要明确提示：本地小模型可能适合 no-render 草稿，不一定适合一次性生成复杂 Manim 动画。

参考：https://docs.ollama.com/openai

### 5.4 Continue

可借鉴点：

- 开源 IDE Agent 通常把模型配置做成 provider + model + apiBase/apiKey 的组合。
- 支持 OpenAI-compatible 自定义 provider，便于接入本地代理或聚合网关。

Aegis 应用方式：

- Web UI 的“自定义 OpenAI-Compatible / Anthropic-Compatible”方向是正确的。
- 但自定义能力必须配套 requestId、endpoint 规范化和错误分层，否则用户很难自助排障。

参考：https://docs.continue.dev/customize/model-providers

### 5.5 OpenAI Structured Outputs 与 Key 安全

可借鉴点：

- 对模型输出强约束 JSON Schema，减少自由文本污染业务解析。
- Key 不应出现在客户端可持久化位置、仓库、日志或截图中。

Aegis 应用方式：

- 未来把生成结果升级为 `{scene_class, code, notes}` schema。
- 当前继续坚持 Web Key 只用于本次请求，不落盘、不写日志。

参考：

- https://platform.openai.com/docs/guides/structured-outputs
- https://help.openai.com/en/articles/5112595-best-practices-for-api-key-safety

## 6. Aegis 下一步落地项

1. Provider health-check：对 `codex-cli` 检查 CLI 安装与登录态，对本地代理检查端口，对 HTTP provider 检查 base URL 形态。
2. Provider contract tests：每个 provider 至少覆盖 endpoint 规范化、Key 需求、UI preset 输出。
3. 结构化输出 envelope：先在支持 JSON Schema 的 provider 上试点，失败时退回代码清洗路径。
4. 失败案例库：将 requestId、生成代码、渲染错误、修复策略整理成 `prompts/manim_knowledge_pack.md` 的输入材料。
5. Model capability registry：记录哪些模型适合 Manim 复杂场景、哪些只能做 no-render 草稿。
6. UI 自助诊断：把 `connection refused`、`401`、`404`、`render failed` 映射为明确的人类动作。

## 7. 新 Provider 接入模板

```text
1. 定义 ProviderPreset
   - id:
   - api_type:
   - base_url:
   - default_model:
   - requires_api_key:

2. 定义认证来源
   - Web 本次 Key:
   - .env / 环境变量:
   - 本机登录态 / 本地代理:

3. 定义 endpoint 规范化
   - 根地址:
   - chat/messages endpoint:
   - 常见错误:

4. 定义验证
   - no-render 生成:
   - 最小 render:
   - requestId:
   - 日志位置:

5. 定义文档更新
   - README Provider 列表:
   - PRODUCT_DEV_LOG:
   - 本方法论文档:
```

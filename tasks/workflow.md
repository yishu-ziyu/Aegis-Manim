# Aegis-Manim Workflow

## 主链路

1. `provider_layer` — Provider 配置、健康检查、fallback 链路
2. `generation_layer` — Prompt 接收、LLM 代码生成、代码修复
3. `validation_layer` — 语法预检、场景检测、兼容性修复
4. `render_layer` — 渲染调度、渲染执行、视频生成
5. `delivery_layer` — 视频交付、社区作品、导出

## 当前状态

- `provider_layer`：
  - Kimi Priority / MiniMax Direct / DeepSeek fallback 链路已验证，证据等级 `production_verified`
  - Mimo Direct 已上线但**不稳定**，CN 节点从 Vercel 访问 timeout 概率约 50%，timeout=120s，证据等级 `production_unstable`
  - Kimi Code API anthropic-compatible User-Agent 修复已部署，证据等级 `production_verified`
  - Provider preset 系统支持 openai-compatible / anthropic-compatible / codex-cli 三种协议
- `generation_layer`：
  - 公开试用计划（Public Trial Plans）支持 3 个 trial provider：kimi-priority、minimax-direct、mimo-direct
  - 系统 Prompt 优化完成，生成代码质量稳定
  - 温度 0.2，max_tokens 8192
- `validation_layer`：
  - `apply_runtime_compatibility_fixes()` 已部署，处理 x_label/y_label 等兼容性问题
  - `extract_python_only()` 提取代码逻辑稳定
  - 预检系统（precheck）在 trial plan 中已集成
- `render_layer`：
  - Render Backend 为外部服务（Render），API key + URL 已配置
  - Vercel 不直接渲染，通过 `/api/render` proxy 到后端
  - `renderBackend: external-required` 标记稳定
- `delivery_layer`：
  - 社区作品系统（Community Works）开发中，Tech Spec 已完成
  - Job Persistence 系统设计完成，尚未完全实现

## 当前要求

- **P0 紧急**：Mimo timeout 不稳定问题需要解决或降级方案
- **P1 优先**：Provider 闭环测试自动化（每次部署后自动验证所有 provider）
- **P1 优先**：代码生成质量评估体系（生成代码成功率、渲染成功率）
- **P2 计划**：社区作品系统前端实现
- **P2 计划**：Job Persistence 完整实现
- **P2 计划**：Vision 分析功能公开化（当前受 feature flag 控制）
- 每次部署前必须运行 `scripts/deploy_vercel.sh`（pyproject.toml 隐藏 workaround）
- 每次 Provider 配置变更必须更新 `tests/test_aegis_llm_providers.py`
- 长程迭代计划见 `Tasks/long-run-iteration-plan.md`

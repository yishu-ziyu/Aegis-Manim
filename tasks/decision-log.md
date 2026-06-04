# Aegis-Manim Decision Log

## 2026-05-28: Mimo timeout 处理策略（待决策）

**问题**：Mimo 从 Vercel 访问不稳定，50% 请求超时

**已排除方案**：
- ❌ 换 SGP 节点：Mimo key 是 CN-only，SGP 返回 401
- ❌ 换 AMS/US/HK 节点：均不可用或 401

**候选方案**：
- A: 增加 timeout 到 150s（需确认 Vercel maxDuration）
- B: Mimo fallback 时自动重试一次（可能仍然超时）
- C: 将 Mimo 从 trial plan 降级为仅专业版可用（减少公开流量）
- D: 在 Vercel 函数内用异步队列 + webhook 处理 Mimo（架构改动大）

**未决策**。

## 2026-05-28: Kimi Code 使用 anthropic-compatible 协议

**决策**：Kimi Code 从 openai-compatible 迁移到 anthropic-compatible

**理由**：Kimi Code 官方推荐使用 anthropic-compatible 端点（`/coding/messages`），且需要特殊的 `Aegis-Manim-Coding-Agent` User-Agent

**不要回退**：openai-compatible 端点不支持 Coding Agent 身份识别

## 2026-05-28: pyproject.toml 部署 workaround

**决策**：部署前临时隐藏 `pyproject.toml`

**理由**：Vercel 的 Python Runtime 检测到 pyproject.toml 会优先使用 `uv sync`，但 `manimpango` 需要系统级 `pangocairo` C 库，uv sync 会失败

**实现**：`scripts/deploy_vercel.sh` 用 `trap` 确保无论成败都恢复文件

**不要回退**：除非 Vercel 支持自定义构建命令绕过 uv，或 manimpango 变为可选依赖

## 2026-05-28: Trial Plan 支持 attempt 级别 base_url 覆盖

**决策**：`PUBLIC_TRIAL_PLANS` 的 attempt 配置支持 `base_url` 字段覆盖

**理由**：Provider preset 的默认 base_url 不一定适合所有部署环境（如 Mimo CN 节点对 Vercel 不稳定，但 key 又不能用 SGP）

**实现**：`generate_code_with_trial_plan()` 中 `trial_base_url = str(attempt.get("base_url", "")).strip()`

## 2026-05-28: Public Trial 不暴露 DeepSeek Direct

**决策**：DeepSeek 仅作为 Kimi Priority 的 fallback，不开放独立 trial plan

**理由**：DeepSeek 是付费 API，公开 trial 会消耗大量额度

**实现**：`PUBLIC_TRIAL_PLANS` 中无 `trial-deepseek-direct`

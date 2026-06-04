# Aegis-Manim Manifest

## 长程状态文件

- `Tasks/todo.md`：当前任务状态机
- `Tasks/handoff.md`：跨 Session 接手说明
- `Tasks/decision-log.md`：关键决策与不要重复探索的理由
- `Tasks/manifest.md`：关键产物路径（本文件）
- `Tasks/review.md`：验证、风险、未完成项
- `Tasks/round-log.md`：长程研发轮次账本，记录平台期、瓶颈、策略跃迁和证据路径
- `docs/issues-and-fixes.md`：问题与修复记录

## 关键开发文件

- `api/index.py` — Vercel Serverless API 网关，包含 generate、render、health、community、vision 等 endpoint
- `core/llm_providers.py` — Provider Preset 系统，支持 openai-compatible / anthropic-compatible / codex-cli
- `core/web_app.py` — 本地 Web App 逻辑
- `core/manim_agent.py` — Manim Agent 核心逻辑
- `core/alignment.py` — 代码对齐与修复
- `scripts/deploy_vercel.sh` — Vercel 部署脚本（pyproject.toml workaround）

## 关键测试文件

- `tests/test_aegis_llm_providers.py` — Provider 配置与 API 请求验证
- `tests/test_aegis_public_trial.py` — Public Trial Plans 状态机与 fallback 测试
- `tests/test_aegis_ops_scripts.py` — 部署脚本与运维工具测试

## Provider 配置

- `core/llm_providers.py` — ProviderPreset 定义
- `api/index.py` — PUBLIC_TRIAL_PLANS、timeout 配置、attempt 链

## 手动验收产物

- `docs/issues-and-fixes.md` — 2026-05-28 Kimi User-Agent + Mimo trial + Vercel 部署修复记录
- `scripts/measure_trial_provider_stability.py` — Provider 稳定性测量脚本

## 外部依赖

- Vercel Serverless Functions（Python Runtime）
- Render Backend（外部渲染服务）
- Supabase（社区作品存储）
- Kimi Code API（anthropic-compatible）
- MiniMax API（anthropic-compatible）
- DeepSeek API（openai-compatible）
- Mimo Token Plan（openai-compatible）

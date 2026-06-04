# Aegis-Manim Handoff

## 快速上下文

Aegis-Manim 是一个基于 Manim 的教育动画生成器，用户输入 prompt，系统调用 LLM 生成 Manim Python 代码，然后通过外部 Render Backend 渲染为视频。

当前部署在 Vercel（`manim.yishuziyu.cn`），API 入口为 Python Serverless Functions。

## 当前活跃问题

1. **Mimo timeout 不稳定**（P0）
   - Vercel US-East → Mimo CN 网络延迟波动大
   - 当前 timeout=120s，约 50% 请求超时 fallback
   - 需要决策：增加 timeout / 换节点 / 降级策略

2. **Provider 闭环测试未自动化**（P1）
   - 当前手动 curl 测试
   - 需要部署后自动验证所有 provider

## 关键文件位置

| 文件 | 作用 |
|------|------|
| `api/index.py` | API 网关，所有 endpoint |
| `core/llm_providers.py` | Provider 预设与调用 |
| `scripts/deploy_vercel.sh` | 部署脚本 |
| `docs/issues-and-fixes.md` | 问题记录 |
| `Tasks/` | 本目录，项目大脑 |

## 部署流程

```bash
# 部署前
rtk gain

# 执行部署（自动处理 pyproject.toml workaround）
./scripts/deploy_vercel.sh

# 部署后验证
./scripts/measure_trial_provider_stability.py
```

## 环境变量（Vercel）

必须配置：
- `KIMI_CODE_API_KEY`
- `MINIMAX_API_KEY`
- `DEEPSEEK_API_KEY`
- `MIMO_API_KEY`
- `RENDER_BACKEND_API_KEY`
- `RENDER_BACKEND_URL`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`

## 不要重复踩的坑

- Vercel 检测到 `pyproject.toml` 会优先用 `uv sync`，但 `manimpango` 需要系统级 C 库 → 必须用 `scripts/deploy_vercel.sh` 隐藏
- Kimi Code API 需要 `Aegis-Manim-Coding-Agent` User-Agent（anthropic-compatible 协议）
- Mimo key 是 CN-only，SGP/AMS/US/HK 节点均不可用
- 国内 API 从 Vercel（美国）访问可能超时，trial plan 应支持 `base_url` 覆盖

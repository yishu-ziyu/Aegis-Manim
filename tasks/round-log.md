# Aegis-Manim Round Log

## Round 2026-05-28: Provider 稳定性攻坚

### 平台期
- Kimi Code API 返回 `access` 错误（User-Agent 缺失）
- Mimo 上线后 timeout / auth 问题
- Vercel 部署被 pyproject.toml 阻塞

### 策略跃迁
- 引入 anthropic-compatible 协议的特殊 User-Agent 处理
- Trial plan 支持 attempt 级别 base_url 覆盖
- 部署脚本化（trap 恢复机制）

### 证据路径
- `docs/issues-and-fixes.md` 记录了完整修复过程
- `tests/test_aegis_llm_providers.py` 新增 Kimi Code User-Agent 断言
- `scripts/deploy_vercel.sh` 解决部署阻塞

### 回滚点
- 如 Mimo 持续不稳定，可移除 `trial-mimo-direct` 从 `PUBLIC_TRIAL_PLANS`
- 如 Kimi Code 仍有 `request` 级问题，可回退到 openai-compatible（但不推荐）

### P0-A 完成证据
- `api/index.py`：`PUBLIC_TRIAL_MIMO_TIMEOUT_SECONDS` 默认 "120" → "150"
- `vercel.json`：`functions["api/*.py"].maxDuration = 300`
- 部署 `dpl_GudJxiyL3hcgDjoWSH5kCiDy1aVx` 到 `https://manim.yishuziyu.cn`
- 连续 5 次 Mimo stress test 全部通过，fallback 率 = 0%
  - 响应时间范围：27s ~ 101s（均在 150s timeout 内）
  - 全部返回 `model: "Mimo 编程试用"`，`codeFile: "vercel-generated-code"`

### P1-A 完成证据
- `scripts/post_deploy_verify.py` — 部署后验证脚本，4 个 provider 全部验证
  - 3 个 required provider（kimi/minimax/mimo）验证 `ok=True` + `codeLen>1000` + `not fallback`
  - 1 个 expected failure（deepseek）验证 `ok=False` + 正确错误信息
- `.github/workflows/provider-smoke-test.yml` — GitHub Actions workflow，部署成功后自动触发
- `scripts/measure_trial_provider_stability.py` — 增强：增加 mimo、timeout=180、`--ci` 模式
- `tests/test_post_deploy_verify.py` — 13 个回归测试全部通过
- 本地验证：`python3 scripts/post_deploy_verify.py` 4/4 通过

### 下一步
- P1-B: 代码生成质量评估
- P2-A: 社区作品系统前端

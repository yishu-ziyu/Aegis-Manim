# Phase P1-A: Provider 闭环测试自动化

## 背景

每次部署后需要手动 curl 测试所有 provider，耗时且容易遗漏。需要建立自动化的闭环测试，部署后自动验证所有 trial provider 的可用性。

## BDD 用例

### 用例 1: 部署后自动健康检查

**Given** 新的生产部署完成
**When** GitHub Actions / Vercel Deploy Hook 触发
**Then** 自动执行 `scripts/measure_trial_provider_stability.py`
**And** 测试结果记录到 `logs/provider-stability/{timestamp}.json`

### 用例 2: 所有 trial provider 生成验证

**Given** 自动化测试脚本运行
**When** 依次调用 `trial-kimi-priority`, `trial-minimax-direct`, `trial-mimo-direct`
**Then** 每个 provider 返回 `ok: true`
**And** `code_len > 1000`（确认生成了有效代码）
**And** `codeFile == "vercel-generated-code"`（确认不是 fallback）

### 用例 3: Provider 降级检测

**Given** 某个 provider 连续 3 次测试失败
**When** 自动化测试完成
**Then** 发送告警（或记录到 `Tasks/review.md`）
**And** 该 provider 被标记为 `production_unstable`

### 用例 4: DeepSeek Direct 拒绝验证

**Given** 自动化测试调用 `trial-deepseek-direct`
**When** API 返回
**Then** 返回 `ok: false`
**And** `error` 包含 "只支持内置免费试用模型"
**And** 测试脚本将该结果标记为 "expected_failure"

## 技术设计

### 新增文件

- `scripts/post_deploy_verify.py` — 部署后验证脚本
- `.github/workflows/provider-smoke-test.yml` — GitHub Actions workflow

### 修改文件

- `scripts/measure_trial_provider_stability.py` — 增强为可 CI 调用

### 脚本逻辑

```python
# scripts/post_deploy_verify.py 伪代码
TRIAL_PROVIDERS = ["trial-kimi-priority", "trial-minimax-direct", "trial-mimo-direct"]
EXPECTED_FAILURES = ["trial-deepseek-direct"]

for provider in TRIAL_PROVIDERS:
    result = test_generate(provider, prompt="Draw a red circle")
    assert result.ok == True
    assert result.code_len > 1000
    assert result.codeFile == "vercel-generated-code"

for provider in EXPECTED_FAILURES:
    result = test_generate(provider)
    assert result.ok == False
```

## 手动验收入口

```bash
# 本地模拟 CI 测试
python3 scripts/post_deploy_verify.py --endpoint https://manim.yishuziyu.cn
```

## 验收标准

- [ ] `scripts/post_deploy_verify.py` 可独立运行
- [ ] GitHub Actions 在每次 Vercel 部署后自动运行
- [ ] 测试失败时发送通知（或至少记录到文件）
- [ ] 测试结果包含每个 provider 的响应时间、code_len、是否 fallback

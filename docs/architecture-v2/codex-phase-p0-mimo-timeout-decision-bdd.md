# Phase P0-A: Mimo Timeout 决策与降级方案

## 背景

Mimo Direct trial plan 已上线，但从 Vercel（US-East）访问 Mimo CN 节点（`token-plan-cn.xiaomimimo.com`）不稳定：
- 网络延迟波动 40s~70s
- 叠加 Mimo 代码生成 50s~60s
- 总时间 55s~122s，当前 timeout=120s 在边缘
- 约 50% 请求触发 `mimo:timeout` fallback 到 stable template

需要做出工程决策并实施。

## BDD 用例

### 用例 1: Mimo 正常响应时使用真模型

**Given** 用户选择 `trial-mimo-direct`
**And** Mimo API 在 120s 内返回
**When** 系统调用 `generate_code_with_trial_plan()`
**Then** 返回 `model: "Mimo 编程试用"`
**And** `codeFile: "vercel-generated-code"`
**And** `warnings` 不包含 timeout 提示

### 用例 2: Mimo 超时时优雅降级

**Given** 用户选择 `trial-mimo-direct`
**And** Mimo API 超过 120s 未返回
**When** 系统触发 fallback
**Then** 返回 `ok: true`
**And** `model: "stable-template-fallback"`
**And** `warnings` 包含 `"模型失败类别：mimo:timeout"`
**And** 用户收到明确提示"已自动切换到稳定模板生成"

### 用例 3: 增加 timeout 到 150s

**Given** `PUBLIC_TRIAL_MIMO_TIMEOUT_SECONDS` 设置为 150
**When** 用户选择 `trial-mimo-direct`
**Then** timeout 参数传递给 `generate_code_with_llm()` 为 150
**And** health check 返回 `"mimo": {"configured": true, "timeout_seconds": 150}`

### 用例 4: Vercel maxDuration 兼容性

**Given** `vercel.json` 中配置了 `"maxDuration": 300`
**When** 部署到 Vercel
**Then** 函数最大执行时间 >= 150s
**And** Mimo 请求在 150s 内不被 Vercel 截断

## 技术设计

### 方案对比

| 方案 | 改动量 | 效果 | 风险 |
|------|--------|------|------|
| A: timeout 120s → 150s | 小 | 可能减少 fallback 概率 | Vercel maxDuration 可能不够 |
| B: 一次重试 | 中 | 重试可能成功 | 总时间更长，用户体验更差 |
| C: Mimo 降级为专业版 | 小 | 彻底消除公开 trial 问题 | 减少免费用户选择 |
| D: 异步队列 | 大 | 彻底解决 | 架构改动大，实现周期长 |

### 推荐方案

**主方案**: A + C
- 先尝试 A（增加 timeout 到 150s，vercel.json 配置 maxDuration=300）
- 如果 A 仍不稳定，执行 C（从 PUBLIC_TRIAL_PLANS 移除 Mimo，保留为专业版 provider）

### 修改文件

- `api/index.py` — 修改 `PUBLIC_TRIAL_MIMO_TIMEOUT_SECONDS` 默认值
- `vercel.json` — 增加 `functions.maxDuration` 配置
- `docs/issues-and-fixes.md` — 记录决策结果

## 手动验收入口

```bash
# 测试 1: 验证 timeout 增加后的 Mimo 稳定性
for i in {1..5}; do
  echo "=== Attempt $i ==="
  curl -s -X POST https://manim.yishuziyu.cn/api/generate \
    -H "Content-Type: application/json" \
    -d '{"provider": "trial-mimo-direct", "prompt": "Draw a red circle"}' \
    --max-time 180 | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f\"ok={d.get('ok')} model={d.get('model')} file={d.get('codeFile')}\")
"
done
```

## 验收标准

- [ ] `PUBLIC_TRIAL_MIMO_TIMEOUT_SECONDS` 默认值为 150
- [ ] `vercel.json` 配置 `maxDuration` >= 150
- [ ] 连续 5 次 Mimo 测试，fallback 率 <= 20%
- [ ] 如 fallback 率仍 > 20%，执行方案 C（从 trial 移除）

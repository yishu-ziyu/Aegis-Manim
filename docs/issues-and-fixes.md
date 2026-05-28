# Aegis-Manim 问题与修复记录

## 2026-05-28: Mimo 上线 + Kimi Code API 修复

### 问题 1: Kimi Code API 返回 `access` 错误

**现象**: 生产站 `trial-kimi-priority` 调用 Kimi Code API 返回：
```
Kimi 本次未完成（access），已自动切换到 DeepSeek API 备用模型。
模型失败类别：kimi-code:access
```

**根因分析**: Kimi Code API 使用 `anthropic-compatible` 协议，但 `call_anthropic_compatible()` 函数中没有设置 `Aegis-Manim-Coding-Agent` User-Agent。Kimi 服务端通过 User-Agent 识别 Coding Agent 身份，缺少该 header 导致返回 access 拒绝。

**对比**: MiniMax 也使用 anthropic-compatible 协议，但 MiniMax 不检查 User-Agent，所以正常。

**修复** (`core/llm_providers.py`):
```python
# 修复前：call_anthropic_compatible 中只有固定 User-Agent
"User-Agent": "Aegis-Manim/1.0 ..."

# 修复后：根据 provider_name 动态设置
user_agent = "Aegis-Manim/1.0 ..."
if "Kimi Code" in provider_name:
    user_agent = "Aegis-Manim-Coding-Agent/1.0 ..."
```

**测试**: `test_kimi_code_anthropic_request_uses_coding_endpoint` 增加断言验证 User-Agent 包含 `Coding-Agent`。

**结果**: Kimi 不再返回 `access` 错误（但仍有 `request` 级问题，可能是超时或 Kimi 服务端其他限制）。

---

### 问题 2: Mimo 不在公开试用计划

**现象**: 生产站选择 Mimo 返回 `"公开内测页只支持内置免费试用模型。"`（HTTP 400）

**根因**: `PUBLIC_TRIAL_PLANS` 只包含 `trial-kimi-priority` 和 `trial-minimax-direct`，Mimo 只在自定义 Provider 列表中。

**修复** (`api/index.py`):
- 新增 `trial-mimo-direct` 试用计划
- 新增 `PUBLIC_TRIAL_MIMO_TIMEOUT_SECONDS` / `PUBLIC_TRIAL_MIMO_REPAIR_TIMEOUT_SECONDS`
- health check 增加 `configured.mimo` 状态

**结果**: Mimo 已可访问，但返回 `mimo:auth` fallback（Vercel 上的 `MIMO_API_KEY` 需要验证）。

---

### 问题 3: Mimo 从 Vercel 访问 CN 节点超时

**现象**: Mimo trial 返回 `HTTP 0 | The read operation timed out`

**根因**: Vercel 构建节点在美国东海岸（iad1），访问 `token-plan-cn.xiaomimimo.com` 超时。Mimo Vision 配置默认用 SGP 节点，但代码生成 preset 用 CN 节点。

**修复** (`api/index.py`):
- 让 trial plan 的 attempts 支持 `base_url` 覆盖
- `trial-mimo-direct` 指定 `"base_url": "https://token-plan-sgp.xiaomimimo.com/v1"`

```python
# 修复前：trial plan 硬编码 base_url=""
raw_code, _, _ = generate_code_with_llm(..., base_url="", ...)

# 修复后：支持 attempt 级别的 base_url 覆盖
trial_base_url = str(attempt.get("base_url", "")).strip()
raw_code, _, _ = generate_code_with_llm(..., base_url=trial_base_url, ...)
```

**结果**: Mimo 响应正常（但返回 auth 错误，需检查 key）。

---

### 问题 4: Vercel 部署被 `pyproject.toml` 阻塞

**现象**: `vercel --prod` 失败，`uv sync` 安装 `manimpango` 时缺少系统 `pangocairo`

**根因**: Vercel 检测到 `pyproject.toml` 后优先使用 `uv` 构建，但 `manimpango` 需要系统级 C 库。

**修复**: 创建 `scripts/deploy_vercel.sh`，部署前临时隐藏 `pyproject.toml`：
```bash
cp pyproject.toml pyproject.toml.bak
mv pyproject.toml pyproject.toml.hidden
trap cleanup EXIT  # 确保无论成败都恢复文件
vercel --prod --yes
```

**结果**: 部署成功，每次部署约 13-18 秒。

---

### 经验沉淀

1. **协议迁移要全面**: Kimi Code 从 `openai-compatible` 迁移到 `anthropic-compatible` 时，不仅要改 `api_type` 和 `base_url`，还要检查所有协议相关的特殊处理（如 User-Agent）。
2. **海外部署要考虑节点**: 国内节点的 API 从 Vercel（美国）访问可能超时，代码预设和 trial 配置应使用海外节点（SGP/AMS）。
3. **trial plan 要支持覆盖**: Provider preset 的默认配置不一定适合所有部署环境，trial plan 应支持 `base_url`、`model` 等字段的覆盖。
4. **部署问题要脚本化**: 手动 `mv`/`vercel`/`mv back` 容易出错，应写成带 `trap` 的脚本确保文件恢复。

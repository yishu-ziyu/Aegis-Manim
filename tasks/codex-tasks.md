# Aegis-Manim 开发任务清单（Codex 接入用）

> 本文件是 Aegis-Manim 项目的完整任务清单，供 Codex 读取后接入开发进度。
> 项目采用 Phase-based 推进设计，已完成 Phase 标记为 ✅，当前活跃 Phase 标记为 🔄，待启动 Phase 标记为 ⏳。
> Phase 命名规范：`P{优先级}-{子序号}`，如 P0-A、P1-B。

---

## 项目上下文

### 项目简介
Aegis-Manim 是一个基于 Manim 的教育动画生成器，用户输入 prompt，系统调用 LLM 生成 Manim Python 代码，然后通过外部 Render Backend 渲染为视频。

### 部署信息
- **生产环境**: `https://manim.yishuziyu.cn`
- **部署平台**: Vercel Serverless Functions（Python Runtime）
- **Vercel Region**: Washington, D.C. (iad1)
- **最新部署**: `dpl_GudJxiyL3hcgDjoWSH5kCiDy1aVx`

### 核心链路
```
prompt_intake → llm_code_generation → code_validation → render_execution → video_output → delivery
     (Web UI)      (Provider Layer)     (Precheck)      (Render Backend)    (MP4/Frames)   (Community)
```

### 技术栈
- **Backend**: Python 3.12, Vercel Serverless Functions
- **Frontend**: Vanilla JS + CSS (web_app.py inline), 正在向 React 过渡
- **Render**: 外部 Render Backend (ECS Docker + Manim)
- **Storage**: Supabase (社区作品)
- **LLM Providers**: Kimi Code、MiniMax、DeepSeek、Mimo、Gemini

---

## Provider 配置（当前状态）

| Provider | 协议 | 节点 | Trial Plan | 状态 |
|----------|------|------|-----------|------|
| Kimi Code | anthropic-compatible | `api.kimi.com/coding` | `trial-kimi-priority` | ✅ production_verified |
| MiniMax | anthropic-compatible | `api.minimaxi.com` | `trial-minimax-direct` | ✅ production_verified |
| DeepSeek | openai-compatible | `api.deepseek.com` | (fallback only) | ✅ production_verified |
| Mimo | openai-compatible | `token-plan-cn.xiaomimimo.com` | `trial-mimo-direct` | ✅ production_verified |
| Gemini | openai-compatible | `generativelanguage.googleapis.com` | (vision only) | ✅ production_verified |

---

## 已完成 Phase

### ✅ P0-A: Mimo Timeout 根治

**问题**: Mimo 从 Vercel 访问不稳定，约 50% 请求 timeout fallback 到模板

**修复内容**:
- `api/index.py`: `PUBLIC_TRIAL_MIMO_TIMEOUT_SECONDS` 默认 "120" → "150"
- `vercel.json`: `functions["api/*.py"].maxDuration = 300`
- 部署 `dpl_GudJxiyL3hcgDjoWSH5kCiDy1aVx`

**验证结果**: 连续 5 次 stress test 全部通过，fallback 率 = 0%
- 响应时间范围：27s ~ 101s（均在 150s timeout 内）
- 全部返回 `model: "Mimo 编程试用"`，`codeFile: "vercel-generated-code"`

**相关文件**:
- `api/index.py:92` — timeout 配置
- `vercel.json:6` — maxDuration 配置
- `docs/architecture-v2/codex-phase-p0-mimo-timeout-decision-bdd.md` — BDD 文档
- `docs/issues-and-fixes.md` — 修复记录

---

### ✅ P1-A: Provider 闭环测试自动化

**目标**: 每次部署后自动验证所有 trial provider 的可用性

**实现内容**:
1. `scripts/post_deploy_verify.py` — 部署后验证脚本
   - 测试 3 个 required provider（kimi/minimax/mimo）
   - 验证 `ok=True` + `codeLen>1000` + `not fallback`
   - 测试 1 个 expected failure（deepseek）验证正确拒绝
   - CI 模式：JSON 输出 + 非 0 退出码

2. `.github/workflows/provider-smoke-test.yml` — GitHub Actions workflow
   - 部署成功后自动触发
   - 支持 workflow_dispatch 手动触发

3. `scripts/measure_trial_provider_stability.py` — 增强
   - 增加 `trial-mimo-direct` 到默认 providers
   - 默认 timeout=180（匹配 Mimo 需求）
   - `--ci` 模式：任何 provider 失败或 fallback 率 > 0 时返回非 0

4. `tests/test_post_deploy_verify.py` — 13 个回归测试

**验证结果**:
- 本地运行 `post_deploy_verify.py` 4/4 通过
- pytest 13/13 通过

**相关文件**:
- `scripts/post_deploy_verify.py`
- `.github/workflows/provider-smoke-test.yml`
- `scripts/measure_trial_provider_stability.py`
- `tests/test_post_deploy_verify.py`
- `docs/architecture-v2/codex-phase-p1-provider-loop-test-bdd.md`

---

## 待启动 Phase

### ⏳ P1-B: 代码生成质量评估

**目标**: 建立代码生成成功率的监控和评估体系

**背景**: 当前无法量化各 provider 的生成质量，fallback 情况只有手动测试才能发现

**任务清单**:
- [ ] 在 `api/index.py` 的 generate 响应中增加结构化日志字段（`provider`, `model`, `code_len`, `fallback_reason`, `latency_ms`）
- [ ] 创建 `scripts/measure_generation_quality.py` — 定期运行所有 provider，记录成功率、fallback 率、平均 latency
- [ ] 输出格式：JSON/CSV 便于后续分析
- [ ] 可选：简单 dashboard 或 Slack webhook 告警

**验收标准**:
- [ ] 可以运行脚本获取过去 N 次生成的统计数据
- [ ] 各 provider 的 success rate、fallback rate、latency P50/P95 可量化
- [ ] 有明确的阈值告警（如 fallback rate > 20% 时告警）

**相关文件**:
- `api/index.py` — 日志字段增强
- `scripts/measure_generation_quality.py` — 新文件

---

### ⏳ P2-A: 社区作品系统前端

**目标**: 实现社区作品展示页面，用户可以浏览、搜索、查看他人生成的教学动画

**背景**: Tech Spec 已完成（`docs/TECH_SPEC_COMMUNITY_WORKS.md`），后端 API 已有基础，需要前端实现

**任务清单**:
- [ ] 阅读 `docs/TECH_SPEC_COMMUNITY_WORKS.md` 确认需求
- [ ] 设计社区作品列表页 UI（作品卡片、缩略图、标题、作者、标签）
- [ ] 设计作品详情页 UI（视频播放、代码展示、下载、分享）
- [ ] 实现搜索和筛选功能（按标签、按时间、按热度）
- [ ] 集成 Supabase 社区作品 API
- [ ] 响应式适配（移动端）
- [ ] 添加回归测试

**验收标准**:
- [ ] 社区作品列表页可正常加载并显示作品
- [ ] 作品详情页可播放视频、查看代码
- [ ] 搜索和筛选功能正常工作
- [ ] 移动端布局正常

**相关文件**:
- `docs/TECH_SPEC_COMMUNITY_WORKS.md` — Tech Spec
- `core/web_app.py` — 前端逻辑（当前为 inline JS/CSS）
- `api/index.py` — 社区作品 API endpoint

---

### ⏳ P2-B: Job Persistence 完整实现

**目标**: 实现渲染任务的持久化存储，支持任务查询、状态跟踪、失败重试

**背景**: Tech Spec 已完成（`docs/TECH_SPEC_JOB_PERSISTENCE.md`），但完整实现尚未完成

**任务清单**:
- [ ] 阅读 `docs/TECH_SPEC_JOB_PERSISTENCE.md` 确认设计
- [ ] 实现 render job 状态机（pending → rendering → done/failed）
- [ ] 实现 job 持久化存储（Supabase 或本地文件）
- [ ] 实现 `/api/render/status/{job_id}` 查询接口
- [ ] 实现失败 job 的自动重试机制（最多 3 次）
- [ ] 前端集成：显示 job 状态、进度、错误信息
- [ ] 添加回归测试

**验收标准**:
- [ ] 提交渲染任务后可查询任务状态
- [ ] 任务失败后自动重试最多 3 次
- [ ] 前端可实时查看任务进度
- [ ] 任务状态持久化，页面刷新不丢失

**相关文件**:
- `docs/TECH_SPEC_JOB_PERSISTENCE.md` — Tech Spec
- `api/index.py` — render 相关 endpoint
- `core/web_app.py` — 前端 job 状态展示

---

### ⏳ P2-C: Vision 分析公开化

**目标**: 将图片理解功能从 feature-flag 控制转为公开可用

**背景**: Vision 功能已实现（`/api/vision/analyze`），但受 `AEGIS_VISION_PUBLIC_ENABLED` 控制，前端上传入口隐藏

**任务清单**:
- [ ] 确认 Vision 后端（ECS CLI bridge 或 Gemini）在生产环境稳定
- [ ] 移除或默认开启 `AEGIS_VISION_PUBLIC_ENABLED` feature flag
- [ ] 前端：在首页/生成页增加图片上传入口（上传/粘贴/拖拽）
- [ ] 前端：显示图片分析结果的中文确认卡片
- [ ] 前端：用户确认后将分析结果回填到生成 prompt
- [ ] 添加公开使用的限制（如每日次数、文件大小限制）
- [ ] 添加回归测试

**验收标准**:
- [ ] 非登录用户可看到图片上传入口
- [ ] 上传图片后可看到中文分析卡片
- [ ] 点击"使用这个方向"后正确回填 prompt
- [ ] 整个流程（上传→分析→生成→渲染→视频）端到端可用

**相关文件**:
- `core/vision_analysis.py` — Vision 分析逻辑
- `api/index.py` — `/api/vision/analyze` endpoint
- `core/web_app.py` — 前端 UI
- `scripts/aegis_vision_server.py` — ECS Vision Server（如使用）

---

### ⏳ P2-D: 渲染成功率监控

**目标**: 监控 Render Backend 的健康状态，及时发现和恢复渲染服务故障

**背景**: Render Backend 是外部 ECS 服务，可能因内存、Docker 状态等原因崩溃

**任务清单**:
- [ ] 实现 Render Backend 健康检查端点（已有基础）
- [ ] 创建 `scripts/render_backend_watchdog.py` — 定时检查 Render Backend 健康状态
- [ ] 健康检查失败时自动重启 Docker 容器（通过 SSH 或 API）
- [ ] 记录渲染失败日志，分析失败原因（代码错误、超时、资源不足）
- [ ] 前端显示 Render Backend 状态指示器
- [ ] 可选：Slack/邮件告警

**验收标准**:
- [ ] Render Backend 崩溃后可自动恢复（< 5 分钟）
- [ ] 前端可看到 Render Backend 状态（在线/离线/忙碌）
- [ ] 渲染失败有明确的错误提示（区分代码错误和服务错误）

**相关文件**:
- `scripts/render_backend_watchdog.py` — 新文件（或增强现有）
- `api/index.py` — render 相关 endpoint
- `core/web_app.py` — 前端状态展示

---

### ⏳ P3-A: 前端 React 重构

**目标**: 将现有 Vanilla JS 前端重构为 React 应用

**背景**: 已有 React 实验入口（`Product/web-react/` 或类似），但尚未替换主应用

**任务清单**:
- [ ] 评估现有 React 实验代码状态
- [ ] 设计 React 组件架构（页面级：Home、Generate、Render、Community）
- [ ] 实现核心页面：Home（Prompt 输入）、Generate（代码展示）、Render（视频播放）
- [ ] 集成现有 API（`/api/generate`、`/api/render`、`/api/health`）
- [ ] 保持现有 UI 风格和用户体验
- [ ] 构建并部署到 Vercel
- [ ] 添加 E2E 测试

**验收标准**:
- [ ] React 版本功能与现有版本一致
- [ ] 构建产物可部署到 Vercel
- [ ] E2E 测试覆盖核心用户流程

**相关文件**:
- `Product/web-react/` — React 实验代码（如有）
- `core/web_app.py` — 现有前端逻辑

---

## 关键决策记录（供 Codex 参考）

### 已决策

1. **Mimo timeout**: 150s + maxDuration=300，不降级 ✅
2. **Kimi Code 协议**: 使用 anthropic-compatible，特殊 User-Agent ✅
3. **pyproject.toml 部署**: 使用 `scripts/deploy_vercel.sh` 隐藏 workaround ✅
4. **DeepSeek**: 仅作为 fallback，不开放独立 trial plan ✅
5. **Vision 公开化**: 当前 gated，需后端稳定后才公开 ⏳

### 待决策

1. **P1-B 数据存储**: 代码生成质量日志存储到哪里？（Vercel Logs、Supabase、本地文件？）
2. **P2-A 社区作品审核**: 用户上传作品是否需要审核？
3. **P3-A React 重构优先级**: 是否在 P2 功能完成后再重构？

---

## 常用命令

```bash
# 部署
./scripts/deploy_vercel.sh

# 部署后验证
python3 scripts/post_deploy_verify.py --endpoint https://manim.yishuziyu.cn

# Provider 稳定性测试
python3 scripts/measure_trial_provider_stability.py --runs 3 --ci

# 本地测试
pytest -o addopts='' tests/test_post_deploy_verify.py -q

# 编译检查
python3 -m py_compile api/index.py core/llm_providers.py
```

---

## 项目状态速览

| 链路 | 状态 | 备注 |
|------|------|------|
| Provider Layer | ✅ stable | 4 provider 全部 production_verified |
| Generation Layer | ✅ stable | 代码生成质量良好 |
| Validation Layer | ✅ stable | precheck + compatibility fixes 工作正常 |
| Render Layer | ⚠️ partial | Render Backend 健康监控待完善 |
| Delivery Layer | 🚧 WIP | 社区作品 + Job Persistence 待实现 |

---

*最后更新: 2026-05-29*

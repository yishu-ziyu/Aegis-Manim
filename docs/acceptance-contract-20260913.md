# Aegis 代码简化 + P0 修复 · 验收契约（2026-09-13）

背景：对 core/web_app.py 与全仓库做严格代码审查后，在不改变产品核心功能的前提下实施代码简化 + 明确 bug 修复。
依据 Skill：anthropics/claude-plugins-official code-simplifier + addyosmani/agent-skills code-simplification。
核心纪律：行为严格保持（bug 修复除外且逐条列出）、不动测试、不弱化错误处理、看不懂的代码不拆。

基线行数：web_app.py 4805 / manim_agent.py 792 / llm_providers.py 636 / api/index.py 1645 / app.py 189 / vision_analysis.py 635 / course_menu.py 65。

## Phase 0（core 其余模块与网关，不涉及 web_app.py，无需重启服务）

- H1（P0-1 修复）core/manim_agent.py 补 `import tempfile`；`python3 -c "import ast; ast.parse(open('core/manim_agent.py').read())"` 通过。
- H2（P0-2 修复）core/llm_providers.py zhipu preset 的 default_model 改为 glm-4-flash（从其 models 元组取值，替换复制粘贴来的 "MiniMax-M3"）。
- H3（死代码，grep 验证零调用后删除）：
  - manim_agent.py：`normalize_zhipu_endpoint`、`extract_assistant_text`、`generate_code_with_zhipu`
  - api/index.py：`class handler`（约 1497-1645 行整段）、`generate_manim_code_with_client_provider`（约 1342-1412 行，含 NameError 地雷）、`trial_timeout_seconds` 中 kimi-code/deepseek 死分支
  - llm_providers.py：`extra_openai_payload_for_provider` 函数及其 604 行唯一调用点（恒返回 {}，kimi-code 实际走 anthropic 分支永不触达）
- H4（行为不变简化）app.py 四段「读 body → json.loads → 400」抽公共 helper；download 响应重复 Content-Type 头消除（保留一处）。
- H5（P1-4 修复）vision_analysis.py `_extract_json_object` 第二次 json.loads 加 try，失败时返回 None（与首次解析的失败语义一致）。
- H6 course_menu.py `json.load(open(...))` 改 with 语句。
- H7 静态门槛：`python3 -m py_compile` 通过于所有被改文件；`pytest tests/test_aegis_llm_providers.py tests/test_aegis_manim_knowledge.py tests/test_aegis_vision_analysis.py tests/test_aegis_web_ui.py tests/test_aegis_runtime_compatibility.py -q -o addopts=""` 通过数 ≥ 基线（85+9 vision 中基线通过数），不得新增失败。

## Phase 1（web_app.py + alignment.py + api/index.py 尾随死代码；QA 已结束，允许重启服务验证）

### 修复项（QA bug + 审查 P0）

- F1（BUG-1/P0-1）删除 `toggleCodeBtn` 第二个 click 绑定（原 3871-3877 行 `var tcBtn` 段）；只保留「显示/隐藏代码」语义。第二段 script 若因此变空可整段删除。
- F2（BUG-3+P0-2）失败/终态反馈闭环：生成失败路径（job 轮询终态 failed、form submit catch）必须在状态框显示错误文案（含 requestId/诊断ID，若有）并调用 `stopProcess()` 关闭进度面板；`applyCommunityWork`、`startAutoRender` 终态同样收口。`stopProcess` 不得再是死代码。
- F3（BUG-4）`apiKey` 隐藏必填字段静默拦截提交：去掉其 `required` 属性，改为提交前 JS 校验——所选 provider 需要 key 且为空时，状态框显示中文提示 + 自动展开高级设置 + focus 该输入框。模型服务选择仍持久化（保留），但校验必须可见。
- F4（BUG-7）空 prompt 提交：状态框中文提示「请先输入要讲的概念」并 focus 输入框（当前静默忽略）。
- F5（BUG-5）右栏「诊断入口」文字溢出：加 overflow-wrap/word-break 或收窄，视觉不得超出卡片右缘。
- F6（BUG-6）落地页热门话题缩略图时长徽章叠压标题：调整徽章定位/卡片内边距，标题完整可读。
- F7（BUG-9）core/alignment.py:247 英文降级警告本地化为中文（tests 无断言，已核实）；语义保持「低置信度兜底对齐，教学使用前请人工审阅」。
- F8（BUG-10）「返回编辑」滚动定位被吸顶 header 遮挡：给滚动目标加 `scroll-margin-top`（含 header 高度）。
- F9（P0-3）审阅队列 token 不再进 URL query（3240 行改请求头传递）；`log_message` 对请求行 query 中的 token 类参数（reviewToken/api_key/token/key）做 `***` 脱敏后再落盘。
- F10（P1-4）`var(--success)`/`var(--warn)` 改为 `var(--ok)`/`var(--danger)`。

### 简化项（行为不变）

- S1 死 CSS 删除且活选择器保留：`.pixel-icon`、旧 `.top-bar` 系列（非 `.topbar`）、`.hero` 系列、旧 `body::before` 纸纹、`.lesson-pair` 被覆盖 grid 规则、被夜航覆盖层完全重写的旧浅色硬编码块；同时 grep 确认 `.topbar`、`.landing`、`.go`、`.status-box`、`.process-panel`、`.rtab` 等活选择器仍在。
- S2 删 `SYSTEM_PROMPT` 死变量（56 行）。
- S3 `.env` 双重加载二选一：保留 `load_dotenv`，删自研 `load_env_file`；删后必须验证 AEGIS_GENERATE_TOKEN / AEGIS_ALLOW_TRIAL / provider key 仍能读到（python -c 实测）。
- S4 删 JS 死分支 `cloudUnavailable`（ProviderPreset 无此字段，两处判断恒 false）。
- S5（P2-6）form submit 重置时同步隐藏并复位 `downloadVideoBtn`（避免下载到上一任务视频）。
- S6（P2-7）删除永不显示的 `.go .spinner` 死 UI（CSS + span）。
- S7（P2-8）主 script 顶层的裸 `localStorage.getItem`（2659 行附近）包安全 helper；其余裸调用点顺手套同一 helper，不改变读写语义。
- S8（P2-10）document 级 paste 监听在 vision 未启用时直接 return，不触发 `/api/vision/analyze`。
- S9（Phase 0 尾随死代码，api/index.py）删前 grep 复核零引用：`DISABLED_CLOUD_PROVIDERS`、`validate_cloud_model_endpoint`、`PUBLIC_TRIAL_KIMI_TIMEOUT_SECONDS`/`PUBLIC_TRIAL_DEEPSEEK_TIMEOUT_SECONDS` 及对应 REPAIR 常量、不可达三元分支。

### 明确不做（写入报告「后续建议」）

- BUG-2 作品状态持久化（产品级设计决策，需走原型流程）
- BUG-8 社区服务 502（本地模式部署态问题，仅报告）
- 同步 /api/generate 本地生成体与 run_generate_job 去重（云端网关+外部 curl 在用，需独立验证轮）
- 响应字段瘦身、JOB_STORE 淘汰、Range 流式播放、_read_json_body 上限、日志加锁、render 超时、/api/align 门禁与 trial 支持、P1-2 试用可见性不一致


## A. 硬性门槛（全部 PASS 才 ACCEPT）

- A1 `python3 -m py_compile core/web_app.py` 通过；api/index.py 同样通过。
- A2 测试基线：`python3 -m pytest tests/test_aegis_web_ui.py tests/test_aegis_llm_providers.py tests/test_aegis_manim_knowledge.py tests/test_aegis_runtime_compatibility.py tests/test_aegis_public_trial.py -q -o addopts=""`
  通过数 ≥ 85 且失败集合 = 基线已知的 3 个 test_aegis_public_trial 失败（test_trial_accepts_soft_budget_overage_for_segmented_rendering / test_trial_regenerates_when_generated_code_exceeds_hosted_render_budget / test_two_part_pricing_trial_falls_back_when_model_script_is_too_heavy）。不得新增失败。
- A3 行数：core/web_app.py 总行数 < 4805（基线），目标净减 ≥ 150 行。
- A4 页面可渲染：重启服务后 `curl -s http://127.0.0.1:8000/` 返回 200 且包含关键标记：
  `id="toggleCodeBtn"`、`aegis-theme`、`landing`（落地态 class 或相关样式）、`/api/generate/start`（本地 JS 调用路径未被误改）。
- A5 JS 语法：用 Python 把 `make_index_html()` 输出中所有 `<script>` 块抽取到 /tmp/*.js，`node --check` 全部通过（本机有 node 则必须做）。
- A6 行为回归（curl 实测）：
  - `/api/health` 200 且 ok:true
  - 无 token POST `/api/generate` → 401/403（默认拒绝保持）
  - `GET /api/community/works` 与基线一致即可（2026-09-13 修订：基线代码从未实现该 GET 路由，HEAD 上就是 404，非回归；社区链路以 `/api/community/search` 到达代理层为准）
  - `GET /instant-svg/`（或其 index.html）200
  - `/api/video/<不存在id>` 不 500（404/400 均可）

## B. 修复项验收（每条需在代码中定位到证据）

- B1（P0-1）`toggleCodeBtn` 只剩一个 click 绑定（约 3871 行的 `var tcBtn` 第二段绑定被删除，其中的 works tab 跳转逻辑不得残留）。
- B2（P0-2）`stopProcess` 不再是死代码：生成失败路径（form submit catch/finally）、`applyCommunityWork`、`startAutoRender` 终态至少调用 `stopProcess()` 或 `finishProcess()` 之一；grep 可见 ≥3 个调用点。
- B3（P0-3）审阅队列请求的 token 不再出现在 URL query（3240 行改为请求头传递）；`log_message` 对请求行中的 token 查询参数做脱敏（或 review 队列路径整体不落明文）。
- B4（P1-4）`var(--success)`/`var(--warn)` 全部消除（改用已定义的 `var(--ok)`/`var(--danger)`）。

## C. 简化项验收（行为不变）

- C1 死 CSS 删除且活选择器保留：`.pixel-icon`、`.top-bar`（旧版，非 `.topbar`）、`.hero`、旧 `body::before` 纸纹、`.lesson-pair` 被覆盖的 grid 规则删除；同时 grep 确认 `.topbar`、`.landing`、`.go`、`.status-box`、`.process-panel` 等活选择器仍在。
- C2 `SYSTEM_PROMPT` 死变量删除（56 行）。
- C3 `.env` 双重加载二选一（保留 load_dotenv，删自研 load_env_file，或反之——以不破坏 AEGIS_ALLOW_TRIAL/AEGIS_GENERATE_TOKEN 读取为准，须有 grep 证据两个来源都还能读到）。
- C4 死 JS 分支 `cloudUnavailable` 删除（前后端确认 ProviderPreset 无此字段后）。
- C5 未实施的大项（同步 /api/generate 本地生成体、响应字段瘦身、JOB_STORE 淘汰、Range 流式播放、`_read_json_body` 上限、日志锁）写入报告的「后续建议」，不在本次实施。

## D. 红线（出现即 REJECT）

- D1 改动 tests/ 下任何文件。
- D2 改动 prompts/、scene_registry.json、core/llm_providers.py 的 provider 解析语义。
- D3 删除或改名页面元素 id / API 路由。
- D4 f-string 花括号转义被破坏（make_index_html 输出中出现单花括号 CSS/JS 残留即失败——A4/A5 可捕获）。
- D5 主题切换、落地态→工作台切换、右栏 4 Tabs 任一交互回归（浏览器实测）。

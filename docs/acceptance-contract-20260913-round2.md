# Aegis 优化推进 · 第二轮验收契约（2026-09-13）

依据：docs/qa-review-20260913.md 第四节后续建议（用户已批准按优先级持续推进）。
纪律同第一轮：行为保持（本契约列出的修复除外）、不弱化错误处理、Chesterton's Fence。测试基线：**102 passed / 3 failed**（3 个失败为 test_aegis_public_trial 已知基线）。

## G 项（按优先级）

- G1（BUG-2 作品持久化）：生成成功后 localStorage 持久化 lastWork（prompt/sceneName/requestId/videoId/视频地址/代码文本）；提交时持久化 lastJob（jobId/prompt/startedAt）。刷新或重开页面后：落地页出现「继续上次」入口（夜航风格，复用现有 ghost-btn/landing 样式，无数据时不显示）→ 点击进入工作台并恢复视频+代码；若 lastJob 仍在进行中（<15 分钟）→ 自动恢复轮询等待。所有 localStorage 读写必须走 safeStorage helper（禁存储环境不崩）。UI 走查截图存证。
- G2（BUG-8 退避）：WarmUp ping 失败后指数退避（首败 ≥30s，逐次翻倍，封顶 ≥5 分钟），不再固定间隔刷 502；console 错误量显著下降。
- G3（/api/align 门禁+trial）：加 X-Aegis-Token 门禁（同 /api/generate 标准，前端 fetch 带头）；trial provider 支持——镜像 run_generate_job 的 trial 解析逻辑（trial-minimax-direct 等）；api/index.py 与 app.py 云端路径同步支持（token 头透传）。页面「重新对齐讲稿」在试用入口下可用。
- G9（P1-2 试用一致性）：试用入口仅在本地 key 实际可用时展示（消除「展示但必然失败」）；552/560/563 行 KIMI/DEEPSEEK 死文案清理为实际存在的计划。
- G4（/api/video Range/206）：解析 Range 头，支持 206 + Content-Range + 分块发送（不分块整读）；无 Range 时保持 200 全量。curl 实测 Range 请求。
- G5（内存淘汰）：JOB_STORE 按 TTL（≥2h）+数量上限（≥100）淘汰；VIDEO_CACHE LRU 上限（≥50）；job events 数量封顶（快照取尾部），防长跑膨胀。
- G6（body 上限）：_read_json_body 按端点默认上限（generate/align/community 64KB、render 256KB、vision 沿用既有 MAX_VISION_REQUEST_BYTES=7MB env 可覆盖——2026-09-13 修订：实施者按 Chesterton's Fence 保留既有 7MB 而非放宽 10MB，正确）；payload 非 dict → 400 而非线程异常。
- G7（日志锁）：append_runtime_log/append_bug_log 加 threading.Lock。
- G8（超时）：render_scene 子进程 timeout（默认 600s，env AEGIS_RENDER_TIMEOUT 覆盖）→ 超时归入失败分类；前端 waitForJob 总超时（12 分钟）→ 显示明确错误 + stopProcess。
- G10（precheck 修正）：manim_knowledge.py `"tex" in lowered` 改词边界匹配（\btex\b，"text"/"context" 不再误命中）；截断检测启发式收紧（减少对正常场景的误判），但必须保留 F-043 截断防护能力——在报告/注释中说明权衡。

## 硬性门槛

- H1 py_compile 所有被改文件；api/index 可 import。
- H2 Aegis 套件 ≥102 passed 且失败集 = 已知 3 个基线失败，不得新增失败。
- H3 页面 200；script 块 node --check 全过；f-string 花括号完好。
- H4 curl：/api/health 200；无 token POST /api/generate 401；无 token POST /api/align 401（新门禁）；/api/video Range 请求返回 206 且 Content-Range 正确。
- H5 浏览器回归：落地页/主题/生成主流程/「继续上次」入口/失败提示，全部真实走查。
- H6 红线：不动 prompts/、scene_registry.json、llm_providers provider 解析语义；元素 id 与既有路由不删；G10 以外的生成质量行为不变。

## 实施顺序

WP-A1 = G1,G2,G3,G9（实施者 1）。WP-A2 = G4,G5,G6,G7,G8,G10（实施者 2，串行于 WP-A1，同文件）。清理与 conftest 解耦由主线并行完成。完成后：Explore 再审查 → 浏览器回归 QA → validator 终验。

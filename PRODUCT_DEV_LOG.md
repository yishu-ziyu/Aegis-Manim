# Aegis 产品开发日志（持续更新）

用途：持续记录产品开发每一步，包含时间戳、问题、方案、原因、预防、经验沉淀。  
更新原则：每次功能改动、每次故障排查、每次关键决策都追加一条记录，不覆盖历史。

记录结构：
- 问题现象
- 解决方案
- 方案原因
- 下次识别与避免
- 结果与经验

---

## 2026-02-14 23:10:00 | 项目能力基线确认（CLI + 渲染链路）
- 问题现象: 需要确认项目是否已具备“代码生成可视化视频”基础能力。
- 解决方案: 检查仓库结构、入口脚本、场景注册表并执行最小渲染冒烟。
- 方案原因: 先验证基础链路再做架构升级，避免在错误前提上开发。
- 下次识别与避免: 新项目接手先做三件事：依赖状态、最小可运行路径、核心入口映射。
- 结果与经验: 渲染主链路可用，但有配置一致性问题（后续已修复）。

## 2026-02-14 23:25:00 | P0 修复（注册表类名、clean --force、README）
- 问题现象: 课程菜单存在条目渲染失败；`clean --force`不生效；文档安装指令不一致。
- 解决方案: 修正`scene_registry.json`类名映射；修复`manage_videos.py`对`--force`参数传递；更新README安装指令。
- 方案原因: 这些问题属于“即用即失败”级别，优先级最高，直接影响用户第一体验。
- 下次识别与避免: 增加注册表一致性检查脚本与CLI参数测试，纳入每次发布前检查。
- 结果与经验: P0问题关闭，主流程稳定性明显提升。

## 2026-02-14 23:35:00 | 接入智谱 GLM-5（CLI）
- 问题现象: 原`manim_agent.py`只有模拟模式，无法真实调用模型。
- 解决方案: 接入智谱兼容`chat/completions`请求；支持`.env`和环境变量读取用户Key；补充`--model/--endpoint/--no-render`参数。
- 方案原因: CLI是最小闭环，先把“自然语言->代码->渲染”打通，再扩展到Web。
- 下次识别与避免: 所有模型接入需保留可配置endpoint和清晰错误输出，避免黑盒失败。
- 结果与经验: 具备真实模型调用能力，且可在开源场景下安全交付。

## 2026-02-14 23:41:00 | Web 首版上线（用户输入自己的API Key）
- 问题现象: 目标从CLI升级到Web端，要求用户在页面填写自己的API Key。
- 解决方案: 新增`core/web_app.py`，提供页面、生成API、视频回放API；前端表单支持Key/Prompt/模型参数输入。
- 方案原因: 使用标准库HTTP服务，零新增后端依赖，快速落地并降低开源项目门槛。
- 下次识别与避免: Web端发布前必须验证：健康检查、请求校验、错误回传、移动端显示。
- 结果与经验: Web闭环可运行，已能承载用户自带Key调用。

## 2026-02-15 00:06:00 | 模型调用失败排查与可观测性增强
- 问题现象: 页面仅显示`Model request failed.`，无法定位失败根因。
- 解决方案: 增加详细错误透传（前端显示`error + detail`）；新增Endpoint规范化（自动修正`https://open.bigmodel.cn/api`到完整`/paas/v4/chat/completions`）；新增`logs/web_runtime.log`运行日志。
- 方案原因: 当前最大问题是“可观测性不足”，先让错误可见，才能快速定位是Key问题、Endpoint问题还是模型问题。
- 下次识别与避免: 识别规则：  
  1) 若报401且含“令牌验证不正确”，优先检查Key是否有效；  
  2) 若报404/NOT_FOUND，优先检查Endpoint是否完整；  
  3) 若前端仅报通用错误，先看`logs/web_runtime.log`。
- 结果与经验: 故障定位时间显著缩短；后续可进一步增加“复制诊断信息”按钮提升自助排查效率。

## 2026-02-15 00:07:36 | 模型调用失败可视化与日志化增强（本轮执行）
- 问题现象: 用户在Web端仅看到Model request failed，无法区分是Key无效还是Endpoint错误。
- 解决方案: 补充详细错误透传到前端；新增endpoint自动规范化；写入logs/web_runtime.log运行日志。
- 方案原因: 先提升可观测性，再定位业务问题，能显著降低排障时间。
- 下次识别与避免: 提交前用/api/generate做错误分层测试；若失败先看logs/web_runtime.log中的MODEL_REQUEST_FAIL。
- 结果与经验: 现在可直接看到401令牌错误或404路径错误详情，并可追溯每次请求。

## 2026-02-15 00:49:33 | Render failed 根因追踪与自动兼容修复（本轮）
- 问题现象: Web端仅显示Render failed。排查后发现模型产物混入解释文本导致SyntaxError；即便净化后仍有LaTeX依赖触发和方向常量NameError。
- 解决方案: 新增生成代码净化与语法校验（extract_python_only）；渲染前自动兼容修复（include_numbers=True改False、UP_RIGHT等别名替换）；错误详情与运行日志输出。
- 方案原因: 模型输出存在随机噪声，必须在执行前做静态清洗和环境兼容处理，才能把失败从'黑盒'变成可恢复流程。
- 下次识别与避免: 识别顺序：1) 先看logs/web_runtime.log中的MODEL_REQUEST/RENDER_FAIL；2) 检查generated/*.py是否混入非代码；3) 若报latex缺失，优先检查include_numbers和Tex族调用。
- 结果与经验: 同一失败样本经自动修复后已成功渲染出片；系统具备内部识别+自动降级能力。

## 2026-02-15 12:44:21 | 旧进程未加载修复导致重复失败（本轮）
- 问题现象: 用户再次提交后仍Render failed；日志仅有旧记录，且新生成文件仍包含解释文本导致SyntaxError。
- 解决方案: 核验8000端口进程启动时间并确认是旧进程；重启Web服务加载新逻辑；新增/api/health版本号用于识别是否已加载最新代码。
- 方案原因: 同一报错重复出现时，优先排除'修复未生效'而不是继续改业务逻辑，能减少误判。
- 下次识别与避免: 每次改完后先检查/api/health版本号；若版本未变或日志无新记录，先重启服务再复测。
- 结果与经验: 服务已重启到web_app_v20260215_3；清洗+兼容修复逻辑已生效，后续可通过版本号快速确认。

## 2026-02-15 13:09:13 | Web前端视觉重构（frontend-design）
- 问题现象: 原界面信息密度和视觉记忆点不足，用户主观反馈为‘丑’，且品牌辨识不强。
- 解决方案: 重做make_index_html设计系统：更换字体组合（Bungee/Noto Serif SC/JetBrains Mono）、重建配色与排版、增强动效和状态层级、加入警告提示区与复制代码按钮。
- 方案原因: 在不改后端接口的前提下提升可用性与品牌感，先解决‘是否想用’的问题，再迭代更深功能。
- 下次识别与避免: 后续每次前端迭代都遵循固定审查：视觉方向明确、移动端适配、焦点可访问、错误状态可读。
- 结果与经验: 新版页面已上线并通过健康检查，功能保持兼容，交互反馈更清晰。

## 2026-02-15 13:23:20 | Web 服务启动失败排查（127.0.0.1:8000 refused）
- 问题现象: 用户 curl /api/health 返回 connection refused；后台 nohup 启动后没有监听，日志初始为空。
- 解决方案: 复现后台启动命令并抓取 /tmp/aegis_web_live.log，定位为 nohup 使用 python 命令失败（python: No such file or directory）；改为 ./.venv/bin/python 启动后恢复监听；新增 scripts/web_server.sh 统一 start/stop/status，自动选择解释器并输出日志位置。
- 方案原因: 连接拒绝通常是服务未启动而非业务接口错误。先确认端口监听，再看启动日志可快速缩小范围。用脚本固化启动流程可避免环境差异（python vs python3）导致的重复故障。
- 下次识别与避免: 下次先执行 lsof -iTCP:8000 -sTCP:LISTEN + curl /api/health 判断是否为进程级故障；使用 ./scripts/web_server.sh start 代替手写 nohup；若启动失败立即查看 /tmp/aegis_web_live.log。
- 结果与经验: 已确认根因是解释器命令不兼容，不是接口代码问题；服务可稳定启动并通过健康检查，README 已更新操作方式。

## 2026-02-16 01:22:20 | 专用 Bug 诊断链路建设（requestId + 结构化日志）
- 问题现象: 浏览器只展示错误显化结果，用户难以准确复述上下文，远程排障沟通成本高。
- 解决方案: 新增 logs/bug_trace.jsonl 结构化日志（stage/severity/requestId/context）；/api/generate 全链路返回 requestId；新增 /api/bugs/recent?limit=N 查询接口与 core/bug_report.py 读取脚本；前端结果面板新增 Req 标签并在状态中展示诊断ID。
- 方案原因: 把口头描述转成可检索的请求级证据，定位时可直接按 requestId 关联 validation/model/render 各阶段。
- 下次识别与避免: 后续遇到报错先记录页面诊断ID，再用 /api/bugs/recent 或 python core/bug_report.py --limit 20 查询；避免仅凭截图猜测。
- 结果与经验: 现在每次失败都能被结构化记录并可按 requestId 回放上下文，协作排障效率显著提升。

## 2026-02-16 01:24:09 | Bug日志按诊断ID精确过滤
- 问题现象: 仅看最近日志会混入其他请求，仍需人工筛选，协作时可能误判。
- 解决方案: 为 /api/bugs/recent 增加 requestId 查询参数；为 core/bug_report.py 增加 --request-id 过滤参数。
- 方案原因: 请求级过滤可以把同一问题上下文固定到一条链路，显著降低噪声。
- 下次识别与避免: 排障时先从页面拿到诊断ID，再使用 requestId 过滤查询，避免按时间猜测。
- 结果与经验: 现在可通过单个ID精准取回对应错误记录，截图+ID即可完成高效协作。

## 2026-02-22 01:24:08 | README 文档优化（结构与可执行性）
- 问题现象: 用户反馈 README 陈旧且信息密度分布不均，部分章节与当前功能状态不匹配，首次上手路径不够直接。
- 解决方案: 重构 README：按定位-能力-结构-快速开始-排障-常见问题重排；统一命令到 .venv/python 与 web_server.sh；补充 requestId 诊断链路和 API 查询示例；更新路线图为下一阶段真实计划。
- 方案原因: 文档应优先服务可执行落地和排障效率，减少新用户阅读成本与误操作。
- 下次识别与避免: 后续每次功能变更后同步更新 README 的对应章节（命令、接口、日志、FAQ），并在发版前做一轮可执行性校验。
- 结果与经验: README 与当前项目实现保持一致，使用和排障路径更清晰，适合对外开源展示。

## 2026-02-28 08:43:00 | 项目开发日志总览文档建立
- 问题现象: 当前仅有流水式日志，缺少一份适合对外协作阅读的阶段总览文档。
- 解决方案: 新增 PROJECT_DEVELOPMENT_LOG.md，按目标-里程碑-问题复盘-当前状态-下一步计划组织内容。
- 方案原因: 将细粒度记录和阶段总结分层管理，可兼顾开发追踪与对外沟通效率。
- 下次识别与避免: 后续每次里程碑变更同步更新总览日志，每次排障细节继续写入 PRODUCT_DEV_LOG.md。
- 结果与经验: 项目现在具备‘流水日志 + 总览日志’双轨记录体系，便于团队协作和开源展示。

## 2026-05-05 14:18:07 | 本地 Codex CLI 接入与 Manim 语法知识层建设
- 问题现象: Web 端选择 `Codex / 本地 OpenAI-Compatible 代理` 时请求 `http://127.0.0.1:8317/api/provider/antigravity/v1` 失败，页面显示 `Model request failed ... Connection refused`。进一步判断后发现 8317 是旧本地代理路径，当前机器没有对应服务监听；即使模型通道打通，生成质量仍取决于模型是否熟悉 Manim 官方语法、本地版本差异和社区成熟写法。
- 解决方案: 参考 `interview-copilot` 的实现，将本机 `codex login` 登录态作为独立 provider 接入 Aegis：新增 `codex-cli` provider，后端通过 `codex -a never exec --ephemeral --ignore-rules --sandbox read-only --output-last-message ...` 调用本地 Codex CLI，不再依赖 8317 HTTP 代理，也不需要页面填写 API Key 或 Base URL。随后新增 `prompts/manim_knowledge_pack.md`，把本地 ManimCE `0.19.2`、`docs/source`、官方文档/示例和高信号测试样例中的稳定语法整理为可维护知识包，并通过 `load_system_prompt()` 注入 CLI 与 Web 两条生成链路。
- 方案原因: `interview-copilot` 已证明“本地 Codex CLI 登录态”比临时 HTTP 代理更适合单机演示和开发者工具原型；而 Manim 生成失败的主要风险不是只有模型可达性，还包括 API 版本漂移、LaTeX 环境缺失、文本/坐标轴重叠、使用过期别名等。把知识层做成版本控制的 prompt 片段，比一次性口头提示更可维护，也能让 Web、CLI、Codex CLI 三条入口共用同一套约束。
- 下次识别与避免: 若出现 `127.0.0.1:8317 connection refused`，先判断是否选择了旧的 `codex-local-proxy`；本机优先选择 `Codex CLI 登录态（本机）/ codex-cli`。若出现渲染失败，先看 `requestId` 对应的 `logs/web_runtime.log` 和 `logs/bug_trace.jsonl`，再检查生成代码是否违反 `prompts/manim_knowledge_pack.md` 中的稳定写法。更新官方文档或升级 Manim 时，必须同步复核知识包中的目标版本与 API 约束。
- 结果与经验: 已完成 `core/llm_providers.py`、`core/web_app.py`、`core/manim_agent.py`、`prompts/manim_knowledge_pack.md`、`tests/test_aegis_prompt_context.py`、`README.md` 等改动。验证通过：`ruff` 全绿；相关测试 `18 passed`；`compileall core` 通过；真实 Web 请求 `provider=codex-cli` 生成并渲染成功，requestId 为 `20260505-141202-0070da25`，生成文件为 `generated/scene_20260505_141304_36aedd54.py`，视频为 `media/videos/scene_20260505_141304_36aedd54/480p15/GeneratedScene.mp4`。

## 2026-05-05 14:38:02 | 文字生命周期与遮挡问题修复
- 问题现象: 生成视频中前后出现的说明文字可能停留在同一区域，旧文字没有及时退出，导致新旧文字互相遮挡。
- 解决方案: 在 `prompts/system_prompt.md` 新增 `Text Lifecycle` 硬约束，要求临时说明文字在下一段进入前 `FadeOut` 或使用 `ReplacementTransform` 替换；在 `prompts/manim_knowledge_pack.md` 补充“阶段文字成组管理、段落边界清场、同一区域禁止叠写”的 Manim 写法；在 `tests/test_aegis_prompt_context.py` 增加断言锁定这些 prompt 规则。
- 方案原因: 这是生成策略层面的视觉质量问题，渲染器不会自动知道哪些旧文字已经过期。把文字生命周期写入 prompt 和知识包，比事后从任意 Python 代码中猜测删除对象更稳定。
- 下次识别与避免: 若视频出现遮挡，先检查生成代码中同一区域是否连续 `Write(Text(...))` 但缺少 `FadeOut`、`ReplacementTransform` 或成组 `FadeOut(section_group)`；后续新增模板时必须把临时说明文字保存为变量或 `VGroup`。
- 结果与经验: 新 prompt 会要求旧文字段在合适时机退出界面，保留坐标轴、前沿曲线等持久视觉锚点，同时清理过期解释文本，降低教学视频的信息遮挡。

## 2026-05-05 17:16:46 | 大模型接入方法论沉淀
- 问题现象: 当前已经完成智谱、OpenAI-Compatible、MiniMax、本地 8317 代理与 Codex CLI 登录态等多条模型接入路径，但经验分散在代码、README 和排障日志中，后续新增 Provider 容易重复踩 Key、Endpoint、代理进程、输出解析和 Manim 知识不足的问题。
- 解决方案: 新增 `docs/aegis_llm_integration_methodology.md`，把 Aegis 的 ProviderPreset 抽象、三类认证通道、OpenAI-Compatible 适配边界、requestId 可观测性、Manim 知识层、生成代码后处理、失败诊断清单和新 Provider 接入模板整理为项目方法论；同时补充 LiteLLM、LangChain、Vercel AI Gateway、Ollama、Continue、OpenAI Structured Outputs 与 Key 安全实践作为外部参考。README 的 Provider 章节增加该方法论文档入口，并在 `/Users/mahaoxuan/Desktop/AI产品经理/大模型接入方法论与Aegis开发日志.md` 保留跨项目沉淀版。
- 方案原因: 模型接入的核心风险不是单次 API 调通，而是长期可维护性：Provider 可替换、认证不混乱、错误可诊断、输出可解析、领域知识可迭代。把方法论固化到仓库文档，能让后续接入本地模型、聚合网关或新厂商时按同一清单推进。
- 下次识别与避免: 新增 Provider 前先按方法论文档中的模板补齐 preset、认证来源、endpoint 规范化、no-render 验证、最小 render 验证和日志证据；遇到 `connection refused`、`401/403`、`404`、渲染失败时按诊断清单定位，不要直接归因于 prompt 或 Key。
- 结果与经验: 项目库现在有一份可演进的大模型接入方法论，既记录本机 Codex/8317/Manim 经验，也吸收开源工具的 provider abstraction、fallback、local OpenAI-compatible、structured output 和 key safety 思路。

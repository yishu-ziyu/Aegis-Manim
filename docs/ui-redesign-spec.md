# Aegis UI 重设计规范 · 温润手帐风 × Apple Design

> 状态：设计定稿，待实施。
> 方向：用户已选定「温润手帐风」（ManimCat 同源）。
> 本规范融合三处来源：ManimCat 前端代码（色彩/字体基底）、`apple-design` Skill（动效与排版准则）、`emil-design-eng` Skill（组件细节与动效决策框架）。

---

## 1. 设计原则

1. **响应优先**：所有反馈发生在 pointer-down 而不是 click；按钮按下瞬间就有 `scale(0.97)`。
2. **克制动效**：动效有频率门槛——高频操作（提交、开关）近乎无动效；入场动画只属于"首次/罕见"层级。宁可不动，不为好看而动。
3. **简单 ≠ 极简**：常用路径放第一屏，高级选项收一层，而不是全部铺出来（当前 UI 的核心病灶）。
4. **材质表达层级**：半透明 + blur 用于悬浮层（吸顶工具条），实色面板承载内容；轻材质不叠轻材质。
5. **看不见的细节会复利**：圆角、缓动、focus ring、换行省略……单项无人注意，总和就是"说不上来的舒服"。

## 2. 设计 Tokens（可直接替换 `core/web_app.py` `:root` 块）

```css
:root {
  /* ── 字体 ── */
  /* 霞鹜文楷 Screen：CDN 引入，见 §3 */
  --font-ui: "LXGW WenKai Screen", "LXGW WenKai", "PingFang SC", "Songti SC", serif;
  --font-mono: "JetBrains Mono", "SF Mono", Consolas, monospace; /* 仅代码区 */

  /* ── 色彩 · iOS 暖色系 ── */
  --bg: #f2f2f7;               /* 页面底 */
  --bg-card: #fffdf8;          /* 奶白卡片 */
  --bg-fill: #e9e9ee;          /* 三级填充（chips、滑轨） */
  --ink: #1c1c1e;              /* 主文字（不用纯黑） */
  --text-2: rgba(60, 60, 67, 0.62);   /* 次级 */
  --text-3: rgba(60, 60, 67, 0.42);   /* 辅助 */
  --accent: #2f6cb3;           /* 填充按钮/链接（保证白字对比度） */
  --accent-soft: #78b4f0;      /* focus ring、tint、选中态 */
  --accent-tint: rgba(120, 180, 240, 0.16);
  --brand: #1b365d;            /* 藏青：仅 hero 标题/logo 锚点，不再做按钮色 */
  --danger: #b3563e;
  --ok: #3f7a5a;
  --code-bg: #2a2a33;          /* 暖炭黑，替代突兀纯黑 */
  --border: rgba(60, 60, 60, 0.12);
  --border-strong: rgba(60, 60, 60, 0.22);

  /* ── 形状 ── */
  --radius-sm: 10px;           /* 输入框、按钮 */
  --radius: 16px;              /* 卡片、面板 */
  --radius-pill: 999px;

  /* ── 阴影（蓝灰基调，不用纯黑） ── */
  --shadow-sm: 0 1px 2px rgba(37, 55, 84, 0.05), 0 4px 16px rgba(37, 55, 84, 0.06);
  --shadow-md: 0 16px 42px rgba(37, 55, 84, 0.10);

  /* ── 动效（数值来自 apple-design / emil-design-eng，不许另造） ── */
  --ease-out: cubic-bezier(0.23, 1, 0.32, 1);        /* 入场、交互 */
  --ease-soft: cubic-bezier(0.22, 1, 0.36, 1);       /* 首屏入场（ManimCat 同款） */
  --ease-drawer: cubic-bezier(0.32, 0.72, 0, 1);     /* 折叠展开 */
  --dur-fast: 150ms;           /* hover、按压反馈 */
  --dur-ui: 220ms;             /* 下拉、折叠、状态切换 */
  --dur-enter: 560ms;          /* 仅首屏首次入场 */
}
```

**移除项**：`--sans: var(--serif)` 自指（当前无衬线变量直接指向衬线体）、网格纸纹理 `body::before`（换 §5 的干净底色 + 可选微噪点）、纯黑代码块、uppercase 等宽标签。

## 3. 字体与排版（apple-design §15）

- 全站单一声音：霞鹜文楷 Screen。引入方式：
  `@import url('https://cdn.jsdelivr.net/npm/lxgw-wenkai-screen-webfont@1.1.0/style.css');`
  （ManimCat 同款 CDN；离线环境退化到 PingFang/宋体，可后续自托管。）
- 字号阶梯：正文 **15px**（当前 14px 偏小）、次级 13px、辅助 12px、hero 标题 `clamp(1.8rem, 3vw, 2.4rem)`。
- **字距随字号变化，禁止全站一个值**：大标题 `-0.01em ~ -0.02em`；正文 `0`；小号 CJK 标签不做 uppercase（对中文无效，只让 "API Key/TEMPERATURE" 变得突兀）。
- 行高与字号反向：标题 1.15，正文 1.6。
- 层级 = 字重 + 字号 + 行高三件套，不靠颜色硬拉。
- 表单标签：13px、`--text-2`、中文自然语气（"模型服务" 而不是 "PROVIDER"），帮助文字 12px `--text-3`。

## 4. 动效规范

### 4.1 决策顺序（animate Skill 硬规则，按序执行，不许跳步）

1. **该不该动？** 按频率：每天上百次 → 永远不动；几十次/天 → 近乎不可觉或不动；偶尔（弹层、状态）→ 标准动效；首次/罕见 → 唯一允许"惊喜预算"的地方。
2. **目的**：反馈 / 空间一致性 / 状态指示 / 避免跳变 / 解释 / 惊喜（仅罕见层级）。说不出目的就不做。
3. **曲线与时长**：只从 §2 tokens 里取，禁止现场发明贝塞尔。
4. **工具**：最便宜的能用就行。**不装动效库**，纯 CSS。

### 4.2 元素级 Motion Budget（本项目的逐项裁决）

| 元素 | 动？ | 目的 | 规格 |
| --- | --- | --- | --- |
| 首屏面板/字段入场 | ✅ | 首次入场 | `--dur-enter` + `--ease-soft`，opacity 0→1 + translateY(12px) + scale(0.992→1)，字段 stagger 40–60ms |
| 按钮/可按压元素 | ✅ | 反馈 | `:active { transform: scale(0.97) }`，`--dur-fast` `--ease-out`；pointer-down 即刻生效 |
| 状态条文字更新 | ✅ | 状态指示 | transition 200ms 交叉淡化；状态切换时可加 `filter: blur(2px)` 过渡掩盖双状态叠影 |
| 生成进度步骤 | ✅ | 状态指示 | 步骤点亮/打勾 transition `--dur-ui`；spinner 转快一点（0.8s linear）——感知加载更快 |
| 视频出现 | ✅ | 避免跳变 | 250ms fade + scale(0.98→1)，transform-origin center（类模态，居中合法） |
| 作品卡片 hover | ✅（微） | 高频层级 → 近乎不可觉 | 仅阴影抬升 `--dur-fast`，无位移无缩放；`@media (hover: hover) and (pointer: fine)` 门控 |
| 高级设置折叠 | ✅ | 避免跳变 | `--dur-ui` `--ease-drawer`，grid-template-rows 0fr→1fr 或等价；不做 height+margin 全套 |
| 错误/提示 toast | ✅ | 空间一致性 | 从哪个方向进出同一条路；**出场快于入场**（入 250ms / 出 150ms） |
| 表单提交瞬间的按钮 | ❌ 近无 | 高频 | 仅 ：active 反馈，不加额外动效 |

### 4.3 硬规则（code review 时逐条对照）

- 只动 `transform` 和 `opacity`；不碰 width/height/margin/top。
- 动态 UI（状态条、进度、提示）用 **transition 不用 @keyframes**——transition 可中断可重定向；keyframes 中断归零。（首屏一次性入场可以用 keyframes。）
- 禁止 `scale(0)` 起步：从 `scale(0.95)` + `opacity: 0` 开始——现实世界没有东西从无中生有。
- 禁止 `ease-in` 做入场；禁止 `transition: all`。
- 入场出 seasons 同路径、同方向（空间一致性）；菜单/浮层 transform-origin 指向触发它的元素。
- stagger 间隔 30–80ms，且不阻塞交互。

## 5. 布局与信息层级

**第一屏 = 产品价值，不是配置表单。**

```
┌────────────────────────────────────────────┐
│  Aegis 经济学动画工作台          [主题][GitHub]│ ← 吸顶，backdrop blur 半透明
│  把一道题、一张图、一段文字，变成可播放的教学动画 │
│  [示例:税收楔子] [示例:拉弗曲线] [示例:比较优势]  │ ← 点击即填入
├────────────────────────────────────────────┤
│  ┌─────────────┐  ┌──────────────────────┐ │
│  │ 你想讲清楚    │  │  视频区（空态：柔和插画  │ │
│  │ 什么问题？    │  │  + 提示语，不是黑块）    │ │
│  │ [textarea]  │  │  作品仓库 · 同步讲稿    │ │
│  │ [生成动画]   │  │  （Tab，而不是三块平铺） │ │
│  │ ▸ 高级设置   │  │                      │ │
│  └─────────────┘  └──────────────────────┘ │
│  诊断: /api/health · v0.1.0        ← 页脚微字 │
└────────────────────────────────────────────┘
```

- **高级设置默认折叠**：Provider、API Key、模型、场景类名、Temperature、Base URL、调试开关全部收进 `<details>`。默认可见的只有：问题输入框 + 生成按钮。
- 诊断入口裸 URL → 页脚 12px 微字或 ⓘ 图标。
- 右栏"视频 / 作品仓库 / 同步讲稿"用 Tab 组织，减少同屏面板数。
- 视频空态设计成产品的一部分：柔和底色 + 一句话 + 示例按钮，杜绝黑块。
- 背景纹理：网格纸纹理移除；保留纯 `--bg` 或极淡噪点（opacity ≤ 0.03）。

## 6. 组件细节清单（Before / After）

| Before（现状） | After（目标） | Why |
| --- | --- | --- |
| 按钮无 `:active` 态 | `:active { scale(0.97) }` 150ms | 按下瞬间要有反馈，接口在"听" |
| `--sans: var(--serif)` | 单一字族 `--font-ui`，mono 只进代码区 | 消除字体系统自相矛盾 |
| 标签 uppercase mono 小字 | 13px 中文自然语气标签 | uppercase 对 CJK 无效，混排突兀 |
| 米色底上米白卡片、8px 圆角 | `#f2f2f7` 上 `#fffdf8` 卡片、16px 圆角 + 柔影 | 拉开层次，圆角是暖感的来源 |
| "公开作品优先复用"按钮竖排折行 | `white-space: nowrap` + 文案缩短 | 折行是 craft 事故 |
| 诊断裸 URL 文本 | 页脚微字 / ⓘ tooltip | 用户不需要看见排障主键 |
| 纯黑代码块 | `--code-bg #2a2a33` 暖炭黑 + 圆角 | 和暖色页面共存而不是打架 |
| 虚线上传框 + 裸 file input | 点击/拖拽整卡 + 图标 + 一句说明 | 上传是功能不是表单项 |
| 全部动效 200ms 单一 ease | §4.2 分层 tokens | 一刀切的 timing 没有性格 |
| 聚焦 ring `#E4ECF5` | `0 0 0 3px var(--accent-tint)` + `:focus-visible` | 键盘导航可见性 + 品牌色一致 |

## 7. 可访问性（随动效一起交付，不做事后补丁）

```css
@media (prefers-reduced-motion: reduce) {
  * { animation-duration: 0.2s !important; transition-duration: 0.2s !important; }
  .shell, .field { transform: none !important; }  /* 位移/缩放全部退化为交叉淡化 */
}
@media (prefers-reduced-transparency: reduce) {
  .topbar { background: var(--bg-card); backdrop-filter: none; }
}
```

- hover 动效一律 `@media (hover: hover) and (pointer: fine)` 门控。
- 全站对比度：正文 `--ink` on `--bg-card` ≥ 7:1；次级文字 ≥ 4.5:1。

## 8. 落地阶段

| 阶段 | 内容 | 改动范围 | 效果占比 |
| --- | --- | --- | --- |
| Phase 1 | §2 tokens 全量替换 + §3 字体 CDN + 圆角/阴影 | `make_index_html()` 的 `<style>` 块头部 | ~70% 观感 |
| Phase 2 | §5 布局重构（高级设置折叠、Tab 化、空态）+ §6 组件逐项 | HTML 结构 + 少量 JS | ~25% |
| Phase 3 | §4 动效全套 + §7 可访问性 + 暗色主题变量接口（ManimCat RGB-triplet 结构） | CSS 为主 | 收尾 ~5% |

约束：不引入前端框架/构建链（保持单文件 stdlib 服务架构），不装动效库，不改后端逻辑。

## 9. 验收方法

1. 实现次日"新鲜眼"复查（emil 惯例）：慢放 2–5 倍逐个过动效，DevTools Animations 面板逐帧看属性是否同步。
2. 对照 `review-animations` Skill 跑一次 diff 评审。
3. 真机过一遍：手机 Safari 触控 + 键盘 Tab 走查 `:focus-visible`。
4. 系统开启"减弱动态效果"后全功能可用。

# Aegis Instant SVG

Instant SVG 是 Aegis-Manim 的轻量教学可视化模式，来自原 `yishu-svg` 项目。

它解决的是“先快速出一张能动、能改、能下载的教学图”的需求；和 Aegis-Manim 的 Manim Video 模式互补：

- `Instant SVG`：浏览器内生成、预览、编辑、下载动态 SVG，适合草图、讲义插图、课堂演示和快速验证表达。
- `Manim Video`：生成 Manim 代码并渲染视频，适合更完整的教学短片和作品沉淀。

## 当前能力

- 纯前端单页应用，打开 `index.html` 即可运行。
- 支持 Manim、时间轴、极简、艺术四种风格提示。
- 支持数学、物理、神经网络、历史时间轴和经济学模板。
- 调用智谱 GLM 或 NVIDIA NIM 生成 animated SVG。
- 支持预览、查看代码、手动编辑、复制代码和下载 `.svg`。
- 保留示例 SVG 和系统提示词，作为后续 prompt grammar / renderer adapter 的资产。

## 运行方式

```bash
open apps/instant-svg/index.html
```

首次使用需要在页面右上角配置自己的 API Key。Key 只保存在浏览器本地 `localStorage`，不会写入仓库。

## 文件结构

```text
apps/instant-svg/
├── index.html
├── js/app.js
├── prompts/svg-animator-system.md
├── examples/
│   ├── quadratic-function.svg
│   ├── neural-network.svg
│   └── economics/
│       ├── supply-demand.svg
│       ├── cost-curves.svg
│       └── is-lm-model.svg
└── PRD.md
```

## 后续方向

Instant SVG 不应发展成第二个孤立产品。它在 Aegis-Manim 中的长期位置是：

1. 作为快速 SVG renderer，承接“秒级教学图”需求。
2. 抽取 `prompts/svg-animator-system.md` 中的规则，进入统一 prompt library。
3. 与 `motion-grammar` 的 scene schema / style tokens 对齐，形成 renderer-agnostic 的教学动画规格。
4. 未来按同一主题同时沉淀 SVG 示例和 Manim Video 示例。

原独立仓库：<https://github.com/yishu-ziyu/yishu-svg>

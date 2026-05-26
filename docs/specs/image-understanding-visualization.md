# 图片理解到 Manim 可视化规格

日期：2026-05-26

## 1. 目标

为 Aegis-Manim 增加一个图片输入能力：用户上传、粘贴或拖拽一张经济学学习图片后，AI 先理解图片内容，生成中文理解卡片和可视化方案；用户确认或补充修改后，再进入现有 Manim 代码生成和渲染链路。

第一版目标是完整闭环，而不是只停留在图片分析：

1. 图片输入。
2. Kimi 视觉理解。
3. 中文理解卡片。
4. 用户确认或补充方向。
5. 生成中文 Manim prompt。
6. 复用现有 `/api/generate` 生成代码。
7. 复用阿里云渲染后端生成视频。

## 2. MVP 边界

第一版聚焦“经济学考研题和教学图示”，图片作为理解输入，不作为视频素材复刻。

支持：

- 中文经济学考研题截图。
- 教材图、供需曲线、IS-LM、AD-AS、无差异曲线、预算线、成本曲线等图示。
- 公式推导、手写板书、课堂截图。
- 图片加可选文字要求。

暂不支持：

- 任意照片美化。
- 照图复刻。
- 图片转短视频特效。
- PDF 整页上传。
- 多图批量上传。
- 摄像头实时取景器。
- Word、PPT、Excel 附件解析。

手机端可通过系统上传入口选择拍照或相册，不单独实现网页内实时拍摄器。

## 3. 用户流程

1. 用户在首页主流程上传、粘贴或拖拽一张图片。
2. 前端展示图片预览、大小状态和隐私提示。
3. 用户可选输入一句文字要求。
4. 用户点击“分析图片”。
5. 后端调用 Kimi 做图片理解。
6. 前端展示中文理解卡片。
7. 用户可点击“展开分析”查看可审计分析。
8. 用户点击“按这个方向生成”，或在自由文本框里补充修改方向后生成。
9. 前端把确认后的结构化摘要和用户补充说明合成最终 prompt。
10. 现有生成和渲染流程继续执行。

## 4. 理解卡片

默认展示内容：

- 图片类型。
- 核心内容中文概括。
- 关键元素。
- 建议可视化方案。
- 不确定点。
- 输出风格：中文考研讲解动画。

“展开分析”展示的是可审计分析，不展示模型原始内部思考链：

- 识别依据。
- 元素定位。
- 可能歧义。
- 生成取舍。

## 5. 接口契约

新增后端接口建议：

- `POST /api/vision/analyze`

请求 JSON：

```json
{
  "image": {
    "mime": "image/png",
    "data": "base64-without-data-url-prefix"
  },
  "user_instruction": "可选中文补充要求",
  "locale": "zh-CN"
}
```

响应 JSON：

```json
{
  "ok": true,
  "analysis": {
    "image_type": "economics_exam_question",
    "recognized_content": "中文概括图片内容",
    "key_elements": ["变量、曲线、公式、题干条件"],
    "uncertainties": [],
    "visualization_plan": [
      "第1步动画",
      "第2步动画",
      "第3步动画"
    ],
    "recommended_prompt": "确认后交给 Manim 代码生成模型的中文提示词",
    "auditable_analysis": {
      "recognition_basis": "为什么这样判断",
      "element_mapping": "识别到的图文元素如何对应到经济学概念",
      "generation_tradeoffs": "为什么建议这样可视化"
    }
  },
  "requestId": "..."
}
```

失败响应必须可恢复：

```json
{
  "ok": false,
  "error": "图片文字较模糊，请裁剪题目区域或重新拍照。",
  "category": "image_unclear",
  "requestId": "..."
}
```

建议错误类别：

- `image_too_large`
- `unsupported_image_type`
- `image_unclear`
- `not_economics_content`
- `vision_provider_unavailable`
- `vision_provider_unsupported`
- `vision_provider_timeout`
- `invalid_vision_response`

## 6. Provider 策略

第一版只用现有 Kimi 套餐能力做图片理解，不增加新的付费模型供应商。Kimi Code 会员能力优先通过真实服务器 CLI 登录态复用，而不是伪造 HTTP 客户端身份。

原则：

- 图片理解固定走 Kimi。
- 优先在云服务器安装真实 Kimi/Codex/Claude CLI，并通过 `KIMI_VISION_CLI_COMMAND` 调用终端里的读图能力。
- Aegis 默认提供 `scripts/kimi_vision_cli_bridge.py` 作为 wrapper，后端固定传 `{image_path}` 和 `{prompt_path}`，wrapper 再调用真实 `kimi --quiet -p ...`。
- wrapper 默认按 Kimi 形态调用，但支持 `KIMI_VISION_CLI_ARGS_JSON` 覆盖参数数组；如果服务器上实际能读图的是 Codex 或 Claude CLI，只改 `KIMI_VISION_CLI_BINARY`、`KIMI_VISION_CLI_ARGS_JSON` 和 `KIMI_VISION_IMAGE_TOKEN_TEMPLATE`。
- Aegis 默认提供 `scripts/probe_kimi_vision_cli.py` 作为服务器验收探针；它必须拿一张真实中文经济学图片跑通真实 CLI 后，才允许把 `AEGIS_VISION_PUBLIC_ENABLED` 改成 `1`。
- 如果后续拿到正式视觉 API，再用 `KIMI_VISION_API_KEY` / `MOONSHOT_API_KEY` 作为云端 API 通道。
- 生产入口受 `AEGIS_VISION_PUBLIC_ENABLED` 控制；服务器真实 CLI 读图验收通过前保持关闭，前端入口隐藏，后端路由返回 disabled。
- `KIMI_CODE_API_KEY` 只作为现有代码生成链路的尝试项，不把网页 HTTP 请求伪装成 IDE/CLI。
- 不要求用户填写自己的 API Key。
- 不新增默认付费供应商。
- 代码生成仍可继续使用现有免费试用链：Kimi 优先，失败后 DeepSeek / MiniMax 备用。

最大不确定性：

- 云服务器上的真实 Kimi/Codex/Claude CLI 是否能稳定接受图片路径输入，需要先实测并固化命令模板。
- 当前 Kimi Code / Kimi 套餐 HTTP 端点是否支持 `image_url` 或等价的图片消息输入，需要先实测；如果返回权限错误，不继续用伪造客户端身份绕过。

服务器探针命令：

```bash
cd /opt/aegis/Aegis-Manim
python3 scripts/probe_kimi_vision_cli.py \
  --image /opt/aegis/vision-test.png \
  --binary kimi \
  --report /opt/aegis/kimi-vision-probe-report.json
```

如果真实可用 CLI 不是 Kimi 形态，可以用参数数组模板探测，例如：

```bash
python3 scripts/probe_kimi_vision_cli.py \
  --image /opt/aegis/vision-test.png \
  --binary codex \
  --args-json '["exec","--image","{image_path}","{prompt}"]' \
  --report /opt/aegis/codex-vision-probe-report.json
```

这里的 `--args-json` 不是固定方案，而是把真实 CLI 的非交互参数形态显式化。需要根据服务器上 `kimi` / `codex` / `claude` 的实际帮助信息调整，直到探针能证明它真的读到了图片。

通过标准：

- `ok` 为 `true`。
- 返回内容包含中文经济学术语。
- `recommended_prompt` 非空且可直接进入 Aegis-Manim 生成。
- 如果 CLI 看不到图片，探针必须失败，不能打开生产入口。

3-5 张图片的整链路验收命令：

```bash
python3 scripts/production_vision_economics_acceptance.py \
  /opt/aegis/acceptance-images/is-lm.png \
  /opt/aegis/acceptance-images/ad-as.png \
  /opt/aegis/acceptance-images/monopoly.png \
  --base-url https://manim.yishuziyu.cn \
  --jsonl /opt/aegis/vision-economics-acceptance.jsonl
```

默认会执行 `图片 -> /api/vision/analyze -> /api/generate -> /api/render -> status -> MP4/frame`。如果只想先隔离读图接口，用 `--skip-render`。

降级规则：

1. 实测成功：图片功能对公测用户开放。
2. 接口可连但不稳定：标记为实验功能，只内部或白名单开放。
3. 实测失败：生产站隐藏图片入口，保留探针和诊断结论，不公开一个必然失败的上传入口。

## 7. 上传限制

第一版限制：

- 一次只允许 1 张图。
- 支持 `PNG`、`JPG`、`JPEG`、`WebP`。
- 前端压缩最长边到 2000px 以内。
- 前端压缩目标大小约 2.5MB。
- 后端硬限制 5MB。
- 超过限制时先尝试自动压缩；自动压缩仍失败，再提示用户裁剪或重新截图。

隐私提示：

```text
图片仅用于本次 AI 理解，不会作为公开视频素材或长期保存。
```

## 8. 数据与日志

第一版不长期保存用户原图。

允许记录：

- requestId。
- 图片 MIME 类型。
- 压缩后字节数。
- 图片类别。
- 成功或失败类别。
- 理解卡片摘要。
- 生成 job id 或 render job id。

禁止记录：

- base64 原图。
- 用户图片文件本体。
- 模型原始隐藏推理。
- API Key。

如果用户明确授权某张图片作为公开样例，再单独提交到样例资产中。

## 9. Prompt 合成

确认后进入 `/api/generate` 的 prompt 应传压缩后的结构化摘要，而不是传原图。

包含：

- 用户原始文字要求。
- 图片类型。
- 核心内容概括。
- 关键元素。
- 用户确认后的可视化方向。
- 不确定点。
- 中文可视化规则。

不包含：

- 原图。
- 大段 OCR 全文堆叠。
- 完整可审计分析。
- 模型原始内部思考。

语言规则：

- 理解卡片全部用中文。
- 动画标题、步骤、结论全部用中文。
- 保留必要变量符号：`P`、`Q`、`Y`、`i`、`IS`、`LM`、`MC`、`MR`。
- 英文题目先翻译为中文考研语境后可视化。
- 不确定 OCR 内容必须显式标出。

## 10. 失败恢复

如果图片理解失败：

- 看不清：提示裁剪题目区域或重新拍照。
- 非经济学内容：提示补充说明想可视化什么。
- 方向不确定：展示不确定点，让用户确认。
- 保留“仍然按我的文字要求生成”入口。

如果图片理解成功但 Manim 生成或渲染失败：

- 保留理解卡片。
- 保留用户补充说明。
- 显示错误和诊断 ID。
- 提供“重新生成动画”按钮。
- 不重复调用图片理解，除非用户点“重新分析图片”。

## 11. 验收标准

第一轮测试使用 5 类中文经济学考研图片：

1. 供需曲线 / 税收楔子图。
2. IS-LM 或 AD-AS 曲线移动。
3. 消费者选择 / 无差异曲线 + 预算线。
4. 成本曲线 / 完全竞争厂商短期均衡。
5. 纯文字题截图，要求 AI 自己提炼可视化路线。

通过标准：

- 5 张测试图里至少 4 张能正确生成理解卡片。
- 至少 3 张能成功进入 Manim 生成并渲染出视频。
- 生成视频中文字不乱码。
- 理解卡片必须为中文。
- 失败时不能白屏、卡死或让用户不知道下一步。
- 如果现有 Kimi Key 读图失败，则功能不公开上线。

## 12. 实现顺序

1. 写最小 Kimi 图片理解探针，分别验证 HTTP 端点、`scripts/kimi_vision_cli_bridge.py` 和服务器真实 CLI 读图能力。
2. 新增 `/api/vision/analyze`，优先走 `KIMI_VISION_CLI_COMMAND`，其次走正式视觉 API。
3. 前端加入上传、粘贴、拖拽、手机拍照上传入口。
4. 前端加入理解卡片、展开分析、自由文本补充和确认生成。
5. 将确认后的摘要接入现有 `/api/generate`。
6. 用 5 类测试图片跑完整闭环。
7. 按测试结果决定公开、实验开放或隐藏入口。

## 13. 非目标

第一版不做：

- 多图分析。
- 图片长期存储。
- 用户图库。
- 原图嵌入最终视频。
- 实时摄像头组件。
- 独立视觉模型供应商采购。
- 对所有 provider 暴露图片能力。
- 结构化字段逐项编辑。

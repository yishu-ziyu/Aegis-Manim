# Dual Coding Lesson Workspace Design

## Context

Aegis-Manim currently turns natural-language prompts into Manim code and rendered teaching videos. The next product step is not only better rendering, but a stronger learning experience based on dual-coding theory: students should see the visual process while also reading the language that explains what the visual process means.

ManimCat is a useful reference for productization: it has a richer workbench, task state, problem framing, modify-and-rerender flows, and a more complete frontend. Aegis should borrow the ideas that improve the learning loop without copying ManimCat's full React + Redis + Agent Studio architecture in the first version.

## Product Goal

Build a first version of a synchronized teaching workspace:

- The left side shows the generated Manim video.
- The right side shows a paragraph-level teaching script and outline.
- Video playback time highlights the matching script paragraph.
- Clicking a script paragraph seeks the video to the matching time range.
- The user can regenerate the alignment when the script does not match the video well enough.

The first version uses paragraph-level synchronization. Sentence-level or subtitle-level synchronization is explicitly deferred, but the data model must allow that later extension.

## Quality Principle

The MVP may be lightweight, but it must not trade away teaching quality for implementation convenience.

This means:

- Alignment quality is a product requirement, not a cosmetic extra.
- The system must show uncertainty instead of pretending weak alignment is exact.
- Users must be able to inspect and correct alignment.
- Failed or low-confidence alignment should degrade visibly and honestly.
- The architecture must leave a clear path to stronger alignment methods such as extracted-frame verification and vision-model calibration.

## Chosen Architecture: C-lite Post-hoc Metadata Alignment

The chosen first-version architecture is post-hoc alignment based on available metadata.

The system first generates and renders the Manim video. After the video exists, it builds an alignment between video time ranges and explanatory script paragraphs. The first implementation does not require full video understanding. Instead, it uses signals that Aegis can obtain cheaply and reliably:

- The original user prompt.
- The generated Manim code.
- The Scene class name.
- The order of `play(...)` and `wait(...)` calls.
- Explicit `run_time` values when present.
- Render result metadata such as the final video URL and observed duration.
- Render logs and retry information when useful.

An LLM then receives a compact alignment prompt and returns structured `alignment.segments[]`.

## Data Model

The first-version response should extend the current generation result with an `alignment` object:

```json
{
  "videoUrl": "/video/...",
  "code": "from manim import *\n...",
  "alignment": {
    "mode": "posthoc_metadata",
    "confidence": "medium",
    "warnings": [],
    "segments": [
      {
        "id": "seg_1",
        "title": "建立直觉",
        "script": "这一段先用图形展示问题的基本结构，让学生把文字描述和画面对象对应起来。",
        "visualIntent": "展示初始对象、坐标或变量关系。",
        "startTime": 0,
        "endTime": 18,
        "confidence": "medium"
      }
    ]
  }
}
```

Segment fields:

- `id`: stable client-side identifier.
- `title`: outline heading.
- `script`: teaching narration paragraph.
- `visualIntent`: concise description of what the video should show.
- `startTime` / `endTime`: seconds in the rendered video.
- `confidence`: `low`, `medium`, or `high`.

Future extension:

```json
{
  "sentences": [
    {
      "text": "逐句讲稿",
      "startTime": 3.2,
      "endTime": 6.8
    }
  ]
}
```

The first version should not require `sentences`.

## Backend Components

### Alignment Signal Extractor

Responsibility: turn generated Manim code and render metadata into compact alignment signals.

Inputs:

- User prompt.
- Generated code.
- Scene name.
- Video duration if known.
- Render attempt metadata.

Outputs:

- Ordered event list.
- Estimated timing blocks.
- Code summary for the alignment prompt.

The extractor should use Python AST where practical, with conservative fallback to regex for Manim call detection. It should avoid executing user-generated code.

### Alignment Generator

Responsibility: call the configured LLM to produce paragraph-level alignment JSON.

Inputs:

- Original prompt.
- Alignment signals.
- Render metadata.
- Generated code summary.

Outputs:

- Validated `alignment` object.

Quality rules:

- Segment time ranges must be non-overlapping and ordered.
- Segment time ranges must stay within video duration when duration is known.
- Empty or invalid LLM output must return a visible alignment error, not fabricated success.
- If timing is estimated rather than grounded in explicit `run_time` or duration data, confidence should not be `high`.

### Alignment Validator

Responsibility: normalize and check model output before it reaches the UI.

Validation rules:

- At least one segment is required.
- `startTime < endTime` for every segment.
- Segments are sorted by `startTime`.
- Overlaps are either corrected conservatively or reported as warnings.
- Unknown duration allows estimated ranges, but the response must include a warning.

## Frontend Workspace

First-version layout:

- Main video panel.
- Script/outline side panel.
- Collapsible generated code and render log panel.

Interactions:

- Video `timeupdate` selects the active segment.
- Clicking a segment seeks to `segment.startTime`.
- Active segment is visually highlighted.
- Low-confidence segments show a subtle warning state.
- A "重新对齐讲稿" action can rerun alignment without rerendering the video.
- A "重新渲染视频" action keeps the existing Aegis render retry path.

## What To Borrow From ManimCat

Borrow now:

- Problem framing as an optional planning stage before generation.
- A visible task state model for generating, rendering, aligning, failed, and completed states.
- Modify-and-rerender as a product pattern.
- Workbench-style layout instead of a simple form-only page.

Defer:

- Full React + Redis + Bull migration.
- Plot Studio.
- Long-lived Agent Studio.
- Full video-understanding alignment.

## Non-goals For First Version

- No sentence-level subtitle timing.
- No automatic voiceover generation.
- No speech recognition input.
- No full ManimCat architecture migration.
- No hard dependency on a vision model.
- No manual timeline editor beyond click-to-seek and rerun alignment.

## Risks

### Alignment May Be Plausible But Wrong

Mitigation: expose confidence and warnings; support rerun alignment; avoid claiming exactness when signals are weak.

### Generated Code May Not Contain Useful Timing Signals

Mitigation: estimate from video duration and ordered visual steps; mark confidence lower; later prompt the code generator to include better timing structure.

### UI May Feel Like Decoration Instead Of Learning Support

Mitigation: make script paragraphs explain the visual meaning, not merely describe what appears on screen.

### Lightweight Backend Could Become Hard To Maintain

Mitigation: keep alignment extractor, generator, and validator separate from `core/web_app.py` request plumbing.

## Acceptance Criteria

- A generated video result can include an `alignment.segments[]` array.
- The UI highlights the current segment while the video plays.
- Clicking a segment seeks the video.
- Low-confidence or failed alignment is visible to the user.
- Alignment can be regenerated without rerendering the video.
- The implementation keeps paragraph-level sync independent from future sentence-level sync.

## Open Implementation Decisions

- Whether video duration is read from ffprobe, Manim metadata, or browser metadata in the first implementation.
- Whether problem framing is introduced in the same milestone or immediately after the alignment MVP.
- Whether manual segment editing is added in the first version or deferred until after playback sync is proven.

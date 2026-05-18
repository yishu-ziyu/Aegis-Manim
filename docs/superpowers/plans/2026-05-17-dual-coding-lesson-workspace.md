# Dual Coding Lesson Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add a first C-lite dual-coding workspace where rendered Manim videos are post-hoc aligned to paragraph-level teaching scripts.

**Architecture:** Keep Aegis' current lightweight Python web server. Add a separate `core/alignment.py` module for signal extraction, LLM/deterministic alignment generation, and validation; integrate it into `core/web_app.py`; extend the existing single-page UI with a script/outline panel driven by `alignment.segments[]`.

**Tech Stack:** Python 3.11+, stdlib `ast`/`json`, existing provider adapter in `core/manim_agent.py`, existing `ThreadingHTTPServer` UI, `unittest`/`pytest`.

---

## File Structure

- Create `core/alignment.py`: extract Manim timing signals, build alignment prompts, parse/validate alignment JSON, and produce honest low-confidence fallback alignments when LLM alignment fails.
- Create `tests/test_aegis_alignment.py`: unit tests for signal extraction, validation, fallback quality warnings, and JSON normalization.
- Modify `core/web_app.py`: return `alignment` after successful render, expose `/api/align`, add script panel UI, and wire video playback to segment highlighting.
- Modify `docs/superpowers/specs/2026-05-17-dual-coding-lesson-workspace-design-preview.html`: optional only if the design preview needs to reflect final behavior; skip unless implementation changes the architecture.
- Modify `docs/superpowers/plans/2026-05-17-dual-coding-lesson-workspace.md`: keep checkboxes current during execution.

## Task 1: Alignment Core

**Files:**
- Create: `core/alignment.py`
- Test: `tests/test_aegis_alignment.py`

- [x] **Step 1: Write failing tests for Manim signal extraction**

```python
def test_extract_alignment_signals_orders_play_and_wait_calls() -> None:
    code = """
from manim import *

class GeneratedScene(Scene):
    def construct(self):
        self.play(Create(Circle()), run_time=2)
        self.wait(0.5)
        self.play(FadeOut(Circle()))
"""
    signals = alignment.extract_alignment_signals(
        code=code,
        scene_name="GeneratedScene",
        video_duration=None,
    )

    assert signals["sceneName"] == "GeneratedScene"
    assert [event["kind"] for event in signals["events"]] == ["play", "wait", "play"]
    assert signals["events"][0]["startTime"] == 0
    assert signals["events"][0]["endTime"] == 2
    assert signals["events"][1]["startTime"] == 2
    assert signals["events"][1]["endTime"] == 2.5
    assert signals["events"][2]["startTime"] == 2.5
    assert signals["events"][2]["endTime"] == 3.5
```

- [x] **Step 2: Run the extraction test and confirm it fails**

Run: `./.venv/bin/python -m pytest tests/test_aegis_alignment.py::AegisAlignmentTest::test_extract_alignment_signals_orders_play_and_wait_calls -q`

Expected: FAIL because `core/alignment.py` does not exist yet.

- [x] **Step 3: Implement `extract_alignment_signals`**

Create `core/alignment.py` with an AST visitor that:

- Parses generated Manim code without executing it.
- Visits calls in source order.
- Treats `self.play(...)` as `kind="play"` and uses `run_time=<number>` when present, otherwise `1.0`.
- Treats `self.wait(<number>)` as `kind="wait"`, otherwise `1.0`.
- Builds ordered `startTime` / `endTime` ranges.
- Scales ranges to `video_duration` when known.
- Returns warnings instead of raising on syntax errors.

- [x] **Step 4: Run the extraction test and confirm it passes**

Run: `./.venv/bin/python -m pytest tests/test_aegis_alignment.py::AegisAlignmentTest::test_extract_alignment_signals_orders_play_and_wait_calls -q`

Expected: PASS.

## Task 2: Alignment Validation And Quality Gates

**Files:**
- Modify: `core/alignment.py`
- Modify: `tests/test_aegis_alignment.py`

- [x] **Step 1: Write failing tests for validation and honest fallback**

```python
def test_validate_alignment_marks_estimated_timing_as_not_high_confidence() -> None:
    raw = {
        "mode": "posthoc_metadata",
        "confidence": "high",
        "warnings": ["Timing estimated from metadata."],
        "segments": [
            {
                "id": "seg_1",
                "title": "建立直觉",
                "script": "解释画面中的初始关系。",
                "visualIntent": "展示初始对象。",
                "startTime": 0,
                "endTime": 10,
                "confidence": "high",
            }
        ],
    }

    normalized = alignment.validate_alignment(raw, video_duration=12, timing_is_estimated=True)

    assert normalized["confidence"] == "medium"
    assert normalized["segments"][0]["confidence"] == "medium"
    assert any("estimated" in warning.lower() for warning in normalized["warnings"])


def test_build_fallback_alignment_is_visible_low_confidence() -> None:
    signals = {"duration": 20, "events": [], "warnings": ["No play/wait calls found."]}

    fallback = alignment.build_fallback_alignment(
        prompt="解释税收楔子如何导致无谓损失",
        scene_name="GeneratedScene",
        signals=signals,
    )

    assert fallback["confidence"] == "low"
    assert fallback["segments"][0]["startTime"] == 0
    assert fallback["segments"][0]["endTime"] == 20
    assert fallback["warnings"]
```

- [x] **Step 2: Run validation tests and confirm they fail**

Run: `./.venv/bin/python -m pytest tests/test_aegis_alignment.py -q`

Expected: FAIL until validation helpers exist.

- [x] **Step 3: Implement `validate_alignment` and `build_fallback_alignment`**

Rules:

- Required top-level fields: `mode`, `confidence`, `warnings`, `segments`.
- Confidence is one of `low`, `medium`, `high`.
- Estimated timing cannot return `high`.
- Segments must be sorted, non-overlapping, and have `startTime < endTime`.
- Invalid segment text gets a concise fallback title/script.
- Empty alignment becomes a low-confidence fallback with visible warnings.

- [x] **Step 4: Run validation tests and confirm they pass**

Run: `./.venv/bin/python -m pytest tests/test_aegis_alignment.py -q`

Expected: PASS.

## Task 3: Backend Generation Integration

**Files:**
- Modify: `core/web_app.py`
- Modify: `core/alignment.py`
- Test: `tests/test_aegis_alignment.py`

- [x] **Step 1: Add tests for LLM JSON parsing without a network call**

```python
def test_parse_alignment_json_extracts_fenced_json() -> None:
    text = '''```json
{"mode":"posthoc_metadata","confidence":"medium","warnings":[],"segments":[{"id":"seg_1","title":"直觉","script":"解释直觉。","visualIntent":"显示对象。","startTime":0,"endTime":5,"confidence":"medium"}]}
```'''

    parsed = alignment.parse_alignment_json(text)

    assert parsed["segments"][0]["title"] == "直觉"
```

- [x] **Step 2: Implement alignment generation helper**

Add `generate_alignment(...)` in `core/alignment.py`:

- Build a compact prompt from prompt, scene name, signals, and code excerpt.
- Call an injected `llm_call` when provided for tests.
- In production, `core/web_app.py` can pass a wrapper around `generate_code_with_llm`.
- Parse JSON via `parse_alignment_json`.
- Validate output.
- On LLM failure, return `build_fallback_alignment(...)` with warning that alignment generation failed.

- [x] **Step 3: Wire successful render responses**

In `core/web_app.py`, after `videoId` is registered:

- Extract signals from `last_code`.
- Generate `alignment`.
- Add `alignment` to the JSON response.
- Log `ALIGNMENT_OK` or `ALIGNMENT_FALLBACK`.

- [x] **Step 4: Add `/api/align`**

Add a POST endpoint that accepts:

```json
{
  "prompt": "...",
  "code": "...",
  "sceneName": "GeneratedScene",
  "videoDuration": 42.3,
  "provider": "zhipu",
  "apiKey": "...",
  "model": "glm-5",
  "baseUrl": "...",
  "endpoint": "..."
}
```

It returns:

```json
{
  "ok": true,
  "alignment": { "mode": "posthoc_metadata", "segments": [] }
}
```

- [x] **Step 5: Run targeted tests**

Run: `./.venv/bin/python -m pytest tests/test_aegis_alignment.py tests/test_aegis_runtime_compatibility.py -q`

Expected: PASS.

## Task 4: Frontend Workspace Panel

**Files:**
- Modify: `core/web_app.py`

- [x] **Step 1: Add result panel markup**

Add a visible script panel next to or below the video area:

- `alignmentPanel`
- `alignmentSummary`
- `alignmentList`
- `realignBtn`

- [x] **Step 2: Add CSS for quality states**

Add styles:

- `.alignment-panel`
- `.segment-card`
- `.segment-card.active`
- `.segment-card.low-confidence`
- `.segment-time`
- `.alignment-warning`

Low-confidence state must be visually distinct but not alarming unless alignment fails.

- [x] **Step 3: Add frontend state and rendering functions**

Add JavaScript functions:

- `setAlignment(alignment)`
- `renderAlignment()`
- `findActiveSegment(currentTime)`
- `seekToSegment(segment)`
- `clearAlignment()`

- [x] **Step 4: Wire video playback**

Add listeners:

- `videoPlayer.addEventListener("timeupdate", ...)`
- `videoPlayer.addEventListener("loadedmetadata", ...)`

The active segment must update during playback, and clicking a segment must set `videoPlayer.currentTime`.

- [x] **Step 5: Wire regenerate alignment**

The "重新对齐讲稿" button posts to `/api/align` using the latest prompt/code/scene/video duration/provider settings. It updates only the alignment panel and does not rerender the video.

## Task 5: Verification And Commit

**Files:**
- Modify: `docs/superpowers/plans/2026-05-17-dual-coding-lesson-workspace.md`

- [x] **Step 1: Run Python tests**

Run: `./.venv/bin/python -m pytest tests/test_aegis_alignment.py tests/test_aegis_runtime_compatibility.py tests/test_aegis_prompt_context.py -q`

Expected: PASS.

- [x] **Step 2: Compile changed Python files**

Run: `./.venv/bin/python -m py_compile core/alignment.py core/web_app.py`

Expected: exit code 0.

- [x] **Step 3: Start local server**

Run: `./scripts/web_server.sh start`

Expected: `Aegis Web running at http://127.0.0.1:8000` or existing status indicates it is running.

- [x] **Step 4: Browser smoke test**

Open `http://127.0.0.1:8000` and verify:

- Page loads.
- Alignment panel is visible.
- Generating with `noRender=true` still works and clears alignment.
- A completed render response with alignment displays script segments.

- [x] **Step 5: Commit with Lore format**

Commit only implementation files and this plan:

```text
Build synchronized lesson alignment for Aegis videos

Constraint: Keep the first version on Aegis' lightweight Python Web path while preserving visible alignment quality gates.
Rejected: Full ManimCat-style platform migration | too broad for the first dual-coding learning loop.
Confidence: high
Scope-risk: moderate
Directive: Do not hide low-confidence alignment; warnings and rerun alignment are part of the product contract.
Tested: ./.venv/bin/python -m pytest tests/test_aegis_alignment.py tests/test_aegis_runtime_compatibility.py tests/test_aegis_prompt_context.py -q; ./.venv/bin/python -m py_compile core/alignment.py core/web_app.py; local browser smoke test
Not-tested: Full production deployment and long generated videos if not exercised during this implementation pass.
Co-authored-by: OmX <omx@oh-my-codex.dev>
```

## Execution Review

- Implemented `core/alignment.py` with AST timing extraction, JSON parsing, validation, quality downgrades for estimated timing, and visible low-confidence fallback output.
- Integrated render-time alignment and `/api/align` in `core/web_app.py`; rendered videos now attempt paragraph-level script alignment after `videoId` registration.
- Added real video duration probing through `ffprobe` when available, so post-hoc timing can scale to the rendered MP4 instead of relying only on estimated Manim durations.
- Added the synchronized teaching-script panel in the Web UI with warning display, active segment highlighting, segment click-to-seek, and "重新对齐讲稿" without rerendering video.
- Verified with:
  - `./.venv/bin/python -m pytest tests/test_aegis_alignment.py tests/test_aegis_runtime_compatibility.py tests/test_aegis_prompt_context.py -q`
  - `./.venv/bin/python -m py_compile core/alignment.py core/web_app.py`
  - `curl -s http://127.0.0.1:18011/api/health`
  - `curl -s -X POST http://127.0.0.1:18011/api/align ...`
  - `browser-harness` real-browser load check for `#alignmentPanel` and `#realignBtn`
- Remaining gap: full end-to-end render with a paid external model/provider was not run in this pass; the fallback and UI behavior were verified locally without external model spend.

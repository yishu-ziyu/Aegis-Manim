from __future__ import annotations

import ast
import json
import re
from typing import Any, Callable

CONFIDENCE_LEVELS = {"low", "medium", "high"}
DEFAULT_EVENT_DURATION = 1.0
DEFAULT_FALLBACK_DURATION = 30.0


def _round_time(value: float) -> float:
    rounded = round(value, 3)
    if rounded == int(rounded):
        return int(rounded)
    return rounded


def _number_from_node(node: ast.AST | None) -> float | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.USub)
        and isinstance(node.operand, ast.Constant)
        and isinstance(node.operand.value, (int, float))
    ):
        return -float(node.operand.value)
    return None


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _duration_for_call(node: ast.Call, kind: str) -> float:
    if kind == "play":
        for keyword in node.keywords:
            if keyword.arg == "run_time":
                value = _number_from_node(keyword.value)
                if value is not None and value > 0:
                    return value
        return DEFAULT_EVENT_DURATION

    if kind == "wait":
        if node.args:
            value = _number_from_node(node.args[0])
            if value is not None and value > 0:
                return value
        for keyword in node.keywords:
            if keyword.arg in {"duration", "run_time"}:
                value = _number_from_node(keyword.value)
                if value is not None and value > 0:
                    return value
        return DEFAULT_EVENT_DURATION

    return DEFAULT_EVENT_DURATION


class _ManimCallVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.calls: list[ast.Call] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        name = _call_name(node)
        if name in {"play", "wait"}:
            self.calls.append(node)
        self.generic_visit(node)


def extract_alignment_signals(
    *,
    code: str,
    scene_name: str,
    video_duration: float | None,
) -> dict[str, Any]:
    warnings: list[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return {
            "sceneName": scene_name,
            "duration": video_duration,
            "events": [],
            "warnings": [f"Could not parse generated code for alignment: {exc.msg}."],
        }

    visitor = _ManimCallVisitor()
    visitor.visit(tree)

    events: list[dict[str, Any]] = []
    cursor = 0.0
    for index, call in enumerate(visitor.calls, start=1):
        kind = _call_name(call) or "event"
        duration = _duration_for_call(call, kind)
        start_time = cursor
        end_time = cursor + duration
        events.append(
            {
                "index": index,
                "kind": kind,
                "duration": _round_time(duration),
                "startTime": _round_time(start_time),
                "endTime": _round_time(end_time),
                "line": getattr(call, "lineno", None),
            }
        )
        cursor = end_time

    if not events:
        warnings.append("No Manim play/wait calls found; alignment timing will be estimated.")

    estimated_duration = cursor if cursor > 0 else None
    duration = video_duration if video_duration and video_duration > 0 else estimated_duration
    if events and video_duration and video_duration > 0 and estimated_duration and estimated_duration > 0:
        scale = video_duration / estimated_duration
        if abs(scale - 1) > 0.01:
            warnings.append("Scaled extracted Manim timing to the rendered video duration.")
            for event in events:
                event["startTime"] = _round_time(float(event["startTime"]) * scale)
                event["endTime"] = _round_time(float(event["endTime"]) * scale)
                event["duration"] = _round_time(float(event["endTime"]) - float(event["startTime"]))

    return {
        "sceneName": scene_name,
        "duration": _round_time(duration) if duration is not None else None,
        "events": events,
        "warnings": warnings,
    }


def _normalize_confidence(value: Any, *, maximum: str = "high") -> str:
    candidate = str(value or "medium").strip().lower()
    if candidate not in CONFIDENCE_LEVELS:
        candidate = "medium"
    order = {"low": 0, "medium": 1, "high": 2}
    if order[candidate] > order[maximum]:
        return maximum
    return candidate


def _clean_text(value: Any, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned or fallback


def validate_alignment(
    raw: dict[str, Any],
    *,
    video_duration: float | None,
    timing_is_estimated: bool,
) -> dict[str, Any]:
    warnings = []
    if isinstance(raw.get("warnings"), list):
        warnings = [str(item).strip() for item in raw["warnings"] if str(item).strip()]

    maximum_confidence = "medium" if timing_is_estimated else "high"
    if timing_is_estimated and not any("estimated" in warning.lower() for warning in warnings):
        warnings.append("Timing is estimated from metadata and should be reviewed.")

    normalized_segments: list[dict[str, Any]] = []
    previous_end = 0.0
    segments = raw.get("segments") if isinstance(raw.get("segments"), list) else []
    for index, segment in enumerate(segments, start=1):
        if not isinstance(segment, dict):
            warnings.append(f"Skipped invalid segment {index}.")
            continue

        try:
            start_time = float(segment.get("startTime"))
            end_time = float(segment.get("endTime"))
        except (TypeError, ValueError):
            warnings.append(f"Skipped segment {index} with invalid time range.")
            continue

        if video_duration is not None and video_duration > 0:
            start_time = max(0.0, min(start_time, video_duration))
            end_time = max(0.0, min(end_time, video_duration))
        if start_time < previous_end:
            warnings.append(f"Adjusted overlapping segment {index}.")
            start_time = previous_end
        if end_time <= start_time:
            warnings.append(f"Skipped segment {index} with empty time range.")
            continue

        segment_confidence = _normalize_confidence(
            segment.get("confidence"),
            maximum=maximum_confidence,
        )
        normalized_segments.append(
            {
                "id": _clean_text(segment.get("id"), f"seg_{len(normalized_segments) + 1}"),
                "title": _clean_text(segment.get("title"), f"教学段落 {len(normalized_segments) + 1}"),
                "script": _clean_text(segment.get("script"), "这一段解释当前画面背后的概念含义。"),
                "visualIntent": _clean_text(segment.get("visualIntent"), "对应当前视频画面中的主要变化。"),
                "startTime": _round_time(start_time),
                "endTime": _round_time(end_time),
                "confidence": segment_confidence,
            }
        )
        previous_end = end_time

    if not normalized_segments:
        fallback_duration = video_duration if video_duration and video_duration > 0 else DEFAULT_FALLBACK_DURATION
        warnings.append("Alignment output had no valid segments; produced a review-required fallback.")
        normalized_segments.append(
            {
                "id": "seg_1",
                "title": "待检查讲解段落",
                "script": "系统暂时只能给出整段视频级别的讲解占位，请重新对齐或人工检查。",
                "visualIntent": "覆盖当前生成视频的整体教学意图。",
                "startTime": 0,
                "endTime": _round_time(fallback_duration),
                "confidence": "low",
            }
        )
        maximum_confidence = "low"

    top_confidence = _normalize_confidence(raw.get("confidence"), maximum=maximum_confidence)
    if any(segment["confidence"] == "low" for segment in normalized_segments):
        top_confidence = "low"

    return {
        "mode": "posthoc_metadata",
        "confidence": top_confidence,
        "warnings": warnings,
        "segments": normalized_segments,
    }


def build_fallback_alignment(
    *,
    prompt: str,
    scene_name: str,
    signals: dict[str, Any],
    extra_warning: str | None = None,
) -> dict[str, Any]:
    duration = signals.get("duration")
    if not isinstance(duration, (int, float)) or duration <= 0:
        duration = DEFAULT_FALLBACK_DURATION

    warnings = ["Generated low-confidence fallback alignment; please review before using it for teaching."]
    for warning in signals.get("warnings", []):
        if str(warning).strip():
            warnings.append(str(warning).strip())
    if extra_warning:
        warnings.append(extra_warning)

    return {
        "mode": "posthoc_metadata",
        "confidence": "low",
        "warnings": warnings,
        "segments": [
            {
                "id": "seg_1",
                "title": f"{scene_name} 整体讲解",
                "script": (
                    "这一段对应整段生成视频。系统没有足够可靠的时间信号来细分讲稿，"
                    f"请检查它是否准确回应了：{_clean_text(prompt, '用户问题')}"
                ),
                "visualIntent": "覆盖整段视频的主要可视化过程。",
                "startTime": 0,
                "endTime": _round_time(float(duration)),
                "confidence": "low",
            }
        ],
    }


def _strip_json_fence(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def parse_alignment_json(text: str) -> dict[str, Any]:
    cleaned = _strip_json_fence(text)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Alignment response did not contain a JSON object.")
    parsed = json.loads(cleaned[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Alignment response JSON must be an object.")
    return parsed


def _build_alignment_prompts(
    *,
    prompt: str,
    code: str,
    scene_name: str,
    signals: dict[str, Any],
) -> tuple[str, str]:
    system_prompt = (
        "You align a rendered Manim teaching video with a Chinese teaching outline. "
        "Return only strict JSON. Do not include markdown."
    )
    code_excerpt = code[:5000]
    user_prompt = json.dumps(
        {
            "task": "Create paragraph-level posthoc_metadata alignment for a teaching video.",
            "qualityRules": [
                "Explain the concept behind the visuals, not just what appears on screen.",
                "Use low or medium confidence when timing is estimated.",
                "Keep segments ordered and non-overlapping.",
                "Return Chinese title/script/visualIntent unless the user prompt is clearly non-Chinese.",
            ],
            "schema": {
                "mode": "posthoc_metadata",
                "confidence": "low|medium|high",
                "warnings": ["string"],
                "segments": [
                    {
                        "id": "seg_1",
                        "title": "string",
                        "script": "string",
                        "visualIntent": "string",
                        "startTime": 0,
                        "endTime": 1,
                        "confidence": "low|medium|high",
                    }
                ],
            },
            "prompt": prompt,
            "sceneName": scene_name,
            "signals": signals,
            "codeExcerpt": code_excerpt,
        },
        ensure_ascii=False,
    )
    return system_prompt, user_prompt


def generate_alignment(
    *,
    prompt: str,
    code: str,
    scene_name: str,
    video_duration: float | None,
    llm_call: Callable[[str, str], str] | None,
) -> dict[str, Any]:
    signals = extract_alignment_signals(
        code=code,
        scene_name=scene_name,
        video_duration=video_duration,
    )
    timing_is_estimated = bool(signals.get("warnings")) or video_duration is None
    if llm_call is None:
        return build_fallback_alignment(
            prompt=prompt,
            scene_name=scene_name,
            signals=signals,
            extra_warning="No alignment model call was configured.",
        )

    system_prompt, user_prompt = _build_alignment_prompts(
        prompt=prompt,
        code=code,
        scene_name=scene_name,
        signals=signals,
    )
    try:
        raw_text = llm_call(system_prompt, user_prompt)
        parsed = parse_alignment_json(raw_text)
        return validate_alignment(
            parsed,
            video_duration=signals.get("duration"),
            timing_is_estimated=timing_is_estimated,
        )
    except Exception as exc:
        return build_fallback_alignment(
            prompt=prompt,
            scene_name=scene_name,
            signals=signals,
            extra_warning=f"Alignment model failed: {exc}",
        )

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def iter_json_object_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    start: int | None = None
    depth = 0
    in_string = False
    escape = False
    for index, char in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            if depth == 0:
                start = index
            depth += 1
            continue
        if char != "}" or depth == 0:
            continue
        depth -= 1
        if depth == 0 and start is not None:
            candidates.append(text[start : index + 1])
            start = None
    return candidates


def extract_json(text: str) -> dict[str, object] | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    for candidate in reversed(iter_json_object_candidates(stripped)):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def build_prompt(image_path: Path, prompt_path: Path) -> str:
    prompt = prompt_path.read_text(encoding="utf-8")
    image_token = os.getenv("KIMI_VISION_IMAGE_TOKEN_TEMPLATE", "@{image_path}").format(
        image_path=str(image_path)
    )
    return (
        f"{prompt}\n\n"
        "请读取并分析下面这张图片，优先输出中文，并严格按上文要求返回 JSON。\n"
        f"图片：{image_token}\n"
    )


def build_command(binary: str, prompt: str, image_path: Path, prompt_path: Path) -> list[str]:
    args_json = os.getenv("KIMI_VISION_CLI_ARGS_JSON", "").strip()
    if not args_json:
        return [binary, "--quiet", "-p", prompt]
    try:
        raw_args = json.loads(args_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"KIMI_VISION_CLI_ARGS_JSON is not valid JSON: {exc}") from exc
    if not isinstance(raw_args, list) or not all(isinstance(item, str) for item in raw_args):
        raise ValueError("KIMI_VISION_CLI_ARGS_JSON must be a JSON string array")
    values = {
        "prompt": prompt,
        "image_path": str(image_path),
        "prompt_path": str(prompt_path),
    }
    return [binary, *(item.format(**values) for item in raw_args)]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bridge Aegis image-analysis requests to a logged-in terminal AI CLI."
    )
    parser.add_argument("image_path", type=Path)
    parser.add_argument("prompt_path", type=Path)
    args = parser.parse_args()

    if not args.image_path.is_file():
        print(json.dumps({"ok": False, "error": f"image not found: {args.image_path}"}))
        return 2
    if not args.prompt_path.is_file():
        print(json.dumps({"ok": False, "error": f"prompt not found: {args.prompt_path}"}))
        return 2

    binary = os.getenv("KIMI_VISION_CLI_BINARY", "kimi")
    timeout = int(os.getenv("KIMI_VISION_CLI_TIMEOUT_SECONDS", "180"))
    prompt = build_prompt(args.image_path, args.prompt_path)
    try:
        command = build_command(binary, prompt, args.image_path, args.prompt_path)
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    proc = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    output = proc.stdout.strip()
    if proc.returncode != 0:
        error_text = proc.stderr.strip() or output or f"{binary} exited with {proc.returncode}"
        print(json.dumps({"ok": False, "error": error_text}, ensure_ascii=False))
        return proc.returncode

    parsed = extract_json(output)
    if parsed is not None:
        print(json.dumps(parsed, ensure_ascii=False))
        return 0

    print(
        json.dumps(
            {
                "image_type": "图片题目",
                "recognized_content": output,
                "key_elements": [],
                "uncertainties": ["Kimi CLI 未返回结构化 JSON，已保留原始文本。"],
                "visualization_plan": output,
                "recommended_prompt": output,
                "auditable_analysis": "kimi_vision_cli_bridge returned raw text.",
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

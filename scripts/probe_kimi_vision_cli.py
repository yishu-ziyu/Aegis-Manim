#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BRIDGE_SCRIPT = PROJECT_ROOT / "scripts" / "kimi_vision_cli_bridge.py"

CHINESE_MARKERS = (
    "供给",
    "需求",
    "均衡",
    "价格",
    "数量",
    "税",
    "福利",
    "曲线",
    "消费者",
    "生产者",
    "垄断",
    "外部性",
    "成本",
    "收益",
)
FAILURE_MARKERS = (
    "无法读取",
    "不能读取",
    "看不到图片",
    "无法访问图片",
    "not found",
    "no such file",
    "permission denied",
    "unsupported",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify that the real server Kimi/Codex/Claude CLI can read an uploaded economics image."
    )
    parser.add_argument(
        "--image",
        type=Path,
        required=True,
        help="Path to a real Chinese economics question image on the server.",
    )
    parser.add_argument(
        "--binary",
        default=os.getenv("KIMI_VISION_CLI_BINARY", "kimi"),
        help="CLI binary to call through scripts/kimi_vision_cli_bridge.py.",
    )
    parser.add_argument(
        "--token-template",
        default=os.getenv("KIMI_VISION_IMAGE_TOKEN_TEMPLATE", "@{image_path}"),
        help="How the CLI prompt should reference the image path.",
    )
    parser.add_argument(
        "--args-json",
        default=os.getenv("KIMI_VISION_CLI_ARGS_JSON", ""),
        help='Optional JSON string array for CLI args, for example \'["--quiet","-p","{prompt}"]\'.',
    )
    parser.add_argument("--timeout", type=int, default=int(os.getenv("KIMI_VISION_CLI_TIMEOUT_SECONDS", "180")))
    parser.add_argument("--report", type=Path, help="Optional path to write the parsed JSON report.")
    return parser.parse_args()


def write_probe_prompt(prompt_path: Path) -> None:
    prompt_path.write_text(
        """
你正在验证 Aegis-Manim 的图片理解能力。请读取这张中文经济学考研题或经济学图表图片，只输出中文 JSON，不要输出 Markdown。

JSON 字段必须包括：
{
  "image_type": "题目截图/经济学图表/手写草图/其他",
  "recognized_content": "尽量完整复述图片中的题干、图形、坐标轴、曲线、公式或关键文字",
  "key_elements": ["图片中可用于 Manim 可视化的经济学元素"],
  "uncertainties": ["无法确认或可能误读的内容"],
  "visualization_plan": "用中文说明应该怎样转成 Manim 动画",
  "recommended_prompt": "可直接交给 Aegis-Manim 生成动画的中文提示词",
  "auditable_analysis": "说明你依据图片中的哪些可见信息做出判断"
}

硬性要求：
- 如果你看不到图片，必须在 uncertainties 中明确写出“看不到图片”，不要猜。
- 如果图片是经济学题，请优先识别考研经济学术语，并把 recommended_prompt 写成中文。
""".strip(),
        encoding="utf-8",
    )


def resolve_binary(binary: str) -> str | None:
    if "/" in binary:
        return binary if Path(binary).exists() else None
    return shutil.which(binary)


def extract_text(payload: dict[str, object]) -> str:
    chunks: list[str] = []
    for key in ("recognized_content", "visualization_plan", "recommended_prompt", "auditable_analysis"):
        value = payload.get(key)
        if isinstance(value, str):
            chunks.append(value)
    for key in ("key_elements", "uncertainties"):
        value = payload.get(key)
        if isinstance(value, list):
            chunks.extend(str(item) for item in value)
    return "\n".join(chunks)


def looks_like_pass(payload: dict[str, object]) -> tuple[bool, list[str]]:
    text = extract_text(payload)
    reasons: list[str] = []
    if not any("\u4e00" <= char <= "\u9fff" for char in text):
        reasons.append("response has no Chinese text")
    if any(marker in text.lower() for marker in FAILURE_MARKERS):
        reasons.append("response says the image was not readable")
    recommended = str(payload.get("recommended_prompt") or "")
    if not recommended.strip():
        reasons.append("recommended_prompt is empty")
    if not any(marker in text for marker in CHINESE_MARKERS):
        reasons.append("response does not contain recognizable economics terms")
    return not reasons, reasons


def main() -> int:
    args = parse_args()
    image_path = args.image.expanduser().resolve()
    if not image_path.is_file():
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"image not found: {image_path}",
                    "next": "Copy a real Chinese economics screenshot to the server, for example /opt/aegis/vision-test.png.",
                },
                ensure_ascii=False,
            )
        )
        return 2
    if not BRIDGE_SCRIPT.is_file():
        print(json.dumps({"ok": False, "error": f"bridge script not found: {BRIDGE_SCRIPT}"}, ensure_ascii=False))
        return 2
    if not resolve_binary(args.binary):
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"CLI binary not found: {args.binary}",
                    "next": "Install and login the real CLI first, then rerun this probe.",
                },
                ensure_ascii=False,
            )
        )
        return 2

    env = {
        **os.environ,
        "KIMI_VISION_CLI_BINARY": args.binary,
        "KIMI_VISION_IMAGE_TOKEN_TEMPLATE": args.token_template,
        "KIMI_VISION_CLI_TIMEOUT_SECONDS": str(args.timeout),
    }
    if args.args_json:
        env["KIMI_VISION_CLI_ARGS_JSON"] = args.args_json
    with tempfile.TemporaryDirectory(prefix="aegis-kimi-vision-probe-") as temp_dir:
        prompt_path = Path(temp_dir) / "vision_probe_prompt.txt"
        write_probe_prompt(prompt_path)
        proc = subprocess.run(
            [sys.executable, str(BRIDGE_SCRIPT), str(image_path), str(prompt_path)],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=args.timeout + 10,
            env=env,
        )

    if proc.returncode != 0:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "CLI bridge failed",
                    "returncode": proc.returncode,
                    "stdout": proc.stdout.strip(),
                    "stderr": proc.stderr.strip(),
                },
                ensure_ascii=False,
            )
        )
        return 1

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(
            json.dumps(
                {"ok": False, "error": "CLI bridge returned non-JSON output", "stdout": proc.stdout.strip()},
                ensure_ascii=False,
            )
        )
        return 1

    ok, reasons = looks_like_pass(payload)
    report = {
        "ok": ok,
        "binary": args.binary,
        "image": str(image_path),
        "tokenTemplate": args.token_template,
        "argsJson": args.args_json,
        "payload": payload,
        "failureReasons": reasons,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if ok:
        exports = [
            f"export KIMI_VISION_CLI_COMMAND='python3 {BRIDGE_SCRIPT} {{image_path}} {{prompt_path}}'",
            f"export KIMI_VISION_CLI_BINARY='{args.binary}'",
            f"export KIMI_VISION_IMAGE_TOKEN_TEMPLATE='{args.token_template}'",
        ]
        if args.args_json:
            exports.append(f"export KIMI_VISION_CLI_ARGS_JSON='{args.args_json}'")
        exports.append("export AEGIS_VISION_PUBLIC_ENABLED=1")
        print("\n生产环境通过该探针后再打开：\n" + "\n".join(exports) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

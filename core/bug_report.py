from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BUG_LOG_PATH = PROJECT_ROOT / "logs" / "bug_trace.jsonl"


def load_recent(limit: int, request_id: str | None = None) -> list[dict[str, Any]]:
    if limit <= 0 or not BUG_LOG_PATH.exists():
        return []

    lines = BUG_LOG_PATH.read_text(encoding="utf-8").splitlines()
    out: list[dict[str, Any]] = []
    for raw in reversed(lines):
        text = raw.strip()
        if not text:
            continue
        try:
            item = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            if request_id and item.get("requestId") != request_id:
                continue
            out.append(item)
        if len(out) >= limit:
            break
    return out


def print_human(entries: list[dict[str, Any]]) -> None:
    if not entries:
        print("No bug entries found.")
        return
    for idx, item in enumerate(entries, start=1):
        time = item.get("time", "-")
        request_id = item.get("requestId", "-")
        stage = item.get("stage", "-")
        severity = item.get("severity", "-")
        message = item.get("message", "")
        detail = item.get("detail", "")
        print(f"[{idx}] {time} | {severity.upper()} | {stage} | requestId={request_id}")
        print(f"    message: {message}")
        if detail:
            print(f"    detail: {detail}")
        context = item.get("context")
        if isinstance(context, dict) and context:
            model = context.get("model")
            endpoint = context.get("endpoint")
            prompt_len = context.get("promptLen")
            prompt_hash = context.get("promptHash")
            print(
                "    context: "
                f"model={model} endpoint={endpoint} promptLen={prompt_len} promptHash={prompt_hash}"
            )
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Read recent structured bug logs.")
    parser.add_argument("--limit", type=int, default=20, help="Number of latest records to show.")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print as JSON array for machine consumption.",
    )
    parser.add_argument(
        "--request-id",
        default="",
        help="Only show entries matching the given requestId.",
    )
    args = parser.parse_args()

    entries = load_recent(
        max(1, min(200, args.limit)),
        request_id=args.request_id.strip() or None,
    )
    if args.json:
        print(json.dumps(entries, ensure_ascii=False, indent=2))
        return 0

    print_human(entries)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

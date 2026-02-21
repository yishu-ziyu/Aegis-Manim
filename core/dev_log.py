from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = PROJECT_ROOT / "PRODUCT_DEV_LOG.md"


def append_entry(
    *,
    step: str,
    problem: str,
    solution: str,
    rationale: str,
    prevention: str,
    result: str,
) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    block = (
        f"\n## {ts} | {step}\n"
        f"- 问题现象: {problem}\n"
        f"- 解决方案: {solution}\n"
        f"- 方案原因: {rationale}\n"
        f"- 下次识别与避免: {prevention}\n"
        f"- 结果与经验: {result}\n"
    )
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(block)


def main() -> int:
    parser = argparse.ArgumentParser(description="Append a structured product dev log entry.")
    parser.add_argument("--step", required=True, help="Current step title")
    parser.add_argument("--problem", required=True, help="Problem observed in this step")
    parser.add_argument("--solution", required=True, help="What was changed to solve it")
    parser.add_argument("--rationale", required=True, help="Why this solution was chosen")
    parser.add_argument("--prevention", required=True, help="How to detect/avoid this issue next time")
    parser.add_argument("--result", required=True, help="Outcome and learnings")
    args = parser.parse_args()

    append_entry(
        step=args.step,
        problem=args.problem,
        solution=args.solution,
        rationale=args.rationale,
        prevention=args.prevention,
        result=args.result,
    )
    print(f"Appended log entry to {LOG_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from urllib import error, request


DEFAULT_URL = "https://manim.yishuziyu.cn/api/generate"
DEFAULT_PROVIDERS = ("trial-minimax-direct", "trial-kimi-priority", "trial-mimo-direct")
DEFAULT_PROMPTS = (
    "用三步解释消费者剩余。",
    "可视化帕累托最优过程。",
    "解释线性增长为什么会累积差距。",
)


@dataclass(frozen=True)
class Sample:
    provider: str
    run: int
    ok: bool
    http: int | None
    request_id: str | None
    model: str | None
    endpoint: str | None
    scene_name: str | None
    fallback: bool
    latency_ms: int
    code_chars: int
    play_count: int
    wait_count: int
    lagged_start_count: int
    warnings_count: int
    error_type: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "run": self.run,
            "ok": self.ok,
            "http": self.http,
            "requestId": self.request_id,
            "model": self.model,
            "endpoint": self.endpoint,
            "sceneName": self.scene_name,
            "fallback": self.fallback,
            "latencyMs": self.latency_ms,
            "codeChars": self.code_chars,
            "playCount": self.play_count,
            "waitCount": self.wait_count,
            "laggedStartCount": self.lagged_start_count,
            "warningsCount": self.warnings_count,
            "errorType": self.error_type,
        }


def percentile(values: list[int], pct: float) -> int | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    index = round((len(ordered) - 1) * pct)
    return ordered[index]


def build_payload(prompt: str, provider: str) -> bytes:
    payload = {
        "prompt": prompt,
        "provider": provider,
        "sceneName": "GeneratedScene",
        "temperature": 0.2,
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def measure_once(url: str, provider: str, prompt: str, run: int, timeout: int) -> Sample:
    started = time.perf_counter()
    req = request.Request(
        url,
        data=build_payload(prompt, provider),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            latency_ms = round((time.perf_counter() - started) * 1000)
            code = str(body.get("code") or "")
            endpoint = str(body.get("endpoint") or "")
            model = str(body.get("model") or "")
            return Sample(
                provider=provider,
                run=run,
                ok=bool(body.get("ok")),
                http=int(resp.status),
                request_id=str(body.get("requestId") or ""),
                model=model,
                endpoint=endpoint,
                scene_name=str(body.get("sceneName") or ""),
                fallback=endpoint == "server-managed-fallback" or model == "stable-template-fallback",
                latency_ms=latency_ms,
                code_chars=len(code),
                play_count=code.count("self.play("),
                wait_count=code.count("self.wait("),
                lagged_start_count=code.count("LaggedStart("),
                warnings_count=len(body.get("warnings") or []),
            )
    except error.HTTPError as exc:
        latency_ms = round((time.perf_counter() - started) * 1000)
        return Sample(
            provider=provider,
            run=run,
            ok=False,
            http=exc.code,
            request_id=None,
            model=None,
            endpoint=None,
            scene_name=None,
            fallback=False,
            latency_ms=latency_ms,
            code_chars=0,
            play_count=0,
            wait_count=0,
            lagged_start_count=0,
            warnings_count=0,
            error_type="HTTPError",
        )
    except Exception as exc:
        latency_ms = round((time.perf_counter() - started) * 1000)
        return Sample(
            provider=provider,
            run=run,
            ok=False,
            http=None,
            request_id=None,
            model=None,
            endpoint=None,
            scene_name=None,
            fallback=False,
            latency_ms=latency_ms,
            code_chars=0,
            play_count=0,
            wait_count=0,
            lagged_start_count=0,
            warnings_count=0,
            error_type=type(exc).__name__,
        )


def summarize(samples: list[Sample]) -> dict[str, object]:
    by_provider: dict[str, list[Sample]] = {}
    for sample in samples:
        by_provider.setdefault(sample.provider, []).append(sample)

    summary: dict[str, object] = {}
    for provider, provider_samples in by_provider.items():
        latencies = [sample.latency_ms for sample in provider_samples if sample.ok]
        successes = sum(1 for sample in provider_samples if sample.ok)
        trial_successes = sum(
            1 for sample in provider_samples if sample.ok and sample.endpoint == "server-managed-trial"
        )
        fallbacks = sum(1 for sample in provider_samples if sample.fallback)
        budget_violations = sum(
            1
            for sample in provider_samples
            if sample.play_count > 14 or sample.wait_count > 12 or sample.lagged_start_count > 2
        )
        count = len(provider_samples)
        summary[provider] = {
            "count": count,
            "successRate": round(successes / count, 3) if count else 0,
            "trialSuccessRate": round(trial_successes / count, 3) if count else 0,
            "fallbackRate": round(fallbacks / count, 3) if count else 0,
            "budgetViolationRate": round(budget_violations / count, 3) if count else 0,
            "latencyMsP50": round(statistics.median(latencies)) if latencies else None,
            "latencyMsP95": percentile(latencies, 0.95),
            "maxLatencyMs": max(latencies) if latencies else None,
        }
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure public Aegis trial provider stability without printing secrets or generated code."
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="Public /api/generate endpoint.")
    parser.add_argument(
        "--provider",
        action="append",
        choices=DEFAULT_PROVIDERS,
        help="Provider to measure. Repeat for multiple providers. Defaults to both trial providers.",
    )
    parser.add_argument("--runs", type=int, default=3, help="Number of prompt samples per provider.")
    parser.add_argument("--timeout", type=int, default=180, help="Per-request timeout in seconds.")
    parser.add_argument("--ci", action="store_true", help="CI mode: exit non-zero if any provider fails or fallback rate > 0.")
    parser.add_argument(
        "--jsonl",
        type=Path,
        help="Optional path to write per-run JSONL summaries. Generated code is never written.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    providers = tuple(args.provider or DEFAULT_PROVIDERS)
    samples: list[Sample] = []
    jsonl_file = args.jsonl.open("w", encoding="utf-8") if args.jsonl else None
    try:
        for provider in providers:
            for run in range(1, args.runs + 1):
                prompt = DEFAULT_PROMPTS[(run - 1) % len(DEFAULT_PROMPTS)]
                sample = measure_once(args.url, provider, prompt, run, args.timeout)
                samples.append(sample)
                line = json.dumps(sample.to_dict(), ensure_ascii=False)
                print(line)
                if jsonl_file:
                    jsonl_file.write(line + "\n")
                    jsonl_file.flush()
    finally:
        if jsonl_file:
            jsonl_file.close()

    summary = summarize(samples)
    print(json.dumps({"summary": summary}, ensure_ascii=False, indent=2))

    if args.ci:
        for provider, stats in summary.items():
            if stats["successRate"] < 1.0:
                print(f"[CI] FAIL: {provider} successRate={stats['successRate']}", file=sys.stderr)
                return 1
            if stats["fallbackRate"] > 0.0:
                print(f"[CI] FAIL: {provider} fallbackRate={stats['fallbackRate']}", file=sys.stderr)
                return 1
        print("[CI] PASS: all providers stable", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

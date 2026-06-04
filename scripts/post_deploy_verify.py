#!/usr/bin/env python3
"""Post-deployment smoke test for Aegis-Manim trial providers.

Usage:
    python3 scripts/post_deploy_verify.py
    python3 scripts/post_deploy_verify.py --endpoint https://manim.yishuziyu.cn
    python3 scripts/post_deploy_verify.py --ci

Exit codes:
    0 — all checks passed
    1 — one or more checks failed
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from urllib import error, request

DEFAULT_ENDPOINT = "https://manim.yishuziyu.cn"

# Providers that must return generated code (not fallback)
REQUIRED_TRIAL_PROVIDERS = (
    "trial-minimax-direct",
    "trial-mimo-direct",
)

# Providers that are expected to fail with a specific error
EXPECTED_FAILURES = {
    "trial-kimi-priority": "公开内测页只支持内置免费试用模型",
    "trial-deepseek-direct": "公开内测页只支持内置免费试用模型",
}

DEFAULT_PROMPT = "Draw a red circle and label it"
DEFAULT_SCENE = "GeneratedScene"


def build_payload(prompt: str, provider: str) -> bytes:
    return json.dumps(
        {
            "prompt": prompt,
            "provider": provider,
            "sceneName": DEFAULT_SCENE,
            "temperature": 0.2,
        },
        ensure_ascii=False,
    ).encode("utf-8")


def test_provider(endpoint: str, provider: str, timeout: int) -> dict[str, object]:
    url = f"{endpoint.rstrip('/')}/api/generate"
    started = time.perf_counter()
    req = request.Request(
        url,
        data=build_payload(DEFAULT_PROMPT, provider),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            latency_ms = round((time.perf_counter() - started) * 1000)
            code = str(body.get("code") or "")
            code_file = str(body.get("codeFile") or "")
            model = str(body.get("model") or "")
            warnings = body.get("warnings") or []
            return {
                "provider": provider,
                "ok": bool(body.get("ok")),
                "http": resp.status,
                "model": model,
                "codeFile": code_file,
                "codeLen": len(code),
                "isFallback": "fallback" in code_file or model == "stable-template-fallback",
                "latencyMs": latency_ms,
                "requestId": str(body.get("requestId") or ""),
                "error": str(body.get("error") or ""),
                "warnings": warnings,
                "passed": False,  # set later
            }
    except error.HTTPError as exc:
        latency_ms = round((time.perf_counter() - started) * 1000)
        body_raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(body_raw)
            error_msg = str(body.get("error") or "")
        except Exception:
            error_msg = body_raw[:200]
        return {
            "provider": provider,
            "ok": False,
            "http": exc.code,
            "model": None,
            "codeFile": None,
            "codeLen": 0,
            "isFallback": False,
            "latencyMs": latency_ms,
            "requestId": None,
            "error": error_msg,
            "warnings": [],
            "passed": False,
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - started) * 1000)
        return {
            "provider": provider,
            "ok": False,
            "http": None,
            "model": None,
            "codeFile": None,
            "codeLen": 0,
            "isFallback": False,
            "latencyMs": latency_ms,
            "requestId": None,
            "error": f"{type(exc).__name__}: {exc}",
            "warnings": [],
            "passed": False,
        }


def evaluate_required(result: dict[str, object]) -> bool:
    """A required provider passes if it returns ok=True, codeLen>1000, and not fallback."""
    if not result["ok"]:
        return False
    if result["codeLen"] <= 1000:
        return False
    if result["isFallback"]:
        return False
    return True


def evaluate_expected_failure(result: dict[str, object], expected_error: str) -> bool:
    """An expected-failure provider passes if it returns ok=False with the expected error."""
    if result["ok"]:
        return False
    if expected_error not in result.get("error", ""):
        return False
    return True


def run_checks(endpoint: str, timeout: int) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []

    for provider in REQUIRED_TRIAL_PROVIDERS:
        result = test_provider(endpoint, provider, timeout)
        result["passed"] = evaluate_required(result)
        result["checkType"] = "required"
        results.append(result)

    for provider, expected_error in EXPECTED_FAILURES.items():
        result = test_provider(endpoint, provider, timeout)
        result["passed"] = evaluate_expected_failure(result, expected_error)
        result["checkType"] = "expected_failure"
        results.append(result)

    return results


def print_results(results: list[dict[str, object]], ci: bool) -> None:
    if ci:
        # CI mode: compact JSON output only
        print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
        return

    # Human-friendly output
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    print(f"\n{'=' * 60}")
    print(f"Aegis-Manim Post-Deploy Verification")
    print(f"{'=' * 60}")
    for r in results:
        status = "✅ PASS" if r["passed"] else "❌ FAIL"
        provider = r["provider"]
        latency = r["latencyMs"]
        code_len = r["codeLen"]
        is_fb = r["isFallback"]
        error = r.get("error", "")
        if r["checkType"] == "required":
            print(f"{status} | {provider:25s} | {latency:5d}ms | code={code_len:5d} | fallback={is_fb}")
        else:
            print(f"{status} | {provider:25s} | {latency:5d}ms | error={error[:60]}")
    print(f"{'=' * 60}")
    print(f"Total: {passed}/{total} passed")
    print(f"{'=' * 60}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Post-deployment smoke test for Aegis-Manim")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="Base URL of the deployment")
    parser.add_argument("--timeout", type=int, default=180, help="Per-request timeout in seconds")
    parser.add_argument("--ci", action="store_true", help="CI mode: JSON output only")
    args = parser.parse_args()

    results = run_checks(args.endpoint, args.timeout)
    print_results(results, args.ci)

    all_passed = all(r["passed"] for r in results)
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

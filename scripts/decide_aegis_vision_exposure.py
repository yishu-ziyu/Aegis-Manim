from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path
from urllib import error


MIN_ACCEPTANCE_CASES = 3
MAX_ACCEPTANCE_CASES = 5


def load_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"ok": False, "missing": str(path)}
    except json.JSONDecodeError as exc:
        return {"ok": False, "invalid": str(path), "error": str(exc)}
    if not isinstance(payload, dict):
        return {"ok": False, "invalid": str(path), "error": "expected JSON object"}
    return payload


def load_jsonl(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            records.append({"ok": False, "status": "invalid-jsonl-line", "errorMessage": line[:200]})
            continue
        if isinstance(payload, dict) and "summary" not in payload:
            records.append(payload)
    return records


def fetch_health(url: str, timeout: int) -> dict[str, object]:
    if not url:
        return {"ok": False, "missing": "health-url"}
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (OSError, error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": type(exc).__name__, "detail": str(exc)}
    if not isinstance(payload, dict):
        return {"ok": False, "error": "invalid-health-payload"}
    return payload


def fetch_public_vision_route(url: str, timeout: int) -> dict[str, object]:
    if not url:
        return {"checked": False, "routeDeployed": None}

    payload = json.dumps({}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            parsed = json.loads(body) if body else {}
            if not isinstance(parsed, dict):
                parsed = {"raw": body[:200]}
            return {"checked": True, "routeDeployed": True, "status": resp.status, "payload": parsed}
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {"raw": body[:200]}
        if not isinstance(parsed, dict):
            parsed = {"raw": body[:200]}
        return {
            "checked": True,
            "routeDeployed": exc.code != 404,
            "status": exc.code,
            "payload": parsed,
        }
    except (OSError, error.URLError, TimeoutError) as exc:
        return {
            "checked": True,
            "routeDeployed": False,
            "error": type(exc).__name__,
            "detail": str(exc),
        }


def _payload_ok(payload: dict[str, object]) -> bool:
    return payload.get("ok") is True or payload.get("status") == "ok"


def decide(
    *,
    probe_report: dict[str, object],
    acceptance_records: list[dict[str, object]],
    health: dict[str, object],
    public_route: dict[str, object] | None = None,
) -> dict[str, object]:
    reasons: list[str] = []
    public_route = public_route or {"checked": False, "routeDeployed": None}

    probe_ok = probe_report.get("ok") is True
    if not probe_ok:
        reasons.append("probe did not pass")

    total = len(acceptance_records)
    case_count_ok = MIN_ACCEPTANCE_CASES <= total <= MAX_ACCEPTANCE_CASES
    if not case_count_ok:
        reasons.append(f"acceptance case count must be {MIN_ACCEPTANCE_CASES}-{MAX_ACCEPTANCE_CASES}, got {total}")

    failed_cases = [
        record
        for record in acceptance_records
        if record.get("ok") is not True
    ]
    if failed_cases:
        reasons.append(f"{len(failed_cases)} acceptance case(s) failed")

    health_ok = _payload_ok(health)
    if not health_ok:
        reasons.append("vision server health is not ok")

    route_checked = public_route.get("checked") is True
    route_deployed = public_route.get("routeDeployed")
    if route_checked and route_deployed is False:
        reasons.append("public /api/vision/analyze route is not deployed")

    all_records_ok = case_count_ok and not failed_cases
    vision_only_passed = all_records_ok and all(record.get("status") == "vision-done" for record in acceptance_records)
    full_render_passed = all_records_ok and all(
        record.get("status") == "done" and bool(record.get("videoUrl")) and int(record.get("videoBytes") or 0) > 0
        for record in acceptance_records
    )

    public_route_allows_exposure = (not route_checked) or route_deployed is not False

    if probe_ok and health_ok and public_route_allows_exposure and full_render_passed:
        exposure = "public"
        reason = "probe, health, and full image-to-render acceptance passed"
    elif probe_ok and health_ok and public_route_allows_exposure and vision_only_passed:
        exposure = "beta"
        reason = "vision-only acceptance passed; full public render acceptance is still required"
    else:
        exposure = "hidden"
        reason = "; ".join(reasons) or "required evidence is incomplete"

    return {
        "ok": exposure != "hidden",
        "exposure": exposure,
        "reason": reason,
        "evidence": {
            "probeOk": probe_ok,
            "healthOk": health_ok,
            "acceptanceTotal": total,
            "acceptancePassed": total - len(failed_cases),
            "visionOnlyPassed": vision_only_passed,
            "fullRenderPassed": full_render_passed,
            "publicRouteChecked": route_checked,
            "publicRouteDeployed": route_deployed,
        },
        "next": next_steps(exposure),
    }


def next_steps(exposure: str) -> list[str]:
    if exposure == "public":
        return [
            "Set AEGIS_VISION_PUBLIC_ENABLED=1.",
            "Set VISION_BACKEND_URL to the HTTPS vision backend.",
            "Run 3-5 public browser image-to-video acceptance cases.",
        ]
    if exposure == "beta":
        return [
            "Keep the image entry behind beta/whitelist access.",
            "Run full generate/render/video acceptance without --skip-render before public exposure.",
            "Do not enable a broad public entry yet.",
        ]
    return [
        "Keep AEGIS_VISION_PUBLIC_ENABLED unset or 0.",
        "Fix the failing probe, health check, or acceptance records.",
        "Deploy the public /api/vision/analyze route if the route check returned 404.",
        "Rerun the server doctor before exposing the feature.",
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Decide Aegis Vision production exposure from verified evidence.")
    parser.add_argument("--probe-report", type=Path, default=Path("/opt/aegis/vision-probe-report.json"))
    parser.add_argument("--acceptance-jsonl", type=Path, default=Path("/opt/aegis/vision-economics-acceptance.jsonl"))
    parser.add_argument("--health-url", default="http://127.0.0.1:5050/health")
    parser.add_argument("--health-timeout", type=int, default=8)
    parser.add_argument("--public-vision-url", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    decision = decide(
        probe_report=load_json(args.probe_report),
        acceptance_records=load_jsonl(args.acceptance_jsonl),
        health=fetch_health(args.health_url, args.health_timeout),
        public_route=fetch_public_vision_route(args.public_vision_url, args.health_timeout),
    )
    print(json.dumps(decision, ensure_ascii=False, indent=2))
    return 0 if decision["exposure"] in {"beta", "public"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from scripts import decide_aegis_vision_exposure as decision


def _records(status: str, count: int = 5) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for index in range(1, count + 1):
        record: dict[str, object] = {
            "index": index,
            "ok": True,
            "status": status,
            "suggestedPromptChars": 420,
        }
        if status == "done":
            record.update({"videoUrl": f"https://example.test/{index}.mp4", "videoBytes": 100000})
        records.append(record)
    return records


def test_decides_beta_after_probe_health_and_vision_only_acceptance() -> None:
    result = decision.decide(
        probe_report={"ok": True},
        acceptance_records=_records("vision-done"),
        health={"status": "ok"},
    )

    assert result["exposure"] == "beta"
    assert result["ok"] is True
    assert result["evidence"]["visionOnlyPassed"] is True
    assert result["evidence"]["fullRenderPassed"] is False


def test_decides_public_only_after_full_render_acceptance() -> None:
    result = decision.decide(
        probe_report={"ok": True},
        acceptance_records=_records("done"),
        health={"ok": True},
    )

    assert result["exposure"] == "public"
    assert result["evidence"]["fullRenderPassed"] is True


def test_decides_hidden_when_probe_or_acceptance_is_missing() -> None:
    result = decision.decide(
        probe_report={"ok": False},
        acceptance_records=_records("vision-done", count=2),
        health={"status": "ok"},
    )

    assert result["exposure"] == "hidden"
    assert result["ok"] is False
    assert "probe did not pass" in result["reason"]


def test_public_route_404_forces_hidden_even_with_server_evidence() -> None:
    result = decision.decide(
        probe_report={"ok": True},
        acceptance_records=_records("vision-done"),
        health={"status": "ok"},
        public_route={"checked": True, "routeDeployed": False, "status": 404},
    )

    assert result["exposure"] == "hidden"
    assert result["evidence"]["publicRouteChecked"] is True
    assert result["evidence"]["publicRouteDeployed"] is False
    assert "public /api/vision/analyze route is not deployed" in result["reason"]


def test_deployed_but_disabled_public_route_does_not_block_beta() -> None:
    result = decision.decide(
        probe_report={"ok": True},
        acceptance_records=_records("vision-done"),
        health={"status": "ok"},
        public_route={
            "checked": True,
            "routeDeployed": True,
            "status": 503,
            "payload": {"code": "vision_feature_disabled"},
        },
    )

    assert result["exposure"] == "beta"
    assert result["evidence"]["publicRouteDeployed"] is True

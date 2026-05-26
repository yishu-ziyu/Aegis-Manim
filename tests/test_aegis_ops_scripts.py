from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_script_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_production_economics_acceptance_uses_chinese_exam_prompts_and_hides_code() -> None:
    script = load_script_module(
        "production_economics_acceptance",
        PROJECT_ROOT / "scripts" / "production_economics_acceptance.py",
    )

    assert len(script.DEFAULT_PROMPTS) >= 5
    assert all("考研经济学题" in prompt for prompt in script.DEFAULT_PROMPTS)
    assert any("二部定价" in prompt for prompt in script.DEFAULT_PROMPTS)
    assert any("税收楔子" in prompt for prompt in script.DEFAULT_PROMPTS)

    sample = script.AcceptanceResult(
        index=1,
        prompt_title="消费者剩余",
        ok=True,
        generate_http=200,
        render_http=202,
        status="done",
        model="stable-template-fallback",
        endpoint="server-managed-fallback",
        job_id="job-123",
        video_url="https://example.test/video.mp4",
        code_chars=2100,
        play_count=4,
        duration_seconds=4.4,
        video_bytes=100000,
        frame_path="/tmp/frame.png",
        latency_ms=900,
    )
    serialized = sample.to_dict()

    assert "code" not in serialized
    assert "from manim" not in str(serialized)
    assert serialized["promptTitle"] == "消费者剩余"
    assert serialized["videoBytes"] == 100000


def test_render_watchdog_is_restart_capable_and_secret_safe() -> None:
    script_path = PROJECT_ROOT / "scripts" / "aegis_render_watchdog.sh"
    script = script_path.read_text(encoding="utf-8")

    assert "curl" in script
    assert "docker restart" in script
    assert "flock" in script
    assert "COOLDOWN_SECONDS" in script
    assert "MANIM_API_KEY" not in script
    assert "X-API-Key" not in script
    assert "aegis-manim-render" in script

    subprocess.run(["bash", "-n", str(script_path)], check=True)


def test_watchdog_installer_uses_systemd_timer_without_secrets() -> None:
    script_path = PROJECT_ROOT / "scripts" / "install_aegis_render_watchdog.sh"
    script = script_path.read_text(encoding="utf-8")

    assert "aegis-render-watchdog.service" in script
    assert "aegis-render-watchdog.timer" in script
    assert "OnUnitActiveSec=60s" in script
    assert "systemctl enable --now aegis-render-watchdog.timer" in script
    assert "MANIM_API_KEY" not in script
    assert "X-API-Key" not in script

    subprocess.run(["bash", "-n", str(script_path)], check=True)


def test_vision_server_and_installer_define_host_cli_bridge() -> None:
    server_path = PROJECT_ROOT / "scripts" / "aegis_vision_server.py"
    installer_path = PROJECT_ROOT / "scripts" / "install_aegis_vision_server.sh"
    server = server_path.read_text(encoding="utf-8")
    installer = installer_path.read_text(encoding="utf-8")

    assert "/api/vision/analyze" in server
    assert "AEGIS_VISION_BACKEND_API_KEY" in server
    assert "vision_analysis.analyze_image_payload" in server
    assert "VISION_BACKEND_URL" in server
    assert "aegis-vision.service" in installer
    assert "kimi_vision_cli_bridge.py {image_path} {prompt_path}" in installer
    assert "KIMI_VISION_CLI_ARGS_JSON" in installer
    assert "systemctl enable --now aegis-vision.service" in installer
    assert "VISION_BACKEND_URL=http://<server-ip>:${PORT}" in installer

    subprocess.run(["python3", "-m", "py_compile", str(server_path)], check=True)
    subprocess.run(["bash", "-n", str(installer_path)], check=True)


def test_vision_server_doctor_runs_probe_then_installer() -> None:
    script_path = PROJECT_ROOT / "scripts" / "aegis_vision_server_doctor.sh"
    script = script_path.read_text(encoding="utf-8")

    assert "scripts/probe_kimi_vision_cli.py" in script
    assert "INSTALL_ON_PASS" in script
    assert "RUN_BATCH_ACCEPTANCE" in script
    assert "IMAGE_PATH" in script
    assert "fixtures/vision-test.png" in script
    assert "scripts/production_vision_economics_acceptance.py" in script
    assert "--skip-render" in script
    assert "--api-key" in script
    assert "format_env_value" in script
    assert "persist_tested_cli_env" in script
    assert "upsert_env_line \"KIMI_VISION_CLI_BINARY\"" in script
    assert "upsert_env_line \"KIMI_VISION_CLI_ARGS_JSON\"" in script
    assert "Persisting tested CLI settings" in script
    assert "vision-economics-acceptance.jsonl" in script
    assert "scripts/install_aegis_vision_server.sh" in script
    assert "VISION_BACKEND_URL=http://121.89.90.68:5050" in script
    assert "VISION_BACKEND_API_KEY" in script
    assert "do not paste it into chat" in script

    subprocess.run(["bash", "-n", str(script_path)], check=True)


def test_vision_server_package_script_includes_server_files() -> None:
    script_path = PROJECT_ROOT / "scripts" / "package_aegis_vision_server_update.sh"
    script = script_path.read_text(encoding="utf-8")

    assert "core/vision_analysis.py" in script
    assert "scripts/aegis_vision_server.py" in script
    assert "scripts/install_aegis_vision_server.sh" in script
    assert "scripts/aegis_vision_server_doctor.sh" in script
    assert "scripts/kimi_vision_cli_bridge.py" in script
    assert "scripts/probe_kimi_vision_cli.py" in script
    assert "scripts/decide_aegis_vision_exposure.py" in script
    assert "scripts/generate_vision_economics_fixtures.py" in script
    assert "scripts/production_vision_economics_acceptance.py" in script
    assert "fixtures/vision-test.png" in script
    assert "tar -C" in script
    assert "scp $OUTPUT root@121.89.90.68" in script

    subprocess.run(["bash", "-n", str(script_path)], check=True)


def test_vision_server_push_script_packages_uploads_and_runs_doctor() -> None:
    script_path = PROJECT_ROOT / "scripts" / "push_aegis_vision_server_update.sh"
    script = script_path.read_text(encoding="utf-8")

    assert "OUTPUT=\"$OUTPUT\" scripts/package_aegis_vision_server_update.sh" in script
    assert "ssh \"$REMOTE_HOST\"" in script
    assert "< \"$OUTPUT\"" in script
    assert "cat > \\\"$REMOTE_ARCHIVE\\\"" in script
    assert "REMOTE_DOCTOR_LOG" in script
    assert "REMOTE_DOCTOR_PID" in script
    assert "nohup bash -lc" in script
    assert "tail -n 40" in script
    assert "REMOTE_PROJECT_DIR" in script
    assert "tar -xzf \\\"$REMOTE_ARCHIVE\\\"" in script
    assert "scripts/aegis_vision_server_doctor.sh" in script
    assert "VISION_BACKEND_API_KEY" not in script
    assert "AEGIS_VISION_BACKEND_API_KEY" not in script

    subprocess.run(["bash", "-n", str(script_path)], check=True)


def test_vision_server_check_script_collects_remote_evidence_without_secrets() -> None:
    script_path = PROJECT_ROOT / "scripts" / "check_aegis_vision_server_update.sh"
    script = script_path.read_text(encoding="utf-8")

    assert "REMOTE_DOCTOR_LOG" in script
    assert "REMOTE_DOCTOR_PID" in script
    assert "tail -n $TAIL_LINES" in script
    assert "Probe passed" in script
    assert "decide_aegis_vision_exposure.py" in script
    assert "systemctl status aegis-vision.service" in script
    assert "curl -fsS http://127.0.0.1:5050/health" in script
    assert "VISION_BACKEND_API_KEY" not in script
    assert "AEGIS_VISION_BACKEND_API_KEY" not in script

    subprocess.run(["bash", "-n", str(script_path)], check=True)


def test_public_vision_acceptance_wrapper_runs_full_render_path() -> None:
    script_path = PROJECT_ROOT / "scripts" / "run_aegis_public_vision_acceptance.sh"
    script = script_path.read_text(encoding="utf-8")

    assert "https://manim.yishuziyu.cn" in script
    assert "generate_vision_economics_fixtures.py" in script
    assert "production_vision_economics_acceptance.py" in script
    assert "--jsonl \"$JSONL\"" in script
    assert "--skip-render" not in script
    assert "01-tax-wedge.png" in script
    assert "05-is-lm.png" in script
    assert "VISION_BACKEND_API_KEY" not in script
    assert "AEGIS_VISION_BACKEND_API_KEY" not in script

    subprocess.run(["bash", "-n", str(script_path)], check=True)

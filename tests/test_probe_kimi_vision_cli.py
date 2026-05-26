from __future__ import annotations

import json
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROBE_SCRIPT = PROJECT_ROOT / "scripts" / "probe_kimi_vision_cli.py"


class ProbeKimiVisionCliTest(unittest.TestCase):
    def test_probe_accepts_real_cli_json_and_prints_production_exports(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fake_kimi = root / "fake_kimi.py"
            image_path = root / "econ-question.png"
            report_path = root / "report.json"
            image_path.write_bytes(b"fake-png")
            fake_kimi.write_text(
                textwrap.dedent(
                    """
                    #!/usr/bin/env python3
                    import json
                    import sys

                    prompt = sys.argv[sys.argv.index("-p") + 1]
                    assert "@/tmp" in prompt or "econ-question.png" in prompt
                    print(json.dumps({
                        "image_type": "经济学图表",
                        "recognized_content": "图片展示需求曲线和供给曲线，均衡价格与均衡数量。",
                        "key_elements": ["需求曲线", "供给曲线", "均衡价格"],
                        "uncertainties": [],
                        "visualization_plan": "先画供需曲线，再标出均衡点。",
                        "recommended_prompt": "请用中文动画解释供给需求均衡。",
                        "auditable_analysis": "依据图中的供给、需求和均衡标注。"
                    }, ensure_ascii=False))
                    """
                ).lstrip(),
                encoding="utf-8",
            )
            fake_kimi.chmod(fake_kimi.stat().st_mode | stat.S_IXUSR)

            result = subprocess.run(
                [
                    sys.executable,
                    str(PROBE_SCRIPT),
                    "--image",
                    str(image_path),
                    "--binary",
                    str(fake_kimi),
                    "--report",
                    str(report_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))

        assert result.returncode == 0, result.stderr + result.stdout
        assert "AEGIS_VISION_PUBLIC_ENABLED=1" in result.stdout
        assert report["ok"] is True
        assert report["payload"]["recommended_prompt"] == "请用中文动画解释供给需求均衡。"

    def test_probe_rejects_cli_output_that_does_not_prove_image_reading(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fake_kimi = root / "fake_kimi.py"
            image_path = root / "econ-question.png"
            image_path.write_bytes(b"fake-png")
            fake_kimi.write_text(
                "#!/usr/bin/env python3\n"
                "import json\n"
                "print(json.dumps({'recognized_content': '看不到图片', 'recommended_prompt': ''}, ensure_ascii=False))\n",
                encoding="utf-8",
            )
            fake_kimi.chmod(fake_kimi.stat().st_mode | stat.S_IXUSR)

            result = subprocess.run(
                [
                    sys.executable,
                    str(PROBE_SCRIPT),
                    "--image",
                    str(image_path),
                    "--binary",
                    str(fake_kimi),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        assert result.returncode == 1
        report = json.loads(result.stdout)
        assert report["ok"] is False
        assert "response says the image was not readable" in report["failureReasons"]

    def test_probe_forwards_custom_args_json_for_non_kimi_cli_shapes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fake_cli = root / "fake_cli.py"
            argv_log = root / "argv.json"
            image_path = root / "econ-question.png"
            image_path.write_bytes(b"fake-png")
            fake_cli.write_text(
                textwrap.dedent(
                    """
                    #!/usr/bin/env python3
                    import json
                    import os
                    import sys

                    open(os.environ["FAKE_CLI_ARGV_LOG"], "w", encoding="utf-8").write(
                        json.dumps(sys.argv[1:], ensure_ascii=False)
                    )
                    print(json.dumps({
                        "image_type": "经济学图表",
                        "recognized_content": "图中有供给曲线、需求曲线、均衡价格和均衡数量。",
                        "key_elements": ["供给曲线", "需求曲线", "均衡数量"],
                        "uncertainties": [],
                        "visualization_plan": "画出两条曲线并标出均衡。",
                        "recommended_prompt": "请用中文动画解释供需均衡。",
                        "auditable_analysis": "依据图片中的供给、需求、均衡标记。"
                    }, ensure_ascii=False))
                    """
                ).lstrip(),
                encoding="utf-8",
            )
            fake_cli.chmod(fake_cli.stat().st_mode | stat.S_IXUSR)

            result = subprocess.run(
                [
                    sys.executable,
                    str(PROBE_SCRIPT),
                    "--image",
                    str(image_path),
                    "--binary",
                    str(fake_cli),
                    "--args-json",
                    '["exec","--image","{image_path}","{prompt}"]',
                ],
                check=False,
                capture_output=True,
                text=True,
                env={"FAKE_CLI_ARGV_LOG": str(argv_log)},
            )
            logged_argv = json.loads(argv_log.read_text(encoding="utf-8"))

        assert result.returncode == 0, result.stderr + result.stdout
        assert logged_argv[:2] == ["exec", "--image"]
        assert Path(logged_argv[2]).resolve() == image_path.resolve()
        assert "KIMI_VISION_CLI_ARGS_JSON" in result.stdout


if __name__ == "__main__":
    unittest.main()

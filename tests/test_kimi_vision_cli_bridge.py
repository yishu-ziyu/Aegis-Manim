from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BRIDGE_SCRIPT = PROJECT_ROOT / "scripts" / "kimi_vision_cli_bridge.py"
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from kimi_vision_cli_bridge import extract_json  # noqa: E402


class KimiVisionCliBridgeTest(unittest.TestCase):
    def test_extract_json_handles_noisy_cli_with_duplicate_json(self) -> None:
        first_payload = json.dumps(
            {
                "recognized_content": "供给曲线和需求曲线。",
                "recommended_prompt": "请用中文解释均衡价格。",
            },
            ensure_ascii=False,
        )
        final_payload = json.dumps(
            {
                "recognized_content": "税收楔子、需求曲线、供给曲线。",
                "recommended_prompt": "请用中文动画解释税收楔子。",
            },
            ensure_ascii=False,
        )

        payload = extract_json(
            f"codex\nhook: start\n{first_payload}\nhook: done\n{final_payload}\ntokens used"
        )

        assert payload is not None
        assert payload["recommended_prompt"] == "请用中文动画解释税收楔子。"

    def test_wrapper_passes_image_reference_to_kimi_quiet_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fake_kimi = root / "fake_kimi.py"
            prompt_log = root / "prompt.log"
            image_path = root / "question.png"
            prompt_path = root / "prompt.txt"
            image_path.write_bytes(b"fake-png")
            prompt_path.write_text("请分析中文经济学题。", encoding="utf-8")
            fake_kimi.write_text(
                textwrap.dedent(
                    """
                    #!/usr/bin/env python3
                    import json
                    import os
                    import sys

                    assert "--quiet" in sys.argv
                    prompt = sys.argv[sys.argv.index("-p") + 1]
                    open(os.environ["FAKE_KIMI_PROMPT_LOG"], "w", encoding="utf-8").write(prompt)
                    print(json.dumps({
                        "recognized_content": "财政扩张使 IS 曲线右移。",
                        "key_elements": ["IS 曲线", "LM 曲线"],
                        "visualization_plan": "画出 IS 曲线右移。",
                        "recommended_prompt": "请用中文解释 IS-LM 财政扩张。"
                    }, ensure_ascii=False))
                    """
                ).lstrip(),
                encoding="utf-8",
            )
            fake_kimi.chmod(fake_kimi.stat().st_mode | stat.S_IXUSR)
            env = {
                **os.environ,
                "KIMI_VISION_CLI_BINARY": str(fake_kimi),
                "KIMI_VISION_IMAGE_TOKEN_TEMPLATE": "file://{image_path}",
                "FAKE_KIMI_PROMPT_LOG": str(prompt_log),
            }

            result = subprocess.run(
                [sys.executable, str(BRIDGE_SCRIPT), str(image_path), str(prompt_path)],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            logged_prompt = prompt_log.read_text(encoding="utf-8")

        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["recommended_prompt"] == "请用中文解释 IS-LM 财政扩张。"
        assert "请分析中文经济学题" in logged_prompt
        assert f"file://{image_path}" in logged_prompt

    def test_wrapper_converts_raw_text_to_structured_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fake_kimi = root / "fake_kimi.py"
            image_path = root / "question.png"
            prompt_path = root / "prompt.txt"
            image_path.write_bytes(b"fake-png")
            prompt_path.write_text("请分析中文经济学题。", encoding="utf-8")
            fake_kimi.write_text(
                "#!/usr/bin/env python3\nprint('这是一道关于供需均衡的题。')\n",
                encoding="utf-8",
            )
            fake_kimi.chmod(fake_kimi.stat().st_mode | stat.S_IXUSR)
            env = {**os.environ, "KIMI_VISION_CLI_BINARY": str(fake_kimi)}

            result = subprocess.run(
                [sys.executable, str(BRIDGE_SCRIPT), str(image_path), str(prompt_path)],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["recognized_content"] == "这是一道关于供需均衡的题。"
        assert payload["recommended_prompt"] == "这是一道关于供需均衡的题。"
        assert "未返回结构化 JSON" in payload["uncertainties"][0]

    def test_wrapper_allows_custom_cli_args_json_for_other_terminal_tools(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fake_cli = root / "fake_cli.py"
            argv_log = root / "argv.json"
            image_path = root / "question.png"
            prompt_path = root / "prompt.txt"
            image_path.write_bytes(b"fake-png")
            prompt_path.write_text("请分析中文经济学题。", encoding="utf-8")
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
                        "recognized_content": "需求曲线向右移动。",
                        "key_elements": ["需求曲线", "均衡价格"],
                        "visualization_plan": "展示均衡价格上升。",
                        "recommended_prompt": "请用中文动画解释需求增加。"
                    }, ensure_ascii=False))
                    """
                ).lstrip(),
                encoding="utf-8",
            )
            fake_cli.chmod(fake_cli.stat().st_mode | stat.S_IXUSR)
            env = {
                **os.environ,
                "KIMI_VISION_CLI_BINARY": str(fake_cli),
                "KIMI_VISION_CLI_ARGS_JSON": '["run","--image","{image_path}","--prompt","{prompt}"]',
                "FAKE_CLI_ARGV_LOG": str(argv_log),
            }

            result = subprocess.run(
                [sys.executable, str(BRIDGE_SCRIPT), str(image_path), str(prompt_path)],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            logged_argv = json.loads(argv_log.read_text(encoding="utf-8"))

        assert result.returncode == 0, result.stderr
        assert logged_argv[:3] == ["run", "--image", str(image_path)]
        assert "--prompt" in logged_argv
        assert "请分析中文经济学题" in logged_argv[-1]
        payload = json.loads(result.stdout)
        assert payload["recommended_prompt"] == "请用中文动画解释需求增加。"


if __name__ == "__main__":
    unittest.main()

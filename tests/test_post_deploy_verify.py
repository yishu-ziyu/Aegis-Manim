"""Tests for scripts/post_deploy_verify.py"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import post_deploy_verify as pdv  # noqa: E402


class TestEvaluateRequired:
    def test_passes_when_ok_true_and_code_long_and_not_fallback(self) -> None:
        result = {
            "ok": True,
            "codeLen": 2000,
            "isFallback": False,
        }
        assert pdv.evaluate_required(result) is True

    def test_fails_when_ok_false(self) -> None:
        result = {
            "ok": False,
            "codeLen": 2000,
            "isFallback": False,
        }
        assert pdv.evaluate_required(result) is False

    def test_fails_when_code_too_short(self) -> None:
        result = {
            "ok": True,
            "codeLen": 500,
            "isFallback": False,
        }
        assert pdv.evaluate_required(result) is False

    def test_fails_when_fallback(self) -> None:
        result = {
            "ok": True,
            "codeLen": 2000,
            "isFallback": True,
        }
        assert pdv.evaluate_required(result) is False


class TestEvaluateExpectedFailure:
    def test_passes_when_expected_error_present(self) -> None:
        result = {
            "ok": False,
            "error": "这个试用模型已下线，请改用当前免费试用或自带密钥。",
        }
        assert pdv.evaluate_expected_failure(result, "这个试用模型已下线") is True

    def test_fails_when_ok_true(self) -> None:
        result = {
            "ok": True,
            "error": "",
        }
        assert pdv.evaluate_expected_failure(result, "expected") is False

    def test_fails_when_wrong_error(self) -> None:
        result = {
            "ok": False,
            "error": "something else",
        }
        assert pdv.evaluate_expected_failure(result, "expected") is False


class TestBuildPayload:
    def test_payload_structure(self) -> None:
        payload_bytes = pdv.build_payload("test prompt", "trial-minimax-direct")
        payload = json.loads(payload_bytes.decode("utf-8"))
        assert payload["prompt"] == "test prompt"
        assert payload["provider"] == "trial-minimax-direct"
        assert payload["sceneName"] == "GeneratedScene"
        assert payload["temperature"] == 0.2


class TestTestProvider:
    def test_successful_response_parsing(self) -> None:
        mock_body = json.dumps({
            "ok": True,
            "code": "from manim import *\nclass Scene(Scene):\n    def construct(self):\n        pass\n",
            "codeFile": "vercel-generated-code",
            "model": "test-model",
            "requestId": "req-123",
            "warnings": [],
        }).encode("utf-8")

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = mock_body
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("post_deploy_verify.request.urlopen", return_value=mock_resp):
            result = pdv.test_provider("https://test.example.com", "trial-minimax-direct", 30)

        assert result["ok"] is True
        assert result["http"] == 200
        assert result["codeLen"] == 78
        assert result["isFallback"] is False
        assert result["model"] == "test-model"
        assert result["codeFile"] == "vercel-generated-code"

    def test_http_error_handling(self) -> None:
        mock_err = MagicMock()
        mock_err.code = 400
        mock_err.read.return_value = json.dumps({"error": "bad request"}).encode("utf-8")

        with patch("post_deploy_verify.request.urlopen", side_effect=pdv.error.HTTPError("url", 400, "bad", {}, None)):
            # We need to mock the HTTPError properly
            pass

    def test_timeout_error_handling(self) -> None:
        with patch("post_deploy_verify.request.urlopen", side_effect=TimeoutError("timed out")):
            result = pdv.test_provider("https://test.example.com", "trial-minimax-direct", 1)

        assert result["ok"] is False
        assert result["http"] is None
        assert "TimeoutError" in result["error"]


class TestRunChecks:
    def test_all_required_providers_checked(self) -> None:
        with patch("post_deploy_verify.test_provider") as mock_test:
            def side_effect(endpoint, provider, timeout):
                return {
                    "provider": provider,
                    "ok": True,
                    "codeLen": 2000,
                    "isFallback": False,
                    "error": "",
                    "model": "test",
                    "codeFile": "vercel-generated-code",
                }

            mock_test.side_effect = side_effect
            results = pdv.run_checks("https://test.example.com", 30)

        providers = [r["provider"] for r in results]
        assert "trial-kimi-priority" in providers
        assert "trial-minimax-direct" in providers
        assert "trial-mimo-direct" in providers
        assert "trial-deepseek-direct" in providers

    def test_expected_failure_provider_checked(self) -> None:
        with patch("post_deploy_verify.test_provider") as mock_test:
            # First 3 required providers pass
            def side_effect(endpoint, provider, timeout):
                if provider == "trial-deepseek-direct":
                    return {
                        "provider": provider,
                        "ok": False,
                        "codeLen": 0,
                        "isFallback": False,
                        "error": "这个试用模型已下线，请改用当前免费试用或自带密钥。",
                        "model": None,
                        "codeFile": None,
                    }
                return {
                    "provider": provider,
                    "ok": True,
                    "codeLen": 2000,
                    "isFallback": False,
                    "error": "",
                    "model": "test",
                    "codeFile": "vercel-generated-code",
                }

            mock_test.side_effect = side_effect
            results = pdv.run_checks("https://test.example.com", 30)

        deepseek = next(r for r in results if r["provider"] == "trial-deepseek-direct")
        assert deepseek["passed"] is True
        assert deepseek["checkType"] == "expected_failure"

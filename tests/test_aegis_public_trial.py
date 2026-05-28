from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path
from urllib.error import URLError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api import index as gateway  # noqa: E402

APP_SPEC = importlib.util.spec_from_file_location("aegis_vercel_asgi_app", PROJECT_ROOT / "app.py")
assert APP_SPEC and APP_SPEC.loader
vercel_asgi = importlib.util.module_from_spec(APP_SPEC)
APP_SPEC.loader.exec_module(vercel_asgi)


class FakeUrlopenResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body
        self.headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


async def call_asgi_app(
    method: str,
    path: str,
    *,
    body: bytes = b"",
    query_string: bytes = b"",
) -> tuple[int, dict[str, object]]:
    messages = [{"type": "http.request", "body": body, "more_body": False}]
    events: list[dict[str, object]] = []

    async def receive() -> dict[str, object]:
        if messages:
            return messages.pop(0)
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, object]) -> None:
        events.append(message)

    await vercel_asgi.app(
        {"type": "http", "method": method, "path": path, "query_string": query_string},
        receive,
        send,
    )

    status = next(event["status"] for event in events if event["type"] == "http.response.start")
    response_body = b"".join(
        event.get("body", b"") for event in events if event["type"] == "http.response.body"
    )
    return int(status), json.loads(response_body.decode("utf-8")) if response_body else {}


class AegisPublicTrialTest(unittest.TestCase):
    def setUp(self) -> None:
        self._old_kimi = os.environ.get("KIMI_CODE_API_KEY")
        self._old_deepseek = os.environ.get("DEEPSEEK_API_KEY")
        self._old_minimax = os.environ.get("MINIMAX_API_KEY")
        os.environ.pop("KIMI_CODE_API_KEY", None)
        os.environ.pop("DEEPSEEK_API_KEY", None)
        os.environ.pop("MINIMAX_API_KEY", None)

    def tearDown(self) -> None:
        if self._old_kimi is None:
            os.environ.pop("KIMI_CODE_API_KEY", None)
        else:
            os.environ["KIMI_CODE_API_KEY"] = self._old_kimi
        if self._old_deepseek is None:
            os.environ.pop("DEEPSEEK_API_KEY", None)
        else:
            os.environ["DEEPSEEK_API_KEY"] = self._old_deepseek
        if self._old_minimax is None:
            os.environ.pop("MINIMAX_API_KEY", None)
        else:
            os.environ["MINIMAX_API_KEY"] = self._old_minimax

    def test_public_config_exposes_only_safe_trial_choices(self) -> None:
        config = gateway.public_provider_config()
        providers = config["providers"]

        assert config["defaultProvider"] == "trial-kimi-priority"
        assert set(providers) == {"trial-kimi-priority", "trial-minimax-direct"}
        assert providers["trial-kimi-priority"]["serverManaged"] is True
        assert providers["trial-kimi-priority"]["requiresApiKey"] is False
        assert providers["trial-kimi-priority"]["hideApiKey"] is True
        assert "baseURL" not in providers["trial-kimi-priority"]
        assert "apiType" not in providers["trial-kimi-priority"]

    def test_health_exposes_safe_trial_provider_diagnostics(self) -> None:
        os.environ["KIMI_CODE_API_KEY"] = "server-kimi-key"
        os.environ["DEEPSEEK_API_KEY"] = "server-deepseek-key"
        os.environ["MINIMAX_API_KEY"] = "server-minimax-key"

        payload = gateway.build_health_payload()
        diagnostics = payload["trialProviders"]

        assert diagnostics["defaultProvider"] == "trial-kimi-priority"
        assert diagnostics["configured"] == {"kimiCode": True, "deepSeek": True, "miniMax": True}
        assert diagnostics["timeouts"]["kimi"] == gateway.PUBLIC_TRIAL_KIMI_TIMEOUT_SECONDS
        assert diagnostics["timeouts"]["deepSeek"] == gateway.PUBLIC_TRIAL_DEEPSEEK_TIMEOUT_SECONDS
        assert "server-kimi-key" not in json.dumps(payload)
        assert "server-deepseek-key" not in json.dumps(payload)
        assert "server-minimax-key" not in json.dumps(payload)

    def test_trial_uses_server_kimi_key_without_client_key(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_generate_code_with_llm(**kwargs: object) -> tuple[str, object, str]:
            calls.append(kwargs)
            provider = gateway.resolve_provider(str(kwargs["provider_id"]))
            return (
                "from manim import *\nclass GeneratedScene(Scene):\n"
                "    def construct(self):\n"
                "        self.play(Write(Text('消费者剩余', font_size=28)))\n",
                provider,
                "hidden",
            )

        original = gateway.generate_code_with_llm
        os.environ["KIMI_CODE_API_KEY"] = "server-kimi-key"
        os.environ["MINIMAX_API_KEY"] = "server-minimax-key"
        gateway.generate_code_with_llm = fake_generate_code_with_llm
        try:
            status, response = gateway.generate_manim_code_for_gateway(
                {
                    "prompt": "解释消费者剩余",
                    "provider": "trial-kimi-priority",
                    "apiKey": "client-key-must-be-ignored",
                    "baseUrl": "https://evil.example/v1",
                    "endpoint": "https://evil.example/v1/chat/completions",
                }
            )
        finally:
            gateway.generate_code_with_llm = original

        assert status == 200
        assert response["ok"] is True
        assert response["provider"] == "trial-kimi-priority"
        assert response["endpoint"] == "server-managed-trial"
        assert calls[0]["provider_id"] == "kimi-code"
        assert calls[0]["api_key"] == "server-kimi-key"
        assert calls[0]["base_url"] == ""
        assert calls[0]["endpoint"] == ""

    def test_trial_falls_back_to_minimax_when_kimi_fails(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_generate_code_with_llm(**kwargs: object) -> tuple[str, object, str]:
            provider_id = str(kwargs["provider_id"])
            calls.append(kwargs)
            if provider_id == "kimi-code":
                raise RuntimeError("Kimi Code API HTTP 429: quota exceeded")
            provider = gateway.resolve_provider(provider_id)
            return (
                "from manim import *\nclass GeneratedScene(Scene):\n"
                "    def construct(self):\n"
                "        self.play(Write(Text('消费者剩余', font_size=24)))\n",
                provider,
                "hidden",
            )

        original = gateway.generate_code_with_llm
        os.environ["KIMI_CODE_API_KEY"] = "server-kimi-key"
        os.environ["MINIMAX_API_KEY"] = "server-minimax-key"
        gateway.generate_code_with_llm = fake_generate_code_with_llm
        try:
            status, response = gateway.generate_manim_code_for_gateway(
                {"prompt": "解释消费者剩余", "provider": "trial-kimi-priority"}
            )
        finally:
            gateway.generate_code_with_llm = original

        assert status == 200
        assert response["ok"] is True
        assert [str(call["provider_id"]) for call in calls] == ["kimi-code", "minimax-coding-cn"]
        assert calls[0]["timeout"] == gateway.PUBLIC_TRIAL_KIMI_TIMEOUT_SECONDS
        assert calls[1]["timeout"] == gateway.PUBLIC_TRIAL_MINIMAX_TIMEOUT_SECONDS
        assert "Public hosted quality contract" in str(calls[1]["user_prompt"])
        assert "MiniMax" in "\n".join(response["warnings"])
        assert "quota" in "\n".join(response["warnings"])
        assert "detail" not in response

    def test_trial_uses_minimax_between_kimi_and_deepseek(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_generate_code_with_llm(**kwargs: object) -> tuple[str, object, str]:
            provider_id = str(kwargs["provider_id"])
            calls.append(kwargs)
            if provider_id == "kimi-code":
                raise RuntimeError("Kimi Code API HTTP 403: access denied")
            provider = gateway.resolve_provider(provider_id)
            return (
                "from manim import *\nclass GeneratedScene(Scene):\n"
                "    def construct(self):\n"
                "        self.play(Write(Text('消费者剩余', font_size=28)))\n",
                provider,
                "hidden",
            )

        original = gateway.generate_code_with_llm
        os.environ["KIMI_CODE_API_KEY"] = "server-kimi-key"
        os.environ["DEEPSEEK_API_KEY"] = "server-deepseek-key"
        os.environ["MINIMAX_API_KEY"] = "server-minimax-key"
        gateway.generate_code_with_llm = fake_generate_code_with_llm
        try:
            status, response = gateway.generate_manim_code_for_gateway(
                {"prompt": "解释消费者剩余", "provider": "trial-kimi-priority"}
            )
        finally:
            gateway.generate_code_with_llm = original

        assert status == 200
        assert response["ok"] is True
        assert [str(call["provider_id"]) for call in calls] == ["kimi-code", "minimax-coding-cn"]
        assert calls[1]["api_key"] == "server-minimax-key"
        assert calls[1]["model"] == "MiniMax-M2.7"
        assert calls[1]["timeout"] == gateway.PUBLIC_TRIAL_MINIMAX_TIMEOUT_SECONDS
        warnings = "\n".join(response["warnings"])
        assert "MiniMax" in warnings
        assert "权限/白名单/套餐额度问题" in warnings
        assert "kimi-code:access" in warnings

    def test_trial_falls_back_to_deepseek_after_minimax_failure(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_generate_code_with_llm(**kwargs: object) -> tuple[str, object, str]:
            provider_id = str(kwargs["provider_id"])
            calls.append(kwargs)
            if provider_id == "kimi-code":
                raise RuntimeError("Kimi Code API HTTP 403: access denied")
            if provider_id == "minimax-coding-cn":
                raise TimeoutError("MiniMax timed out")
            provider = gateway.resolve_provider(provider_id)
            return (
                "from manim import *\nclass GeneratedScene(Scene):\n"
                "    def construct(self):\n"
                "        self.play(Write(Text('消费者剩余', font_size=28)))\n",
                provider,
                "hidden",
            )

        original = gateway.generate_code_with_llm
        os.environ["KIMI_CODE_API_KEY"] = "server-kimi-key"
        os.environ["DEEPSEEK_API_KEY"] = "server-deepseek-key"
        os.environ["MINIMAX_API_KEY"] = "server-minimax-key"
        gateway.generate_code_with_llm = fake_generate_code_with_llm
        try:
            status, response = gateway.generate_manim_code_for_gateway(
                {"prompt": "解释消费者剩余", "provider": "trial-kimi-priority"}
            )
        finally:
            gateway.generate_code_with_llm = original

        assert status == 200
        assert response["ok"] is True
        assert [str(call["provider_id"]) for call in calls] == ["kimi-code", "minimax-coding-cn", "deepseek"]
        assert calls[1]["timeout"] == gateway.PUBLIC_TRIAL_MINIMAX_TIMEOUT_SECONDS
        assert calls[2]["timeout"] == gateway.PUBLIC_TRIAL_DEEPSEEK_TIMEOUT_SECONDS
        warnings = "\n".join(response["warnings"])
        assert "DeepSeek" in warnings
        assert "kimi-code:access" in warnings
        assert "minimax-coding-cn:timeout" in warnings

    def test_minimax_direct_uses_longer_timeout_and_teaching_contract(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_generate_code_with_llm(**kwargs: object) -> tuple[str, object, str]:
            calls.append(kwargs)
            provider = gateway.resolve_provider(str(kwargs["provider_id"]))
            return (
                "from manim import *\nclass GeneratedScene(Scene):\n"
                "    def construct(self):\n"
                "        self.play(Write(Text('税收楔子', font_size=28)))\n",
                provider,
                "hidden",
            )

        original = gateway.generate_code_with_llm
        os.environ["MINIMAX_API_KEY"] = "server-minimax-key"
        gateway.generate_code_with_llm = fake_generate_code_with_llm
        try:
            status, response = gateway.generate_manim_code_for_gateway(
                {"prompt": "解释税收楔子如何造成无谓损失", "provider": "trial-minimax-direct"}
            )
        finally:
            gateway.generate_code_with_llm = original

        assert status == 200
        assert response["ok"] is True
        assert len(calls) == 1
        assert calls[0]["provider_id"] == "minimax-coding-cn"
        assert calls[0]["timeout"] == gateway.PUBLIC_TRIAL_MINIMAX_TIMEOUT_SECONDS
        user_prompt = str(calls[0]["user_prompt"])
        assert "教学 brief" in user_prompt
        assert "4-6 visual beats" in user_prompt
        assert "Chinese-first visible text contract" in user_prompt
        assert "translate it before putting text into Text" in user_prompt
        assert "价格 P" in user_prompt
        assert "FadeOut the old caption" in user_prompt
        assert "do not leave English prose" in user_prompt

    def test_trial_repairs_static_precheck_errors_before_returning_code(self) -> None:
        calls: list[str] = []

        def fake_generate_code_with_llm(**kwargs: object) -> tuple[str, object, str]:
            calls.append(str(kwargs["user_prompt"]))
            provider = gateway.resolve_provider(str(kwargs["provider_id"]))
            if len(calls) == 1:
                return "print('not a manim scene')\n", provider, "hidden"
            return (
                "from manim import *\nclass GeneratedScene(Scene):\n"
                "    def construct(self):\n"
                "        self.play(Write(Text('税收楔子', font_size=28)))\n",
                provider,
                "hidden",
            )

        original = gateway.generate_code_with_llm
        os.environ["MINIMAX_API_KEY"] = "server-minimax-key"
        gateway.generate_code_with_llm = fake_generate_code_with_llm
        try:
            status, response = gateway.generate_manim_code_for_gateway(
                {"prompt": "解释税收楔子", "provider": "trial-minimax-direct"}
            )
        finally:
            gateway.generate_code_with_llm = original

        assert status == 200
        assert response["ok"] is True
        assert len(calls) == 2
        assert "pre-render quality gate" in calls[1]
        assert "No class inheriting from Scene was found" in calls[1]
        assert "税收楔子" in str(response["code"])

    def test_trial_response_uses_detected_scene_name(self) -> None:
        def fake_generate_code_with_llm(**kwargs: object) -> tuple[str, object, str]:
            provider = gateway.resolve_provider(str(kwargs["provider_id"]))
            return (
                "from manim import *\nclass ParetoOptimalityScene(Scene):\n"
                "    def construct(self):\n"
                "        self.play(Write(Text('帕累托最优', font_size=28)))\n",
                provider,
                "hidden",
            )

        original = gateway.generate_code_with_llm
        os.environ["KIMI_CODE_API_KEY"] = "server-kimi-key"
        gateway.generate_code_with_llm = fake_generate_code_with_llm
        try:
            status, response = gateway.generate_manim_code_for_gateway(
                {
                    "prompt": "将帕累托最优的过程可视化。",
                    "provider": "trial-kimi-priority",
                    "sceneName": "GeneratedScene",
                }
            )
        finally:
            gateway.generate_code_with_llm = original

        assert status == 200
        assert response["sceneName"] == "ParetoOptimalityScene"
        assert response["sceneNameInput"] == "GeneratedScene"

    def test_trial_regenerates_when_generated_code_exceeds_hosted_render_budget(self) -> None:
        calls: list[str] = []

        def fake_generate_code_with_llm(**kwargs: object) -> tuple[str, object, str]:
            calls.append(str(kwargs["user_prompt"]))
            provider = gateway.resolve_provider(str(kwargs["provider_id"]))
            if len(calls) == 1:
                heavy = "\n".join("        self.play(FadeIn(Dot()))" for _ in range(30))
                return (
                    "from manim import *\nclass GeneratedScene(Scene):\n    def construct(self):\n"
                    + heavy
                    + "\n",
                    provider,
                    "hidden",
                )
            return (
                "from manim import *\nclass GeneratedScene(Scene):\n    def construct(self):\n"
                "        self.play(Write(Text('短例子', font_size=24)))\n",
                provider,
                "hidden",
            )

        original = gateway.generate_code_with_llm
        os.environ["KIMI_CODE_API_KEY"] = "server-kimi-key"
        gateway.generate_code_with_llm = fake_generate_code_with_llm
        try:
            status, response = gateway.generate_manim_code_for_gateway(
                {
                    "prompt": "将帕累托最优的过程可视化。",
                    "provider": "trial-kimi-priority",
                    "sceneName": "GeneratedScene",
                }
            )
        finally:
            gateway.generate_code_with_llm = original

        assert status == 200
        assert response["ok"] is True
        assert len(calls) == 2
        assert "Hosted render budget correction" in calls[1]
        assert f"at most {gateway.MAX_PUBLIC_RENDER_PLAYS} self.play" in calls[1]
        assert str(response["code"]).count("self.play(") == 1

    def test_trial_uses_stable_template_when_repair_still_exceeds_budget(self) -> None:
        def fake_generate_code_with_llm(**kwargs: object) -> tuple[str, object, str]:
            provider = gateway.resolve_provider(str(kwargs["provider_id"]))
            heavy = "\n".join("        self.play(Write(Text('x', font_size=24)))" for _ in range(45))
            return (
                "from manim import *\nclass GeneratedScene(Scene):\n    def construct(self):\n"
                + heavy
                + "\n",
                provider,
                "hidden",
            )

        original = gateway.generate_code_with_llm
        os.environ["MINIMAX_API_KEY"] = "server-minimax-key"
        gateway.generate_code_with_llm = fake_generate_code_with_llm
        try:
            status, response = gateway.generate_manim_code_for_gateway(
                {
                    "prompt": "可视化帕累托最优过程。",
                    "provider": "trial-minimax-direct",
                    "sceneName": "GeneratedScene",
                }
            )
        finally:
            gateway.generate_code_with_llm = original

        assert status == 200
        assert response["model"] == "stable-template-fallback"
        assert "不能让一人更好" in str(response["code"])

    def test_trial_accepts_soft_budget_overage_for_segmented_rendering(self) -> None:
        def fake_generate_code_with_llm(**kwargs: object) -> tuple[str, object, str]:
            provider = gateway.resolve_provider(str(kwargs["provider_id"]))
            medium = "\n".join("        self.play(FadeIn(Dot()))" for _ in range(30))
            return (
                "from manim import *\nclass GeneratedScene(Scene):\n    def construct(self):\n"
                + medium
                + "\n",
                provider,
                "hidden",
            )

        original = gateway.generate_code_with_llm
        os.environ["MINIMAX_API_KEY"] = "server-minimax-key"
        gateway.generate_code_with_llm = fake_generate_code_with_llm
        try:
            status, response = gateway.generate_manim_code_for_gateway(
                {
                    "prompt": "可视化帕累托最优过程。",
                    "provider": "trial-minimax-direct",
                    "sceneName": "GeneratedScene",
                }
            )
        finally:
            gateway.generate_code_with_llm = original

        assert status == 200
        assert response["model"] == "MiniMax 稳定试用"
        assert response["codeFile"] == "vercel-generated-code"
        assert str(response["code"]).count("self.play(") == 30
        assert "略超软预算" in "\n".join(response["warnings"])

    def test_trial_returns_stable_template_when_server_models_are_unavailable(self) -> None:
        def fake_generate_code_with_llm(**kwargs: object) -> tuple[str, object, str]:
            raise TimeoutError("provider timed out")

        original = gateway.generate_code_with_llm
        os.environ["MINIMAX_API_KEY"] = "server-minimax-key"
        gateway.generate_code_with_llm = fake_generate_code_with_llm
        try:
            status, response = gateway.generate_manim_code_for_gateway(
                {
                    "prompt": "解释线性增长为什么会累积差距",
                    "sceneName": "GeneratedScene",
                }
            )
        finally:
            gateway.generate_code_with_llm = original

        assert status == 200
        assert response["ok"] is True
        assert response["model"] == "stable-template-fallback"
        assert response["endpoint"] == "server-managed-fallback"
        assert "class GeneratedScene(Scene)" in str(response["code"])
        assert "_AEGIS_CJK_FONT" in str(response["code"])
        assert "稳定模板" in "\n".join(response["warnings"])
        assert "模型失败类别" in "\n".join(response["warnings"])

    def test_pareto_fallback_uses_topic_specific_teaching_scene(self) -> None:
        code = gateway.build_fallback_manim_code("可视化帕累托最优过程。", "GeneratedScene")
        patched, notes = gateway.apply_runtime_compatibility_fixes(code)

        assert "不能让一人更好" in patched
        assert "Axes(" in patched
        assert "frontier" in patched
        assert patched.count("self.play(") >= 6
        assert "_AEGIS_CJK_FONT" in patched
        assert any("CJK-capable" in note for note in notes)

    def test_tax_wedge_fallback_uses_supply_demand_teaching_scene(self) -> None:
        code = gateway.build_fallback_manim_code(
            "tax wedge deadweight loss supply demand buyer price seller price",
            "GeneratedScene",
        )
        patched, notes = gateway.apply_runtime_compatibility_fixes(code)

        assert "税收楔子与无谓损失" in patched
        assert "需求 D" in patched
        assert "供给 S" in patched
        assert "税收收入" in patched
        assert "无谓损失" in patched
        assert "Polygon(" in patched
        assert "_AEGIS_CJK_FONT" in patched
        assert any("CJK-capable" in note for note in notes)

    def test_two_part_pricing_prompt_does_not_use_tax_wedge_fallback(self) -> None:
        prompt = (
            "可视化垄断厂商的二部定价如何提取消费者剩余。请用需求曲线、边际成本曲线、"
            "垄断定价点、有效率产量点、消费者剩余区域、固定入场费区域和总利润变化。"
        )

        code = gateway.build_fallback_manim_code(prompt, "GeneratedScene")
        patched, notes = gateway.apply_runtime_compatibility_fixes(code)

        assert gateway.is_tax_wedge_prompt(prompt) is False
        assert "二部定价" in patched
        assert "固定入场费" in patched
        assert "消费者剩余" in patched
        assert "边际成本 MC" in patched
        assert "税收楔子" not in patched
        assert "_AEGIS_CJK_FONT" in patched
        assert any("CJK-capable" in note for note in notes)

    def test_two_part_pricing_prompt_with_deadweight_loss_keeps_topic_fallback(self) -> None:
        prompt = (
            "考研经济学题：用中文动画解释垄断厂商实行二部定价时的福利变化。"
            "请比较普通线性垄断定价与二部定价，说明为什么二部定价能消除无谓损失。"
        )

        code = gateway.build_fallback_manim_code(prompt, "GeneratedScene")

        assert gateway.is_tax_wedge_prompt(prompt) is True
        assert gateway.is_two_part_pricing_prompt(prompt) is True
        assert "二部定价" in code
        assert "固定入场费" in code
        assert "税收楔子" not in code

    def test_standard_monopoly_prompt_with_deadweight_loss_keeps_topic_fallback(self) -> None:
        prompt = (
            "使用Manim创建一个经济学垄断模型动画。绘制需求曲线D、边际收益曲线MR、"
            "边际成本曲线MC，标出垄断利润和无谓损失DWL。"
        )

        code = gateway.build_fallback_manim_code(prompt, "GeneratedScene")
        patched, notes = gateway.apply_runtime_compatibility_fixes(code)

        assert gateway.is_tax_wedge_prompt(prompt) is True
        assert gateway.is_standard_monopoly_prompt(prompt) is True
        assert "垄断定价与福利损失" in patched
        assert "边际收益 MR" in patched
        assert "边际成本 MC" in patched
        assert "垄断利润" in patched
        assert "无谓损失" in patched
        assert "税收楔子" not in patched
        assert "_AEGIS_CJK_FONT" in patched
        assert any("CJK-capable" in note for note in notes)

    def test_consumer_choice_prompt_uses_topic_fallback(self) -> None:
        prompt = (
            "经济学考研题：消费者选择与价格效应。请画出预算线、无差异曲线、"
            "补偿预算线，并标出 A 到 B 的替代效应和 B 到 C 的收入效应。"
        )

        code = gateway.build_fallback_manim_code(prompt, "GeneratedScene")
        patched, notes = gateway.apply_runtime_compatibility_fixes(code)

        assert gateway.is_consumer_choice_prompt(prompt) is True
        assert "消费者选择与价格效应" in patched
        assert "预算线" in patched
        assert "无差异曲线" in patched
        assert "补偿预算线" in patched
        assert "替代效应" in patched
        assert "收入效应" in patched
        assert '"A"' in patched
        assert '"B"' in patched
        assert '"C"' in patched
        assert "税收楔子" not in patched
        assert "_AEGIS_CJK_FONT" in patched
        assert any("CJK-capable" in note for note in notes)

    def test_default_trial_uses_fast_stable_template_for_two_part_pricing(self) -> None:
        def fail_if_called(**kwargs: object) -> tuple[str, object, str]:
            raise AssertionError("two-part pricing default path should not wait for external model calls")

        original = gateway.generate_code_with_llm
        os.environ["KIMI_CODE_API_KEY"] = "server-kimi-key"
        gateway.generate_code_with_llm = fail_if_called
        try:
            status, response = gateway.generate_manim_code_for_gateway(
                {
                    "prompt": (
                        "考研经济学题：比较普通线性垄断定价与二部定价，"
                        "说明固定入场费如何提取消费者剩余并消除无谓损失。"
                    ),
                    "provider": "trial-kimi-priority",
                    "sceneName": "GeneratedScene",
                }
            )
        finally:
            gateway.generate_code_with_llm = original

        assert status == 200
        assert response["model"] == "stable-template-fallback"
        assert "二部定价" in str(response["code"])
        assert "税收楔子" not in str(response["code"])
        assert "优先使用中文稳定模板" in "\n".join(response["warnings"])

    def test_default_trial_uses_fast_stable_template_for_standard_monopoly(self) -> None:
        def fail_if_called(**kwargs: object) -> tuple[str, object, str]:
            raise AssertionError("standard-monopoly default path should not wait for external model calls")

        original = gateway.generate_code_with_llm
        os.environ["KIMI_CODE_API_KEY"] = "server-kimi-key"
        gateway.generate_code_with_llm = fail_if_called
        try:
            status, response = gateway.generate_manim_code_for_gateway(
                {
                    "prompt": (
                        "考研经济学题：解释垄断定价。请画出需求曲线D、边际收益MR、"
                        "边际成本MC、垄断利润和无谓损失DWL。"
                    ),
                    "provider": "trial-kimi-priority",
                    "sceneName": "GeneratedScene",
                }
            )
        finally:
            gateway.generate_code_with_llm = original

        assert status == 200
        assert response["model"] == "stable-template-fallback"
        assert "垄断定价与福利损失" in str(response["code"])
        assert "边际收益 MR" in str(response["code"])
        assert "边际成本 MC" in str(response["code"])
        assert "税收楔子" not in str(response["code"])
        assert "优先使用中文稳定模板" in "\n".join(response["warnings"])

    def test_default_trial_uses_fast_stable_template_for_consumer_choice(self) -> None:
        def fail_if_called(**kwargs: object) -> tuple[str, object, str]:
            raise AssertionError("consumer-choice default path should not wait for external model calls")

        original = gateway.generate_code_with_llm
        os.environ["KIMI_CODE_API_KEY"] = "server-kimi-key"
        gateway.generate_code_with_llm = fail_if_called
        try:
            status, response = gateway.generate_manim_code_for_gateway(
                {
                    "prompt": (
                        "考研经济学题：消费者选择与价格效应。请画预算线、无差异曲线、"
                        "补偿预算线，并解释替代效应和收入效应。"
                    ),
                    "provider": "trial-kimi-priority",
                    "sceneName": "GeneratedScene",
                }
            )
        finally:
            gateway.generate_code_with_llm = original

        assert status == 200
        assert response["model"] == "stable-template-fallback"
        assert "消费者选择与价格效应" in str(response["code"])
        assert "替代效应" in str(response["code"])
        assert "收入效应" in str(response["code"])
        assert "税收楔子" not in str(response["code"])
        assert "优先使用中文稳定模板" in "\n".join(response["warnings"])

    def test_default_trial_uses_fast_stable_template_for_tax_wedge(self) -> None:
        def fail_if_called(**kwargs: object) -> tuple[str, object, str]:
            raise AssertionError("tax-wedge default path should not wait for external model calls")

        original = gateway.generate_code_with_llm
        os.environ["KIMI_CODE_API_KEY"] = "server-kimi-key"
        gateway.generate_code_with_llm = fail_if_called
        try:
            status, response = gateway.generate_manim_code_for_gateway(
                {
                    "prompt": (
                        "考研经济学题：解释从量税如何形成税收楔子，"
                        "标出买方价格、卖方价格、税收收入和无谓损失。"
                    ),
                    "provider": "trial-kimi-priority",
                    "sceneName": "GeneratedScene",
                }
            )
        finally:
            gateway.generate_code_with_llm = original

        assert status == 200
        assert response["model"] == "stable-template-fallback"
        assert "税收楔子" in str(response["code"])
        assert "税收收入" in str(response["code"])
        assert "二部定价" not in str(response["code"])
        assert "优先使用中文稳定模板" in "\n".join(response["warnings"])

    def test_tax_wedge_trial_falls_back_when_model_misses_required_economics_objects(self) -> None:
        def fake_generate_code_with_llm(**kwargs: object) -> tuple[str, object, str]:
            provider = gateway.resolve_provider(str(kwargs["provider_id"]))
            return (
                "from manim import *\nclass GeneratedScene(Scene):\n"
                "    def construct(self):\n"
                "        axes = Axes(x_range=[0, 10, 1], y_range=[0, 8, 1])\n"
                "        self.play(Create(axes))\n"
                "        self.play(Write(Text('税收楔子与无谓损失', font_size=28)))\n",
                provider,
                "hidden",
            )

        original = gateway.generate_code_with_llm
        os.environ["MINIMAX_API_KEY"] = "server-minimax-key"
        gateway.generate_code_with_llm = fake_generate_code_with_llm
        try:
            status, response = gateway.generate_manim_code_for_gateway(
                {
                    "prompt": "解释税收楔子如何造成 deadweight loss，并展示 tax revenue。",
                    "provider": "trial-minimax-direct",
                    "sceneName": "GeneratedScene",
                }
            )
        finally:
            gateway.generate_code_with_llm = original

        assert status == 200
        assert response["model"] == "stable-template-fallback"
        assert "税收收入" in str(response["code"])
        assert "买方价上升" in str(response["code"])
        assert "topic-quality" in "\n".join(response["warnings"])

    def test_two_part_pricing_trial_falls_back_when_model_misses_required_objects(self) -> None:
        def fake_generate_code_with_llm(**kwargs: object) -> tuple[str, object, str]:
            provider = gateway.resolve_provider(str(kwargs["provider_id"]))
            return (
                "from manim import *\nclass GeneratedScene(Scene):\n"
                "    def construct(self):\n"
                "        axes = Axes(x_range=[0, 10, 1], y_range=[0, 8, 1])\n"
                "        self.play(Create(axes))\n"
                "        self.play(Write(Text('垄断厂商定价', font_size=28)))\n",
                provider,
                "hidden",
            )

        original = gateway.generate_code_with_llm
        os.environ["MINIMAX_API_KEY"] = "server-minimax-key"
        gateway.generate_code_with_llm = fake_generate_code_with_llm
        try:
            status, response = gateway.generate_manim_code_for_gateway(
                {
                    "prompt": "可视化垄断厂商的二部定价如何提取消费者剩余，并比较线性垄断定价。",
                    "provider": "trial-minimax-direct",
                    "sceneName": "GeneratedScene",
                }
            )
        finally:
            gateway.generate_code_with_llm = original

        assert status == 200
        assert response["model"] == "stable-template-fallback"
        assert "二部定价" in str(response["code"])
        assert "固定入场费" in str(response["code"])
        assert "topic-quality" in "\n".join(response["warnings"])

    def test_two_part_pricing_trial_falls_back_when_model_script_is_too_heavy(self) -> None:
        heavy_plays = "\n".join(
            "        self.play(FadeIn(Dot()))"
            for _ in range(gateway.MAX_PUBLIC_RENDER_PLAYS + 2)
        )

        def fake_generate_code_with_llm(**kwargs: object) -> tuple[str, object, str]:
            provider = gateway.resolve_provider(str(kwargs["provider_id"]))
            return (
                "from manim import *\nclass GeneratedScene(Scene):\n"
                "    def construct(self):\n"
                "        # 二部定价 消费者剩余 固定入场费 边际成本 垄断定价 有效率产量\n"
                "        region = Polygon(LEFT, RIGHT, UP)\n"
                + heavy_plays
                + "\n",
                provider,
                "hidden",
            )

        original = gateway.generate_code_with_llm
        os.environ["MINIMAX_API_KEY"] = "server-minimax-key"
        gateway.generate_code_with_llm = fake_generate_code_with_llm
        try:
            status, response = gateway.generate_manim_code_for_gateway(
                {
                    "prompt": "可视化垄断厂商的二部定价如何提取消费者剩余，并比较线性垄断定价。",
                    "provider": "trial-minimax-direct",
                    "sceneName": "GeneratedScene",
                }
            )
        finally:
            gateway.generate_code_with_llm = original

        assert status == 200
        assert response["model"] == "stable-template-fallback"
        assert str(response["code"]).count("self.play(") < gateway.MAX_PUBLIC_RENDER_PLAYS
        assert "二部定价" in str(response["code"])
        assert "topic-budget" in "\n".join(response["warnings"])

    def test_two_part_pricing_trial_falls_back_for_segment_timeout_risky_constructs(self) -> None:
        risky_code = (
            "from manim import *\n"
            "class GeneratedScene(Scene):\n"
            "    def construct(self):\n"
            "        self.play(Write(Text('二部定价 消费者剩余 固定入场费 边际成本 垄断定价 有效率产量', font_size=24)))\n"
            "        region = Polygon(LEFT, RIGHT, UP)\n"
            "        brace = BraceLabel(region, '固定入场费', label_constructor=Text)\n"
            "        self.play(LaggedStart(FadeIn(region), FadeIn(brace)))\n"
        )

        def fake_generate_code_with_llm(**kwargs: object) -> tuple[str, object, str]:
            provider = gateway.resolve_provider(str(kwargs["provider_id"]))
            return risky_code, provider, "hidden"

        original = gateway.generate_code_with_llm
        os.environ["MINIMAX_API_KEY"] = "server-minimax-key"
        gateway.generate_code_with_llm = fake_generate_code_with_llm
        try:
            status, response = gateway.generate_manim_code_for_gateway(
                {
                    "prompt": "可视化垄断厂商的二部定价如何提取消费者剩余，并比较线性垄断定价。",
                    "provider": "trial-minimax-direct",
                    "sceneName": "GeneratedScene",
                }
            )
        finally:
            gateway.generate_code_with_llm = original

        warnings = "\n".join(response["warnings"])
        assert status == 200
        assert response["model"] == "stable-template-fallback"
        assert "BraceLabel" not in str(response["code"])
        assert "LaggedStart" not in str(response["code"])
        assert "topic-budget" in warnings

    def test_public_gateway_rejects_arbitrary_provider_and_long_prompt(self) -> None:
        status, response = gateway.generate_manim_code_for_gateway(
            {"prompt": "解释消费者剩余", "provider": "custom-openai"}
        )
        assert status == 400
        assert "内置免费试用模型" in response["error"]

        status, response = gateway.generate_manim_code_for_gateway(
            {"prompt": "x" * (gateway.MAX_PUBLIC_PROMPT_CHARS + 1)}
        )
        assert status == 400
        assert "问题太长" in response["error"]

    def test_public_html_contains_render_poll_and_playback_flow(self) -> None:
        html = gateway.build_index_html()

        assert 'fetch("/api/render"' in html
        assert "/api/render/status/" in html
        assert "/api/render/download/" in html
        assert "video_url" in html
        assert 'dlResp.headers.get("content-type")' in html
        assert "if (!statusResp.ok)" in html
        assert "渲染失败" in html

    def test_render_proxy_accepts_snake_case_scene_name_and_detects_code_class(self) -> None:
        render_payload, error_payload = gateway.build_render_backend_submit_payload(
            {
                "code": (
                    "from manim import *\n"
                    "class ParetoOptimalScene(Scene):\n"
                    "    def construct(self):\n"
                    "        self.play(Write(Text('帕累托最优')))\n"
                ),
                "scene_name": "GeneratedScene",
                "render_mode": "auto",
            }
        )

        assert error_payload is None
        assert render_payload is not None
        assert render_payload["scene_name"] == "ParetoOptimalScene"
        assert render_payload["render_mode"] == "auto"

    def test_community_search_proxy_forwards_query_to_render_backend(self) -> None:
        calls: list[tuple[str, str, dict[str, object] | None]] = []

        def fake_proxy(path, method="GET", payload=None, timeout=15):
            calls.append((path, method, payload))
            return 200, {"ok": True, "hit": False, "items": []}

        original = gateway._proxy_to_render_backend
        gateway._proxy_to_render_backend = fake_proxy
        try:
            status, response = gateway.proxy_community_request(
                "/api/community/search",
                query="q=%E5%B8%95%E7%B4%AF%E6%89%98&limit=1",
            )
        finally:
            gateway._proxy_to_render_backend = original

        assert status == 200
        assert response["ok"] is True
        assert calls == [("/community/search?q=%E5%B8%95%E7%B4%AF%E6%89%98&limit=1", "GET", None)]

    def test_community_write_proxy_forwards_safe_payload_to_render_backend(self) -> None:
        calls: list[tuple[str, str, dict[str, object] | None]] = []

        def fake_proxy(path, method="GET", payload=None, timeout=15):
            calls.append((path, method, payload))
            return 200, {"ok": True, "work": {"workId": "work-1"}}

        original = gateway._proxy_to_render_backend
        gateway._proxy_to_render_backend = fake_proxy
        try:
            status, response = gateway.proxy_community_request(
                "/api/community/works/work-1/rating",
                method="POST",
                payload={"rating": 5, "raterKey": "anon-1"},
            )
        finally:
            gateway._proxy_to_render_backend = original

        assert status == 200
        assert response["ok"] is True
        assert calls == [
            ("/community/works/work-1/rating", "POST", {"rating": 5, "raterKey": "anon-1"})
        ]

    def test_vercel_asgi_forwards_community_search_query(self) -> None:
        calls: list[tuple[str, str, str, dict[str, object] | None]] = []

        def fake_community_proxy(route, query="", method="GET", payload=None):
            calls.append((route, query, method, payload))
            return 200, {"ok": True, "hit": True, "items": [{"workId": "work-1"}]}

        original = vercel_asgi.proxy_community_request
        vercel_asgi.proxy_community_request = fake_community_proxy
        try:
            status, response = asyncio.run(
                call_asgi_app(
                    "GET",
                    "/api/community/search",
                    query_string=b"q=%E5%B8%95%E7%B4%AF%E6%89%98&limit=1",
                )
            )
        finally:
            vercel_asgi.proxy_community_request = original

        assert status == 200
        assert response["hit"] is True
        assert calls == [
            ("/api/community/search", "q=%E5%B8%95%E7%B4%AF%E6%89%98&limit=1", "GET", None)
        ]

    def test_vercel_asgi_forwards_community_write_payload(self) -> None:
        calls: list[tuple[str, str, dict[str, object] | None]] = []

        def fake_community_proxy(route, query="", method="GET", payload=None):
            calls.append((route, method, payload))
            return 200, {"ok": True, "reuseCount": 2}

        original = vercel_asgi.proxy_community_request
        vercel_asgi.proxy_community_request = fake_community_proxy
        try:
            status, response = asyncio.run(
                call_asgi_app(
                    "POST",
                    "/api/community/works/work-1/reuse",
                    body=b'{"userKey":"anon-1"}',
                )
            )
        finally:
            vercel_asgi.proxy_community_request = original

        assert status == 200
        assert response["ok"] is True
        assert calls == [("/api/community/works/work-1/reuse", "POST", {"userKey": "anon-1"})]

    def test_download_proxy_extracts_safe_video_redirect_url(self) -> None:
        url = "https://example.supabase.co/storage/v1/object/public/manim-videos/job/video.mp4"

        assert gateway._extract_download_video_url({"video_url": url}) == url
        assert gateway._extract_download_video_url({"video_url": "javascript:alert(1)"}) is None
        assert gateway._extract_download_video_url({"video_url": "/relative/video.mp4"}) is None

    def test_render_proxy_retries_after_cold_start_connection_error(self) -> None:
        old_url = gateway.RENDER_BACKEND_URL
        gateway.RENDER_BACKEND_URL = "https://render.example"
        calls: list[str] = []

        def fake_urlopen(req, timeout=15):
            calls.append(req.full_url)
            if len(calls) == 1:
                raise URLError("cold")
            return FakeUrlopenResponse(202, b'{"job_id":"job-1","status":"pending"}')

        original_urlopen = gateway.urllib_request.urlopen
        original_sleep = gateway.time.sleep
        gateway.urllib_request.urlopen = fake_urlopen
        gateway.time.sleep = lambda *_: None
        try:
            status, response = gateway._proxy_to_render_backend(
                "/render-async",
                method="POST",
                payload={"code": "from manim import *", "scene_name": "GeneratedScene"},
            )
        finally:
            gateway.urllib_request.urlopen = original_urlopen
            gateway.time.sleep = original_sleep
            gateway.RENDER_BACKEND_URL = old_url

        assert status == 202
        assert response["job_id"] == "job-1"
        assert calls == [
            "https://render.example/render-async",
            "https://render.example/health",
            "https://render.example/render-async",
        ]

    def test_render_proxy_returns_friendly_error_when_cold_start_retry_fails(self) -> None:
        old_url = gateway.RENDER_BACKEND_URL
        gateway.RENDER_BACKEND_URL = "https://render.example"

        def fail_urlopen(*args, **kwargs):
            raise URLError("still cold")

        original_urlopen = gateway.urllib_request.urlopen
        original_sleep = gateway.time.sleep
        gateway.urllib_request.urlopen = fail_urlopen
        gateway.time.sleep = lambda *_: None
        try:
            status, response = gateway._proxy_to_render_backend("/status/job-1")
        finally:
            gateway.urllib_request.urlopen = original_urlopen
            gateway.time.sleep = original_sleep
            gateway.RENDER_BACKEND_URL = old_url

        assert status == 502
        assert response["ok"] is False
        assert "冷启动" in response["error"]

    def test_asgi_exposes_vision_analyze_route(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_analyze(payload: dict[str, object]) -> tuple[int, dict[str, object]]:
            calls.append(payload)
            return 200, {"ok": True, "suggestedPrompt": "请用中文解释供需曲线。"}

        original_analyze = vercel_asgi.analyze_image_payload
        old_enabled = os.environ.get("AEGIS_VISION_PUBLIC_ENABLED")
        old_command = os.environ.get("KIMI_VISION_CLI_COMMAND")
        os.environ["AEGIS_VISION_PUBLIC_ENABLED"] = "1"
        os.environ["KIMI_VISION_CLI_COMMAND"] = "python3 fake.py {image_path} {prompt_path}"
        vercel_asgi.analyze_image_payload = fake_analyze
        try:
            status, response = asyncio.run(
                call_asgi_app(
                    "POST",
                    "/api/vision/analyze",
                    body=json.dumps({"imageData": "x", "mimeType": "image/png"}).encode("utf-8"),
                )
            )
        finally:
            vercel_asgi.analyze_image_payload = original_analyze
            if old_enabled is None:
                os.environ.pop("AEGIS_VISION_PUBLIC_ENABLED", None)
            else:
                os.environ["AEGIS_VISION_PUBLIC_ENABLED"] = old_enabled
            if old_command is None:
                os.environ.pop("KIMI_VISION_CLI_COMMAND", None)
            else:
                os.environ["KIMI_VISION_CLI_COMMAND"] = old_command

        assert status == 200
        assert response["ok"] is True
        assert response["suggestedPrompt"] == "请用中文解释供需曲线。"
        assert calls == [{"imageData": "x", "mimeType": "image/png"}]

    def test_asgi_vision_route_stays_closed_until_public_gate_enabled(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_analyze(payload: dict[str, object]) -> tuple[int, dict[str, object]]:
            calls.append(payload)
            return 200, {"ok": True}

        original_analyze = vercel_asgi.analyze_image_payload
        old_enabled = os.environ.get("AEGIS_VISION_PUBLIC_ENABLED")
        old_command = os.environ.get("KIMI_VISION_CLI_COMMAND")
        os.environ.pop("AEGIS_VISION_PUBLIC_ENABLED", None)
        os.environ["KIMI_VISION_CLI_COMMAND"] = "python3 fake.py {image_path} {prompt_path}"
        vercel_asgi.analyze_image_payload = fake_analyze
        try:
            status, response = asyncio.run(
                call_asgi_app(
                    "POST",
                    "/api/vision/analyze",
                    body=json.dumps({"imageData": "x", "mimeType": "image/png"}).encode("utf-8"),
                )
            )
        finally:
            vercel_asgi.analyze_image_payload = original_analyze
            if old_enabled is None:
                os.environ.pop("AEGIS_VISION_PUBLIC_ENABLED", None)
            else:
                os.environ["AEGIS_VISION_PUBLIC_ENABLED"] = old_enabled
            if old_command is None:
                os.environ.pop("KIMI_VISION_CLI_COMMAND", None)
            else:
                os.environ["KIMI_VISION_CLI_COMMAND"] = old_command

        assert status == 503
        assert response["code"] == "vision_feature_disabled"
        assert calls == []


if __name__ == "__main__":
    unittest.main()

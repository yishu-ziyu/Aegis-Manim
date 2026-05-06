from __future__ import annotations

import sys
from importlib.util import find_spec
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from api.index import (  # noqa: E402
    APP_VERSION,
    build_health_payload,
    build_index_html,
    generate_manim_code_for_gateway,
    public_provider_config,
)


def main() -> int:
    health = build_health_payload()
    assert health["ok"] is True
    assert health["runtime"] == "vercel-python-function"
    assert health["renderBackend"] == "external-required"
    assert health["version"] == APP_VERSION

    html = build_index_html()
    assert "Aegis Studio Web" in html
    assert "/api/health" in html
    assert "Generate Code" in html
    assert "Vercel 云端模式" in html
    assert "VERCEL · USER-KEY · CODE" in html
    assert "云端无法访问你电脑上的 127.0.0.1 本地代理" in html

    providers = public_provider_config()["providers"]
    assert "codex-cli" not in providers
    assert "codex-local-proxy" not in providers

    status, missing_prompt = generate_manim_code_for_gateway({"prompt": ""})
    assert status == 400
    assert missing_prompt["ok"] is False

    status, disabled_provider = generate_manim_code_for_gateway(
        {"prompt": "解释消费者剩余", "provider": "codex-cli"},
    )
    assert status == 400
    assert disabled_provider["ok"] is False

    status, missing_key = generate_manim_code_for_gateway(
        {"prompt": "解释消费者剩余", "provider": "zhipu"},
    )
    assert status == 400
    assert missing_key["ok"] is False

    if find_spec("fastapi"):
        from app import app

        assert app.title == "Aegis-Manim Vercel Gateway"

    print("Vercel gateway verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

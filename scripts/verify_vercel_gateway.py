from __future__ import annotations

import sys
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


async def call_asgi_app(method: str, path: str, body: bytes = b"") -> tuple[int, dict[str, str], bytes]:
    from app import app

    sent: list[dict[str, object]] = []
    received = False

    async def receive() -> dict[str, object]:
        nonlocal received
        if received:
            return {"type": "http.request", "body": b"", "more_body": False}
        received = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    await app(
        {"type": "http", "method": method, "path": path},
        receive,
        send,
    )

    start = sent[0]
    response = sent[1]
    headers = {
        key.decode("utf-8"): value.decode("utf-8")
        for key, value in start.get("headers", [])
    }
    return int(start["status"]), headers, response.get("body", b"")


def main() -> int:
    import asyncio

    health = build_health_payload()
    assert health["ok"] is True
    assert health["runtime"] == "vercel-python-function"
    assert health["renderBackend"] == "external-required"
    assert health["version"] == APP_VERSION

    html = build_index_html()
    assert "Aegis 经济学动画工作台" in html
    assert "/api/health" in html
    assert "生成动画草稿" in html
    assert "Vercel 云端只展示能力入口" in html
    assert "API Key 只用于本次生成，不写入仓库。" in html
    assert "MiniMax M3 与 Mimo 编程" in html
    assert "免费试用 · Kimi 优先" not in html
    assert "免费试用 · MiniMax M3" in html
    assert "Kimi Code API" in html
    assert "自定义 OpenAI-Compatible" in html
    assert "Codex CLI 登录态" not in html
    assert "aegis.byok.vault.v1" in html
    assert 'data-mode="byok"' in html
    assert "测试连通" in html
    assert 'fetch("/api/byok/preflight"' in html
    vercel_config = (PROJECT_ROOT / "vercel.json").read_text(encoding="utf-8")
    assert '"/api/byok/preflight"' in vercel_config
    assert '"/api/align"' in vercel_config
    assert 'id="communityDrawer"' in html
    assert 'fetch("/api/generate"' in html
    assert 'fetch("/api/generate/start"' not in html
    assert "await waitForJob(data.statusUrl, payload);" not in html
    assert "promptPreview" in html
    assert "function renderRichText" in html
    assert "tex-chtml.js" in html
    assert "script.textContent = segment.script" not in html

    public_config = public_provider_config()
    providers = public_config["providers"]
    assert public_config["defaultProvider"] == "trial-minimax-direct"
    assert public_config["providerStorageKey"] == "aegis.provider.public.v5"
    assert "aegis.provider.public.v5" in html
    assert {"trial-minimax-direct", "trial-mimo-direct", "openai", "custom-openai"} <= set(providers)
    assert providers["trial-minimax-direct"]["serverManaged"] is True
    assert providers["trial-minimax-direct"]["hideApiKey"] is True
    assert providers["trial-minimax-direct"]["defaultModel"] == "MiniMax M3 试用"
    assert "baseURL" not in providers["trial-minimax-direct"]
    assert "apiType" not in providers["trial-minimax-direct"]
    assert "codex-cli" not in providers

    status, missing_prompt = generate_manim_code_for_gateway({"prompt": ""})
    assert status == 400
    assert missing_prompt["ok"] is False

    status, disabled_provider = generate_manim_code_for_gateway(
        {"prompt": "解释消费者剩余", "provider": "codex-cli"},
    )
    assert status == 400
    assert disabled_provider["ok"] is False
    assert "只能在本机使用" in disabled_provider["error"]

    status, private_endpoint = generate_manim_code_for_gateway(
        {
            "prompt": "解释消费者剩余",
            "provider": "custom-openai",
            "apiKey": "test-key",
            "baseUrl": "http://127.0.0.1:8317/api/provider/antigravity/v1",
        },
    )
    assert status == 400
    assert private_endpoint["ok"] is False
    assert "公网 HTTPS 模型端点" in private_endpoint["error"]

    status_code, _headers, body = asyncio.run(call_asgi_app("GET", "/favicon.ico"))
    assert status_code == 204
    assert body == b""

    print("Vercel gateway verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

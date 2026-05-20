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
    assert "Aegis Studio Web" in html
    assert "/api/health" in html
    assert "Generate Code" in html
    assert "Vercel 云端模式" in html
    assert "VERCEL · USER-KEY · CODE" in html
    assert "Codex CLI 登录态（本机）（仅本地）" in html
    assert "下载项目后在本地 Aegis Web 使用的选项" in html
    assert "Vercel 云端无法访问你的本机 Codex" in html
    assert "Vercel 云端只展示能力入口" in html
    assert "云端无法访问你电脑上的 127.0.0.1 本地代理" in html
    assert "例如本地代理" not in html
    assert 'fetch("/api/generate"' in html
    assert 'fetch("/api/generate/start"' not in html
    assert "await waitForJob(data.statusUrl, payload);" not in html
    assert "promptPreview" in html
    assert "function renderRichText" in html
    assert "tex-chtml.js" in html
    assert "script.textContent = segment.script" not in html

    providers = public_provider_config()["providers"]
    assert public_provider_config()["defaultProvider"] == "kimi-code"
    assert providers["kimi-code"]["baseURL"] == "https://api.kimi.com/coding/v1"
    assert providers["kimi-code"]["defaultModel"] == "kimi-for-coding"
    assert providers["codex-cli"]["cloudUnavailable"] is True
    assert providers["codex-local-proxy"]["cloudUnavailable"] is True

    status, missing_prompt = generate_manim_code_for_gateway({"prompt": ""})
    assert status == 400
    assert missing_prompt["ok"] is False

    status, disabled_provider = generate_manim_code_for_gateway(
        {"prompt": "解释消费者剩余", "provider": "codex-cli"},
    )
    assert status == 400
    assert disabled_provider["ok"] is False

    status, private_endpoint = generate_manim_code_for_gateway(
        {
            "prompt": "解释消费者剩余",
            "provider": "openai-compatible",
            "apiKey": "test-key",
            "baseUrl": "http://127.0.0.1:8317/api/provider/antigravity/v1",
        },
    )
    assert status == 400
    assert private_endpoint["ok"] is False
    assert "公网 HTTPS" in private_endpoint["error"]

    status, missing_key = generate_manim_code_for_gateway(
        {"prompt": "解释消费者剩余", "provider": "zhipu"},
    )
    assert status == 400
    assert missing_key["ok"] is False

    status_code, _headers, body = asyncio.run(call_asgi_app("GET", "/favicon.ico"))
    assert status_code == 204
    assert body == b""

    print("Vercel gateway verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

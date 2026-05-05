from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

APP_VERSION = "vercel_gateway_v20260506_1"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = PROJECT_ROOT / "core"
if str(CORE_PATH) not in sys.path:
    sys.path.insert(0, str(CORE_PATH))

from llm_providers import (  # noqa: E402
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    provider_presets_for_ui,
    resolve_provider,
)
from manim_agent import (  # noqa: E402
    apply_runtime_compatibility_fixes,
    extract_python_only,
    generate_code_with_llm,
    load_system_prompt,
)

SYSTEM_PROMPT = load_system_prompt()
DISABLED_CLOUD_PROVIDERS = {"codex-cli", "codex-local-proxy"}


def build_health_payload() -> dict[str, object]:
    return {
        "ok": True,
        "runtime": "vercel-python-function",
        "renderBackend": "external-required",
        "version": APP_VERSION,
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def build_generate_unavailable_payload() -> dict[str, object]:
    return {
        "ok": False,
        "error": "Video rendering is not available on the Vercel gateway.",
        "detail": (
            "Aegis-Manim needs a long-running Python service with Manim, ffmpeg, "
            "and local media storage. Keep Vercel as the public gateway and deploy "
            "the render backend on a VPS, Render, or Fly.io."
        ),
    }


def public_provider_config() -> dict[str, object]:
    config = provider_presets_for_ui()
    providers = dict(config.get("providers", {}))
    for provider_id in DISABLED_CLOUD_PROVIDERS:
        providers.pop(provider_id, None)
    return {**config, "providers": providers}


def clamp_temperature(value: object) -> float:
    try:
        temperature = float(value)
    except (TypeError, ValueError):
        temperature = 0.2
    return max(0.0, min(1.0, temperature))


def generate_manim_code_for_gateway(payload: dict[str, object]) -> tuple[int, dict[str, object]]:
    prompt = str(payload.get("prompt", "")).strip()
    if not prompt:
        return HTTPStatus.BAD_REQUEST, {"ok": False, "error": "请输入要讲清楚的问题。"}

    provider_id = str(payload.get("provider", DEFAULT_PROVIDER)).strip() or DEFAULT_PROVIDER
    if provider_id in DISABLED_CLOUD_PROVIDERS:
        return HTTPStatus.BAD_REQUEST, {
            "ok": False,
            "error": "这个 Provider 只能在本机使用，不能在 Vercel 云端运行。",
        }

    provider = resolve_provider(provider_id)
    api_key = str(payload.get("apiKey", "")).strip()
    model = str(payload.get("model", "")).strip() or provider.default_model or DEFAULT_MODEL
    base_url = str(payload.get("baseUrl", "")).strip()
    endpoint = str(payload.get("endpoint", "")).strip()
    temperature = clamp_temperature(payload.get("temperature", 0.2))

    try:
        raw_code, used_provider, used_endpoint = generate_code_with_llm(
            provider_id=provider.id,
            api_key=api_key,
            base_url=base_url,
            endpoint=endpoint,
            model=model,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=prompt,
            temperature=temperature,
        )
        cleaned_code = extract_python_only(raw_code)
        patched_code, compatibility_notes = apply_runtime_compatibility_fixes(cleaned_code)
    except ValueError as exc:
        return HTTPStatus.BAD_REQUEST, {
            "ok": False,
            "error": str(exc),
        }
    except Exception as exc:
        return HTTPStatus.BAD_GATEWAY, {
            "ok": False,
            "error": "Model request failed.",
            "detail": str(exc),
        }

    return HTTPStatus.OK, {
        "ok": True,
        "provider": used_provider.id,
        "providerName": used_provider.name,
        "model": model,
        "endpoint": used_endpoint,
        "code": patched_code,
        "compatibilityNotes": compatibility_notes,
        "rendered": False,
        "renderBackend": "external-required",
        "message": "Vercel 已生成 Manim 代码；视频渲染需要后端服务承载。",
    }


def build_index_html() -> str:
    health = json.dumps(build_health_payload(), ensure_ascii=False)
    provider_config = json.dumps(public_provider_config(), ensure_ascii=False)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Aegis-Manim</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f6f7f9;
      color: #17181c;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      padding: 32px 18px;
    }}
    main {{
      width: min(1080px, 100%);
      margin: 0 auto;
      background: #ffffff;
      border: 1px solid #e4e7ec;
      border-radius: 8px;
      padding: clamp(28px, 5vw, 56px);
      box-shadow: 0 18px 48px rgba(24, 32, 56, 0.08);
    }}
    .eyebrow {{
      margin: 0 0 16px;
      color: #4761d8;
      font-size: 14px;
      font-weight: 700;
      letter-spacing: 0;
      text-transform: uppercase;
    }}
    h1 {{
      margin: 0;
      max-width: 760px;
      font-size: clamp(32px, 5vw, 56px);
      line-height: 1.05;
      letter-spacing: 0;
    }}
    p {{
      max-width: 720px;
      color: #555c68;
      font-size: 17px;
      line-height: 1.7;
    }}
    .status {{
      display: grid;
      gap: 12px;
      margin-top: 32px;
      padding: 18px;
      border: 1px solid #e8ebf0;
      border-radius: 8px;
      background: #fafbfc;
    }}
    form {{
      display: grid;
      gap: 16px;
      margin-top: 28px;
    }}
    label {{
      display: grid;
      gap: 8px;
      color: #4d5562;
      font-size: 14px;
      font-weight: 700;
    }}
    textarea,
    input,
    select {{
      width: 100%;
      border: 1px solid #d9dee7;
      border-radius: 8px;
      padding: 12px 14px;
      font: inherit;
      color: #17181c;
      background: #fff;
    }}
    textarea {{
      min-height: 118px;
      resize: vertical;
      line-height: 1.6;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
    }}
    button {{
      width: fit-content;
      border: 0;
      border-radius: 8px;
      padding: 12px 18px;
      color: #fff;
      background: #17181c;
      font: inherit;
      font-weight: 800;
      cursor: pointer;
    }}
    button:disabled {{
      cursor: not-allowed;
      opacity: 0.6;
    }}
    pre {{
      overflow: auto;
      max-height: 520px;
      margin: 18px 0 0;
      padding: 18px;
      border-radius: 8px;
      background: #111827;
      color: #e5e7eb;
      font-size: 13px;
      line-height: 1.55;
    }}
    .message {{
      min-height: 24px;
      color: #4d5562;
      font-size: 14px;
      font-weight: 700;
    }}
    .error {{ color: #be123c; }}
    .row {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      color: #30343b;
      font-size: 15px;
    }}
    .row span:first-child {{ color: #697180; }}
    code {{
      padding: 2px 6px;
      border-radius: 6px;
      background: #eef1f6;
      color: #20242b;
      font-size: 14px;
    }}
    @media (max-width: 760px) {{
      main {{ padding: 24px; }}
      .grid {{ grid-template-columns: 1fr; }}
      button {{ width: 100%; }}
    }}
  </style>
</head>
<body>
  <main>
    <p class="eyebrow">Aegis-Manim</p>
    <h1>把抽象知识变成 Manim 动态可视化视频。</h1>
    <p>
      当前 Vercel 部署可直接生成 Manim 代码。完整的视频渲染需要独立后端承载，
      因为 Manim 依赖 ffmpeg、本地媒体目录和更长的任务执行时间。
    </p>
    <section class="status" aria-label="Deployment status">
      <div class="row"><span>Gateway</span><span>Vercel Python Function</span></div>
      <div class="row"><span>Health</span><span><code>/api/health</code></span></div>
      <div class="row"><span>Generate Code</span><span>Available</span></div>
      <div class="row"><span>Render Video</span><span>External service required</span></div>
    </section>
    <form id="generateForm">
      <label>
        你要讲清楚的问题
        <textarea id="prompt" required>可视化帕累托最优过程</textarea>
      </label>
      <div class="grid">
        <label>
          模型服务
          <select id="provider"></select>
        </label>
        <label>
          模型
          <input id="model" autocomplete="off" />
        </label>
      </div>
      <label>
        API Key
        <input id="apiKey" type="password" autocomplete="off" placeholder="仅用于本次请求，不写入仓库" />
      </label>
      <div class="grid">
        <label>
          Base URL
          <input id="baseUrl" autocomplete="off" />
        </label>
        <label>
          Temperature
          <input id="temperature" type="number" min="0" max="1" step="0.1" value="0.2" />
        </label>
      </div>
      <button id="submitBtn" type="submit">Generate Manim Code</button>
      <div id="message" class="message"></div>
    </form>
    <pre id="codeOutput" hidden></pre>
    <script id="health-payload" type="application/json">{health}</script>
    <script id="provider-config" type="application/json">{provider_config}</script>
    <script>
      const config = JSON.parse(document.getElementById("provider-config").textContent);
      const providerSelect = document.getElementById("provider");
      const modelInput = document.getElementById("model");
      const baseUrlInput = document.getElementById("baseUrl");
      const apiKeyInput = document.getElementById("apiKey");
      const messageEl = document.getElementById("message");
      const outputEl = document.getElementById("codeOutput");
      const submitBtn = document.getElementById("submitBtn");

      function optionLabel(provider) {{
        return provider.name + " · " + provider.apiType;
      }}

      Object.entries(config.providers).forEach(([id, provider]) => {{
        const option = document.createElement("option");
        option.value = id;
        option.textContent = optionLabel(provider);
        providerSelect.appendChild(option);
      }});

      function applyProviderDefaults() {{
        const provider = config.providers[providerSelect.value];
        modelInput.value = provider.defaultModel || "";
        baseUrlInput.value = provider.baseURL || "";
        apiKeyInput.placeholder = provider.apiKeyPlaceholder || "API Key...";
      }}

      providerSelect.value = config.defaultProvider in config.providers
        ? config.defaultProvider
        : Object.keys(config.providers)[0];
      applyProviderDefaults();
      providerSelect.addEventListener("change", applyProviderDefaults);

      document.getElementById("generateForm").addEventListener("submit", async (event) => {{
        event.preventDefault();
        messageEl.className = "message";
        messageEl.textContent = "Generating...";
        outputEl.hidden = true;
        outputEl.textContent = "";
        submitBtn.disabled = true;

        try {{
          const response = await fetch("/api/generate", {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{
              prompt: document.getElementById("prompt").value,
              provider: providerSelect.value,
              apiKey: apiKeyInput.value,
              model: modelInput.value,
              baseUrl: baseUrlInput.value,
              temperature: document.getElementById("temperature").value
            }})
          }});
          const data = await response.json();
          if (!response.ok || !data.ok) {{
            throw new Error(data.detail || data.error || "Request failed.");
          }}
          messageEl.textContent = data.message || "Generated.";
          outputEl.textContent = data.code;
          outputEl.hidden = false;
        }} catch (error) {{
          messageEl.className = "message error";
          messageEl.textContent = error.message || String(error);
        }} finally {{
          submitBtn.disabled = false;
        }}
      }});
    </script>
  </main>
</body>
</html>"""


class handler(BaseHTTPRequestHandler):
    def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict[str, object]:
        raw_len = self.headers.get("Content-Length", "0")
        try:
            body_len = int(raw_len)
        except ValueError:
            return {}
        if body_len <= 0:
            return {}
        raw = self.rfile.read(body_len)
        parsed = json.loads(raw.decode("utf-8"))
        if not isinstance(parsed, dict):
            return {}
        return parsed

    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if route == "/":
            self._send_html(build_index_html())
            return
        if route == "/api/health":
            self._send_json(HTTPStatus.OK, build_health_payload())
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found."})

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if route == "/api/generate":
            try:
                payload = self._read_json_body()
            except Exception as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                return
            status, response = generate_manim_code_for_gateway(payload)
            self._send_json(HTTPStatus(status), response)
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found."})

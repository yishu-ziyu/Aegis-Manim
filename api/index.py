from __future__ import annotations

import json
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

APP_VERSION = "vercel_gateway_v20260505_1"


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


def build_index_html() -> str:
    health = json.dumps(build_health_payload(), ensure_ascii=False)
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
      display: grid;
      place-items: center;
      padding: 32px 18px;
    }}
    main {{
      width: min(860px, 100%);
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
      font-size: clamp(34px, 5vw, 58px);
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
  </style>
</head>
<body>
  <main>
    <p class="eyebrow">Aegis-Manim</p>
    <h1>把抽象知识变成 Manim 动态可视化视频。</h1>
    <p>
      当前 Vercel 部署作为公开入口和健康检查网关运行。完整的视频生成与渲染需要独立后端承载，
      因为 Manim 依赖 ffmpeg、本地媒体目录和更长的任务执行时间。
    </p>
    <section class="status" aria-label="Deployment status">
      <div class="row"><span>Gateway</span><span>Vercel Python Function</span></div>
      <div class="row"><span>Health</span><span><code>/api/health</code></span></div>
      <div class="row"><span>Render Backend</span><span>External service required</span></div>
    </section>
    <script id="health-payload" type="application/json">{health}</script>
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
            self._send_json(
                HTTPStatus.NOT_IMPLEMENTED,
                build_generate_unavailable_payload(),
            )
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found."})

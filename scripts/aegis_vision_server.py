#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORE_DIR = PROJECT_ROOT / "core"
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

import vision_analysis  # noqa: E402


def _configured_api_key() -> str:
    return os.getenv("AEGIS_VISION_BACKEND_API_KEY", os.getenv("VISION_BACKEND_API_KEY", "")).strip()


class AegisVisionServer(BaseHTTPRequestHandler):
    server_version = "AegisVisionServer/1.0"

    def _send_json(self, status: int | HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        expected = _configured_api_key()
        if not expected:
            return True
        return self.headers.get("X-API-Key", "") == expected

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send_json(HTTPStatus.OK, {"ok": True})

    def do_GET(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/health":
            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found."})
            return
        self._send_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "providerConfigured": vision_analysis.is_vision_provider_configured(),
                "cliConfigured": bool(os.getenv("KIMI_VISION_CLI_COMMAND", "").strip()),
                "apiConfigured": bool(
                    os.getenv("KIMI_VISION_API_KEY", "").strip()
                    or os.getenv("MOONSHOT_API_KEY", "").strip()
                ),
                "maxImageBytes": vision_analysis.MAX_IMAGE_BYTES,
            },
        )

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/vision/analyze":
            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found."})
            return
        if not self._authorized():
            self._send_json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "Invalid X-API-Key."})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        if content_length > vision_analysis.MAX_VISION_REQUEST_BYTES:
            self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"ok": False, "error": "图片请求体太大。"})
            return

        try:
            raw_body = self.rfile.read(content_length) if content_length else b"{}"
            payload = json.loads(raw_body.decode("utf-8"))
            if not isinstance(payload, dict):
                payload = {}
        except Exception as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return

        old_backend = os.environ.pop("VISION_BACKEND_URL", None)
        try:
            status, response = vision_analysis.analyze_image_payload(payload)
        finally:
            if old_backend is not None:
                os.environ["VISION_BACKEND_URL"] = old_backend
        self._send_json(status, response)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[aegis-vision] {self.address_string()} {fmt % args}", file=sys.stderr)


def main() -> None:
    host = os.getenv("AEGIS_VISION_HOST", "0.0.0.0")
    port = int(os.getenv("AEGIS_VISION_PORT", "5050"))
    server = ThreadingHTTPServer((host, port), AegisVisionServer)
    print(f"[aegis-vision] listening on http://{host}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

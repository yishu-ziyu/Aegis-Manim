from __future__ import annotations

import json
from http import HTTPStatus
from typing import Any

from api.index import build_health_payload, build_index_html, generate_manim_code_for_gateway


async def read_body(receive: Any) -> bytes:
    chunks: list[bytes] = []
    more_body = True
    while more_body:
        message = await receive()
        chunks.append(message.get("body", b""))
        more_body = bool(message.get("more_body", False))
    return b"".join(chunks)


async def send_response(
    send: Any,
    status: HTTPStatus,
    body: bytes,
    content_type: str,
) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": int(status),
            "headers": [
                (b"content-type", content_type.encode("utf-8")),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


async def send_json(send: Any, status: HTTPStatus, payload: dict[str, object]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    await send_response(send, status, body, "application/json; charset=utf-8")


async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
    if scope.get("type") != "http":
        await send_json(send, HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found."})
        return

    method = scope.get("method", "GET")
    path = scope.get("path", "/")
    if method in {"GET", "HEAD"} and path == "/favicon.ico":
        await send_response(send, HTTPStatus.NO_CONTENT, b"", "image/x-icon")
        return

    if method in {"GET", "HEAD"} and path == "/":
        await send_response(
            send,
            HTTPStatus.OK,
            b"" if method == "HEAD" else build_index_html().encode("utf-8"),
            "text/html; charset=utf-8",
        )
        return

    if method == "GET" and path == "/api/health":
        await send_json(send, HTTPStatus.OK, build_health_payload())
        return

    if method == "POST" and path == "/api/generate":
        try:
            raw_body = await read_body(receive)
            payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
            if not isinstance(payload, dict):
                payload = {}
        except Exception as exc:
            await send_json(send, HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return

        status, response = generate_manim_code_for_gateway(payload)
        await send_json(send, HTTPStatus(status), response)
        return

    await send_json(send, HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found.", "path": path})

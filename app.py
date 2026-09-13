from __future__ import annotations

import json
from http import HTTPStatus
from typing import Any

from api.index import (
    MAX_PUBLIC_BODY_BYTES,
    MAX_VISION_REQUEST_BYTES,
    RENDER_BODY_MAX_BYTES,
    _proxy_to_render_backend,
    _proxy_to_render_backend_raw,
    analyze_image_payload,
    build_health_payload,
    build_index_html,
    disabled_vision_response,
    generate_manim_code_for_gateway,
    generate_alignment_for_gateway,
    is_vision_public_enabled,
    proxy_community_request,
)


async def read_body(receive: Any, *, max_bytes: int = MAX_PUBLIC_BODY_BYTES) -> bytes:
    chunks: list[bytes] = []
    more_body = True
    while more_body:
        message = await receive()
        chunks.append(message.get("body", b""))
        if sum(len(chunk) for chunk in chunks) > max_bytes:
            raise ValueError("请求体太大，请缩短问题后再试。")
        more_body = bool(message.get("more_body", False))
    return b"".join(chunks)


async def send_response(
    send: Any,
    status: HTTPStatus,
    body: bytes,
    content_type: str,
    extra_headers: list[tuple[bytes, bytes]] | None = None,
) -> None:
    headers: list[tuple[bytes, bytes]] = [
        (b"content-type", content_type.encode("utf-8")),
        (b"content-length", str(len(body)).encode("ascii")),
    ]
    if extra_headers:
        headers.extend(extra_headers)
    await send(
        {
            "type": "http.response.start",
            "status": int(status),
            "headers": headers,
        }
    )
    await send({"type": "http.response.body", "body": body})


async def send_json(send: Any, status: HTTPStatus, payload: dict[str, object]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    await send_response(send, status, body, "application/json; charset=utf-8")


async def read_json_body(
    send: Any,
    receive: Any,
    *,
    max_bytes: int = MAX_PUBLIC_BODY_BYTES,
) -> dict[str, object] | None:
    """读请求体并解析为 JSON dict；失败时回 400 并返回 None。"""
    try:
        raw_body = await read_body(receive, max_bytes=max_bytes)
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        if not isinstance(payload, dict):
            payload = {}
    except Exception as exc:
        await send_json(send, HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
        return None
    return payload


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

    if method == "GET" and path == "/api/community/search":
        raw_query = scope.get("query_string", b"")
        query = raw_query.decode("utf-8", "replace") if isinstance(raw_query, bytes) else str(raw_query or "")
        status, response = proxy_community_request(path, query=query)
        await send_json(send, HTTPStatus(status), response)
        return

    if method == "GET" and path == "/api/community/review/queue":
        raw_query = scope.get("query_string", b"")
        query = raw_query.decode("utf-8", "replace") if isinstance(raw_query, bytes) else str(raw_query or "")
        review_token = ""
        for header_name, header_value in scope.get("headers") or []:
            if header_name.decode("latin-1").lower() == "x-review-token":
                review_token = header_value.decode("latin-1").strip()
                break
        if review_token:
            status, response = proxy_community_request(path, query=query, review_token=review_token)
        else:
            status, response = proxy_community_request(path, query=query)
        await send_json(send, HTTPStatus(status), response)
        return

    if method == "GET" and path.startswith("/api/render/status/"):
        job_id = path.split("/api/render/status/", 1)[-1]
        status, response = _proxy_to_render_backend(f"/status/{job_id}")
        await send_json(send, HTTPStatus(status), response)
        return

    if method == "GET" and path.startswith("/api/render/download/"):
        job_id = path.split("/api/render/download/", 1)[-1]
        status_code, body_bytes, resp_headers = _proxy_to_render_backend_raw(f"/download/{job_id}")
        content_type = resp_headers.get("Content-Type") or resp_headers.get("content-type") or "video/mp4"
        extra: list[tuple[bytes, bytes]] = []
        disposition = resp_headers.get("Content-Disposition") or resp_headers.get("content-disposition")
        if disposition:
            extra.append((b"content-disposition", disposition.encode("utf-8")))
        await send_response(send, HTTPStatus(status_code), body_bytes, content_type, extra)
        return

    if method == "POST" and path == "/api/generate":
        payload = await read_json_body(send, receive)
        if payload is None:
            return

        status, response = generate_manim_code_for_gateway(payload)
        await send_json(send, HTTPStatus(status), response)
        return

    if method == "POST" and path == "/api/align":
        # G3: 云端讲稿对齐；X-Aegis-Token 请求头透传（与云端 /api/generate 同标准开放）。
        payload = await read_json_body(send, receive)
        if payload is None:
            return

        status, response = generate_alignment_for_gateway(payload)
        await send_json(send, HTTPStatus(status), response)
        return

    if method == "POST" and path == "/api/vision/analyze":
        if not is_vision_public_enabled():
            status, response = disabled_vision_response()
            await send_json(send, HTTPStatus(status), response)
            return
        payload = await read_json_body(send, receive, max_bytes=MAX_VISION_REQUEST_BYTES)
        if payload is None:
            return

        status, response = analyze_image_payload(payload)
        await send_json(send, HTTPStatus(status), response)
        return

    if method == "POST" and (path == "/api/community/works" or path.startswith("/api/community/works/")):
        payload = await read_json_body(send, receive)
        if payload is None:
            return

        status, response = proxy_community_request(path, method="POST", payload=payload)
        await send_json(send, HTTPStatus(status), response)
        return

    if method == "POST" and path == "/api/render":
        payload = await read_json_body(send, receive, max_bytes=RENDER_BODY_MAX_BYTES)
        if payload is None:
            return

        code = str(payload.get("code", "")).strip()
        scene_name = str(payload.get("sceneName", "GeneratedScene")).strip()
        if not code:
            await send_json(send, HTTPStatus.BAD_REQUEST, {"ok": False, "error": "缺少 code 字段"})
            return

        status, response = _proxy_to_render_backend(
            "/render-async",
            method="POST",
            payload={"code": code, "scene_name": scene_name},
            timeout=15,
        )
        await send_json(send, HTTPStatus(status), response)
        return

    await send_json(send, HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found.", "path": path})

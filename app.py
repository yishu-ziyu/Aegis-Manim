from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from api.index import (
    build_health_payload,
    build_index_html,
    generate_manim_code_for_gateway,
)

app = FastAPI(title="Aegis-Manim Vercel Gateway")


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return build_index_html()


@app.get("/api/health")
def health() -> dict[str, object]:
    return build_health_payload()


@app.post("/api/generate")
def generate(payload: dict[str, object]) -> JSONResponse:
    status, content = generate_manim_code_for_gateway(payload)
    return JSONResponse(status_code=status, content=content)


@app.get("/{path:path}")
def not_found(path: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"ok": False, "error": "Not found.", "path": path},
    )

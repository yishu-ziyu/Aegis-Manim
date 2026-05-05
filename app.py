from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from api.index import (
    build_generate_unavailable_payload,
    build_health_payload,
    build_index_html,
)

app = FastAPI(title="Aegis-Manim Vercel Gateway")


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return build_index_html()


@app.get("/api/health")
def health() -> dict[str, object]:
    return build_health_payload()


@app.post("/api/generate")
def generate_unavailable() -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content=build_generate_unavailable_payload(),
    )


@app.get("/{path:path}")
def not_found(path: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"ok": False, "error": "Not found.", "path": path},
    )

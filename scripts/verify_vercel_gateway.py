from __future__ import annotations

import sys
from importlib.util import find_spec
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from api.index import (  # noqa: E402
    APP_VERSION,
    build_generate_unavailable_payload,
    build_health_payload,
    build_index_html,
)


def main() -> int:
    health = build_health_payload()
    assert health["ok"] is True
    assert health["runtime"] == "vercel-python-function"
    assert health["renderBackend"] == "external-required"
    assert health["version"] == APP_VERSION

    generate = build_generate_unavailable_payload()
    assert generate["ok"] is False
    assert "not available" in str(generate["error"])
    assert "VPS, Render, or Fly.io" in str(generate["detail"])

    html = build_index_html()
    assert "Aegis-Manim" in html
    assert "/api/health" in html
    assert "External service required" in html

    if find_spec("fastapi"):
        from app import app

        assert app.title == "Aegis-Manim Vercel Gateway"

    print("Vercel gateway verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

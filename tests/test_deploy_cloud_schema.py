from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

deploy_cloud = importlib.import_module("scripts.deploy_cloud")


def test_split_sql_statements_preserves_dollar_quoted_function_body() -> None:
    sql = """
CREATE TABLE demo (id int);
CREATE OR REPLACE FUNCTION demo_fn()
RETURNS trigger AS $$
BEGIN
    NEW.id := 1;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE INDEX demo_idx ON demo(id);
"""

    statements = deploy_cloud.split_sql_statements(sql)

    assert len(statements) == 3
    assert statements[1].startswith("CREATE OR REPLACE FUNCTION demo_fn")
    assert "NEW.id := 1;" in statements[1]
    assert statements[2] == "CREATE INDEX demo_idx ON demo(id)"


def test_split_sql_statements_handles_semicolons_in_strings_and_comments() -> None:
    sql = """
-- comment with ; must stay attached
CREATE TABLE quoted (value text DEFAULT 'a;b');
/* block ; comment */
CREATE TABLE named ("semi;colon" text);
"""

    statements = deploy_cloud.split_sql_statements(sql)

    assert len(statements) == 2
    assert "'a;b'" in statements[0]
    assert '"semi;colon"' in statements[1]


def test_schema_file_splits_into_executable_function_statements() -> None:
    sql = (PROJECT_ROOT / "supabase" / "schema.sql").read_text(encoding="utf-8")

    statements = deploy_cloud.split_sql_statements(sql)

    update_function = next(
        statement for statement in statements if "FUNCTION update_updated_at_column" in statement
    )
    cleanup_function = next(
        statement for statement in statements if "FUNCTION cleanup_old_render_jobs" in statement
    )
    assert "NEW.updated_at = now();" in update_function
    assert "GET DIAGNOSTICS deleted_count = ROW_COUNT;" in cleanup_function


def test_schema_defines_community_work_repository_tables() -> None:
    sql = (PROJECT_ROOT / "supabase" / "schema.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS community_works" in sql
    assert "CREATE TABLE IF NOT EXISTS community_work_ratings" in sql
    assert "CREATE TABLE IF NOT EXISTS community_work_events" in sql
    assert "idx_community_works_quality" in sql
    assert "DEFAULT 'candidate'" in sql
    assert "status IN ('candidate', 'published', 'featured', 'quarantine', 'hidden', 'rejected')" in sql
    assert "status IN ('published', 'featured')" in sql
    assert "UNIQUE (work_id, rater_key)" in sql
    assert "ALTER TABLE community_works ENABLE ROW LEVEL SECURITY" in sql


def test_vercel_rewrites_include_community_proxy_routes() -> None:
    config = json.loads((PROJECT_ROOT / "vercel.json").read_text(encoding="utf-8"))
    rewrites = {rewrite["source"]: rewrite["destination"] for rewrite in config["rewrites"]}

    assert rewrites["/api/vision/analyze"] == "/api/index"
    assert rewrites["/api/community/search"] == "/api/index"
    assert rewrites["/api/community/review/queue"] == "/api/index"
    assert rewrites["/api/community/works"] == "/api/index"
    assert rewrites["/api/community/works/(.*)"] == "/api/index"


def test_economics_maturity_benchmark_captures_slutsky_hicks_case() -> None:
    benchmark = (PROJECT_ROOT / "docs" / "specs" / "economics-maturity-benchmark.md").read_text(encoding="utf-8")

    assert "Slutsky and Hicks Decomposition" in benchmark
    assert "A = (6, 6)" in benchmark
    assert "C = (0.6, 9.6)" in benchmark
    assert "S = (1.5, 24)" in benchmark
    assert "H = (0.96, 15.36)" in benchmark
    assert "Slutsky compensation line `y=30-4x`" in benchmark
    assert "Hicks compensation line `y=19.2-4x`" in benchmark


def test_vercel_function_bundle_excludes_local_heavy_directories() -> None:
    config = json.loads((PROJECT_ROOT / "vercel.json").read_text(encoding="utf-8"))
    assert config.get("framework") is None
    assert "api/*.py" in config.get("functions", {})

    exclude_patterns = "\n".join(
        function_config.get("excludeFiles", "")
        for function_config in config.get("functions", {}).values()
    )
    assert len(config["functions"]["api/*.py"]["excludeFiles"]) <= 256

    for path in [
        ".vercel",
        ".venv",
        ".aegis-local-venv",
        "pyproject.toml",
        "uv.lock",
        "manim",
        "media",
        "render_backend",
        "final_video_warehouse",
        "tests",
        "docs",
    ]:
        assert path in exclude_patterns


def test_deploy_supabase_schema_uses_safe_statement_splitter(monkeypatch) -> None:
    observed_queries: list[str] = []

    monkeypatch.setattr(deploy_cloud, "SUPABASE_ACCESS_TOKEN", "token")
    monkeypatch.setattr(deploy_cloud, "SUPABASE_REF", "project-ref")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-key")

    def fake_req(url, method="GET", headers=None, data=None, timeout=30):
        observed_queries.append(data.decode("utf-8"))
        return 200, {}

    monkeypatch.setattr(deploy_cloud, "_req", fake_req)

    assert deploy_cloud.deploy_supabase_schema() is True
    assert any("update_updated_at_column" in query for query in observed_queries)
    assert any("cleanup_old_render_jobs" in query for query in observed_queries)

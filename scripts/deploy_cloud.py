#!/usr/bin/env python3
"""
Aegis-Manim 云端一键部署脚本

自动化完成以下步骤：
1. Supabase 数据库建表 + Storage bucket 创建
2. Render.com 部署渲染后端
3. Vercel 环境变量配置

使用方法：
    export SUPABASE_URL="https://xxx.supabase.co"
    export SUPABASE_SERVICE_KEY="eyJ..."
    export SUPABASE_ACCESS_TOKEN="sbp_..."
    export RENDER_API_KEY="rnd_..."
    export VERCEL_TOKEN="..."
    export VERCEL_PROJECT_ID="prj_..."
    python3 scripts/deploy_cloud.py

所需凭证获取方式见文档底部。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib import error, request

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
SUPABASE_ACCESS_TOKEN = os.environ.get("SUPABASE_ACCESS_TOKEN", "")
RENDER_API_KEY = os.environ.get("RENDER_API_KEY", "")
VERCEL_TOKEN = os.environ.get("VERCEL_TOKEN", "")
VERCEL_PROJECT_ID = os.environ.get("VERCEL_PROJECT_ID", "")

# Derived
SUPABASE_REF = SUPABASE_URL.replace("https://", "").split(".")[0] if SUPABASE_URL else ""
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _req(
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    data: bytes | None = None,
    timeout: int = 30,
) -> tuple[int, dict]:
    """Make HTTP request and return (status, json_body)."""
    req = request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {"raw": body[:300]}
    except Exception as exc:
        return 0, {"error": str(exc)}


def _check_env(*names: str) -> bool:
    missing = [n for n in names if not os.environ.get(n, "").strip()]
    if missing:
        print(f"[ERROR] 缺少环境变量: {', '.join(missing)}")
        return False
    return True


def _step(name: str):
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")


def split_sql_statements(sql: str) -> list[str]:
    """Split SQL on statement semicolons while preserving quoted function bodies."""
    statements: list[str] = []
    current: list[str] = []
    single_quote = False
    double_quote = False
    line_comment = False
    block_comment = False
    dollar_quote: str | None = None
    i = 0

    while i < len(sql):
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""

        if line_comment:
            current.append(ch)
            if ch == "\n":
                line_comment = False
            i += 1
            continue

        if block_comment:
            current.append(ch)
            if ch == "*" and nxt == "/":
                current.append(nxt)
                block_comment = False
                i += 2
            else:
                i += 1
            continue

        if dollar_quote is not None:
            if sql.startswith(dollar_quote, i):
                current.append(dollar_quote)
                i += len(dollar_quote)
                dollar_quote = None
            else:
                current.append(ch)
                i += 1
            continue

        if single_quote:
            current.append(ch)
            if ch == "'" and nxt == "'":
                current.append(nxt)
                i += 2
                continue
            if ch == "'":
                single_quote = False
            i += 1
            continue

        if double_quote:
            current.append(ch)
            if ch == '"' and nxt == '"':
                current.append(nxt)
                i += 2
                continue
            if ch == '"':
                double_quote = False
            i += 1
            continue

        if ch == "-" and nxt == "-":
            current.append(ch)
            current.append(nxt)
            line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            current.append(ch)
            current.append(nxt)
            block_comment = True
            i += 2
            continue
        if ch == "'":
            current.append(ch)
            single_quote = True
            i += 1
            continue
        if ch == '"':
            current.append(ch)
            double_quote = True
            i += 1
            continue
        if ch == "$":
            end = sql.find("$", i + 1)
            if end != -1:
                candidate = sql[i : end + 1]
                tag = candidate[1:-1]
                if tag == "" or tag.replace("_", "a").isalnum():
                    current.append(candidate)
                    dollar_quote = candidate
                    i = end + 1
                    continue
        if ch == ";":
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            i += 1
            continue

        current.append(ch)
        i += 1

    statement = "".join(current).strip()
    if statement:
        statements.append(statement)
    return statements

# ---------------------------------------------------------------------------
# 1. Supabase Database
# ---------------------------------------------------------------------------

def deploy_supabase_schema() -> bool:
    _step("1/4 部署 Supabase 数据库表结构")

    if not _check_env("SUPABASE_URL", "SUPABASE_SERVICE_KEY"):
        return False

    schema_path = PROJECT_ROOT / "supabase" / "schema.sql"
    if not schema_path.exists():
        print(f"[ERROR] 找不到 schema 文件: {schema_path}")
        return False

    sql = schema_path.read_text(encoding="utf-8")

    # Use PostgREST to execute SQL via rpc (if available) or direct SQL
    # Supabase doesn't expose raw SQL via REST directly for security.
    # We'll use the Management API if access token is available,
    # otherwise guide user to run manually.

    if SUPABASE_ACCESS_TOKEN:
        # Try Management API query endpoint
        url = f"https://api.supabase.com/v1/projects/{SUPABASE_REF}/database/query"
        headers = {
            "Authorization": f"Bearer {SUPABASE_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }
        # Split SQL into individual statements and execute one by one.
        # The schema contains PL/pgSQL function bodies with internal semicolons,
        # so a plain sql.split(";") would corrupt those statements.
        statements = split_sql_statements(sql)
        print(f"[INFO] 准备执行 {len(statements)} 条 SQL 语句...")

        for i, stmt in enumerate(statements, 1):
            payload = json.dumps({"query": stmt}).encode("utf-8")
            status, body = _req(url, method="POST", headers=headers, data=payload)
            if status not in (200, 201):
                # Some statements may already exist (IF NOT EXISTS), ignore 409-like errors
                err = body.get("message", body.get("error", "unknown"))
                if "already exists" in str(err).lower() or "duplicate" in str(err).lower():
                    print(f"  [{i}/{len(statements)}] ⚠️ 已存在，跳过")
                else:
                    print(f"  [{i}/{len(statements)}] ❌ 失败: {err}")
            else:
                print(f"  [{i}/{len(statements)}] ✅ 成功")
    else:
        print("[WARN] 未设置 SUPABASE_ACCESS_TOKEN，无法自动执行 SQL。")
        print("[ACTION] 请手动复制以下内容到 Supabase SQL Editor 执行：")
        print("-" * 40)
        print(sql[:500] + "..." if len(sql) > 500 else sql)
        print("-" * 40)
        return False

    print("[DONE] Supabase 数据库表结构部署完成")
    return True


# ---------------------------------------------------------------------------
# 2. Supabase Storage Bucket
# ---------------------------------------------------------------------------

def create_supabase_bucket() -> bool:
    _step("2/4 创建 Supabase Storage Bucket")

    if not _check_env("SUPABASE_URL", "SUPABASE_SERVICE_KEY"):
        return False

    bucket_name = "manim-videos"
    url = f"{SUPABASE_URL}/storage/v1/bucket"
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }

    # Check if bucket exists
    status, buckets = _req(url, headers=headers)
    if status == 200 and isinstance(buckets, list):
        existing = [b.get("name") for b in buckets]
        if bucket_name in existing:
            print(f"[INFO] Bucket '{bucket_name}' 已存在，跳过")
            print("[DONE] Storage Bucket 就绪")
            return True

    # Create bucket
    payload = json.dumps({
        "id": bucket_name,
        "name": bucket_name,
        "public": True,  # Public so videos can be accessed via URL
    }).encode("utf-8")
    status, body = _req(url, method="POST", headers=headers, data=payload)

    if status in (200, 201):
        print(f"[DONE] Bucket '{bucket_name}' 创建成功（Public）")
        return True
    else:
        err = body.get("message", body.get("error", str(body)))
        print(f"[ERROR] 创建 Bucket 失败: {err}")
        return False


# ---------------------------------------------------------------------------
# 3. Render.com Deploy
# ---------------------------------------------------------------------------

def deploy_render_backend() -> bool:
    _step("3/4 部署渲染后端到 Render.com")

    if not _check_env("RENDER_API_KEY"):
        print("[SKIP] 未设置 RENDER_API_KEY，跳过 Render 部署")
        print("[INFO] 你可以稍后手动在 Render Dashboard 创建 Web Service")
        return False

    headers = {
        "Authorization": f"Bearer {RENDER_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    # Check existing services
    status, services = _req(
        "https://api.render.com/v1/services?type=web_service&limit=20",
        headers=headers,
    )

    service_name = "aegis-manim-render"
    existing_service = None
    if status == 200 and isinstance(services, list):
        for svc in services:
            if svc.get("service", {}).get("name") == service_name:
                existing_service = svc["service"]
                break

    if existing_service:
        print(f"[INFO] Render 服务 '{service_name}' 已存在")
        svc_url = existing_service.get("serviceDetails", {}).get("url", "")
    else:
        # Create new service via blueprint or direct API
        # Render API for creating services requires more fields (repo, branch, etc.)
        # Blueprint approach is simpler: create a render.yaml in repo
        print("[INFO] Render 服务不存在，需要通过 Blueprint 创建")
        print("[ACTION] 请确认 GitHub 仓库已连接，然后在 Render Dashboard 选择 'New Blueprint'")
        print("[INFO] 或手动创建 Web Service，配置如下：")
        print("  - Build Command: pip install -r render_backend/requirements.txt")
        print("  - Start Command: gunicorn -w 2 -b 0.0.0.0:$PORT render_backend.app:app")
        print("  - 环境变量:")
        print(f"    SUPABASE_URL={SUPABASE_URL}")
        print("    SUPABASE_SERVICE_KEY=***")
        print("    MANIM_API_KEY=your-secure-key")
        return False

    if svc_url:
        print(f"[DONE] 渲染后端地址: {svc_url}")
        print("[ACTION] 请将以下环境变量加入 Render 服务：")
        print(f"  RENDER_BACKEND_URL={svc_url}")
    return True


# ---------------------------------------------------------------------------
# 4. Vercel Env Variables
# ---------------------------------------------------------------------------

def configure_vercel_env() -> bool:
    _step("4/4 配置 Vercel 环境变量")

    if not _check_env("VERCEL_TOKEN", "VERCEL_PROJECT_ID"):
        print("[SKIP] 未设置 VERCEL_TOKEN / VERCEL_PROJECT_ID，跳过")
        print("[INFO] 你可以稍后手动在 Vercel Dashboard > Settings > Environment Variables 添加")
        return False

    headers = {
        "Authorization": f"Bearer {VERCEL_TOKEN}",
        "Content-Type": "application/json",
    }

    # Determine render backend URL
    render_url = os.environ.get("RENDER_BACKEND_URL", "")
    if not render_url:
        print("[WARN] 未设置 RENDER_BACKEND_URL，Vercel 将无法连接渲染后端")
        print("[INFO] 请在 Render 部署完成后重新运行此脚本，或手动设置")
        return False

    env_vars = {
        "RENDER_BACKEND_URL": render_url,
        "RENDER_BACKEND_API_KEY": os.environ.get("MANIM_API_KEY", "dev-key-change-in-production"),
        "KIMI_CODE_API_KEY": os.environ.get("KIMI_CODE_API_KEY", ""),
        "MINIMAX_API_KEY": os.environ.get("MINIMAX_API_KEY", ""),
    }

    for key, value in env_vars.items():
        if not value:
            continue
        url = f"https://api.vercel.com/v10/projects/{VERCEL_PROJECT_ID}/env"
        payload = json.dumps({
            "key": key,
            "value": value,
            "type": "encrypted",
            "target": ["production", "preview"],
        }).encode("utf-8")
        status, body = _req(url, method="POST", headers=headers, data=payload)
        if status in (200, 201):
            print(f"  ✅ {key}")
        elif status == 400 and "already exists" in str(body).lower():
            print(f"  ⚠️ {key} 已存在，跳过")
        else:
            err = body.get("error", {}).get("message", str(body))
            print(f"  ❌ {key}: {err}")

    print("[DONE] Vercel 环境变量配置完成")
    print("[ACTION] 请重新部署 Vercel 项目以应用新环境变量")
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("=" * 60)
    print("  Aegis-Manim 云端一键部署")
    print("=" * 60)

    results = {
        "supabase_schema": deploy_supabase_schema(),
        "supabase_bucket": create_supabase_bucket(),
        "render_backend": deploy_render_backend(),
        "vercel_env": configure_vercel_env(),
    }

    print("\n" + "=" * 60)
    print("  部署摘要")
    print("=" * 60)
    for name, ok in results.items():
        icon = "✅" if ok else "❌"
        print(f"  {icon} {name}")

    if not all(results.values()):
        print("\n[NOTE] 部分步骤失败或跳过。请根据上方提示手动完成剩余步骤。")
        print("\n凭证获取指南：")
        print("  - SUPABASE_ACCESS_TOKEN: https://app.supabase.com/account/tokens")
        print("  - RENDER_API_KEY: https://dashboard.render.com/u/settings#api-keys")
        print("  - VERCEL_TOKEN: https://vercel.com/account/tokens")
        return 1

    print("\n[DONE] 全部部署完成！")
    return 0


if __name__ == "__main__":
    sys.exit(main())

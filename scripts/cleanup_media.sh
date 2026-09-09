#!/usr/bin/env bash
# Aegis 媒体清理：删除 N 天前的生成产物（默认 14 天，默认 dry-run，加 -y 才真删）
# 用法: ./scripts/cleanup_media.sh [天数] [-y]
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DAYS=14
APPLY=0
for arg in "$@"; do
  case "$arg" in
    -y) APPLY=1 ;;
    [0-9]*) DAYS="$arg" ;;
    *) echo "未知参数: $arg (用法: $0 [天数] [-y])" >&2; exit 1 ;;
  esac
done

echo "清理 ${DAYS} 天前的 media/videos 与 generated 产物（dry-run=$( [ "$APPLY" = 1 ] && echo off || echo on )）"

find "$ROOT_DIR/media/videos" -mindepth 1 -maxdepth 1 -type d -mtime "+$DAYS" -print0 | {
  total=0
  while IFS= read -r -d '' d; do
    echo "  删除: ${d#"$ROOT_DIR"/}"
    total=$((total + 1))
    [ "$APPLY" = 1 ] && rm -rf "$d"
  done
  echo "共 $total 个视频目录"
}

find "$ROOT_DIR/generated" -maxdepth 1 -name "scene_*.py" -mtime "+$DAYS" -print0 | {
  total=0
  while IFS= read -r -d '' f; do
    echo "  删除: ${f#"$ROOT_DIR"/}"
    total=$((total + 1))
    [ "$APPLY" = 1 ] && rm -f "$f"
  done
  echo "共 $total 个场景文件"
}

[ "$APPLY" = 1 ] || echo "（dry-run：未实际删除。确认无误后加 -y 执行）"

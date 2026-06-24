#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "未找到 python3，请先安装 Python 3。" >&2
  exit 1
fi

echo "使用: $($PYTHON --version)"
echo "创建虚拟环境: $ROOT/.venv"
"$PYTHON" -m venv .venv

echo "安装依赖..."
.venv/bin/python -m pip install -U pip
.venv/bin/pip install -r requirements.txt

echo "完成。虚拟环境 Python: $(.venv/bin/python --version)"

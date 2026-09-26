#!/bin/bash
# 提交前 / CI 的统一门禁：一条命令跑完所有检查
#
#   ./scripts/check.sh
set -euo pipefail
cd "$(dirname "$0")/.."

echo "── ruff（lint）──"
uv run --quiet ruff check .

echo "── ruff（format 检查，不自动改）──"
uv run --quiet ruff format --check .

echo "── mypy --strict ──"
uv run --quiet mypy

echo "── 分层契约（import-linter）──"
uv run --quiet lint-imports

echo "── pytest ──"
uv run --quiet pytest

echo
echo "全部通过"

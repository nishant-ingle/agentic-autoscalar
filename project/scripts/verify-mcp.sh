#!/usr/bin/env bash
set -euo pipefail

TARGET_HOST="${1:-http://localhost:8001}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

PYTHON_BIN="${PROJECT_ROOT}/venv/bin/python"
if [ ! -f "${PYTHON_BIN}" ]; then
  PYTHON_BIN="python3"
fi

"${PYTHON_BIN}" "${SCRIPT_DIR}/verify-mcp.py" "${TARGET_HOST}"

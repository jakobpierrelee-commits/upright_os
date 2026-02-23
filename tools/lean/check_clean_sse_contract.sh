#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

TARGET="app/bridge/server.py"

echo "[check_clean_sse_contract] validating clean preflight SSE events..."
rg -n 'if u.path == "/agent/clean/preflight/stream"' "${TARGET}" >/dev/null
rg -n '"start"' "${TARGET}" >/dev/null
rg -n '"check_start"' "${TARGET}" >/dev/null
rg -n '"check_done"' "${TARGET}" >/dev/null
rg -n '"done"' "${TARGET}" >/dev/null

echo "[check_clean_sse_contract] PASS"

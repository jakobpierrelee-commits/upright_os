#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

SERVER_TARGET="app/bridge/server.py"
PREFLIGHT_TARGET="app/bridge/clean_preflight.py"

find_match() {
  local pattern="$1"
  local target="$2"
  if command -v rg >/dev/null 2>&1; then
    rg -n "${pattern}" "${target}" >/dev/null
  else
    grep -nE "${pattern}" "${target}" >/dev/null
  fi
}

echo "[check_clean_sse_contract] validating clean preflight SSE events..."
find_match 'if u.path == "/agent/clean/preflight/stream"' "${SERVER_TARGET}"
find_match 'send_evt\("start"' "${SERVER_TARGET}"
find_match '"check_start"' "${PREFLIGHT_TARGET}"
find_match 'emit\("check_done"' "${PREFLIGHT_TARGET}"
find_match 'emit\("done"' "${PREFLIGHT_TARGET}"

echo "[check_clean_sse_contract] PASS"

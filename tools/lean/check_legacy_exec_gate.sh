#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

SERVER_TARGET="app/bridge/server.py"
LEGACY_GATE_TARGET="app/bridge/clean_legacy_gate.py"

find_match() {
  local pattern="$1"
  local target="$2"
  if command -v rg >/dev/null 2>&1; then
    rg -n "${pattern}" "${target}" >/dev/null
  else
    grep -nE "${pattern}" "${target}" >/dev/null
  fi
}

count_match() {
  local pattern="$1"
  local target="$2"
  if command -v rg >/dev/null 2>&1; then
    rg -c "${pattern}" "${target}"
  else
    grep -cE "${pattern}" "${target}"
  fi
}

echo "[check_legacy_exec_gate] validating legacy execution hard gate..."
find_match 'LEGACY_EXEC_ENV_FLAG = "UPRIGHT_ALLOW_LEGACY_EXEC"' "${LEGACY_GATE_TARGET}"
find_match 'def _legacy_execution_guard\(path: str\)' "${SERVER_TARGET}"
find_match 'if u.path == "/agent/threads":' "${SERVER_TARGET}"
find_match 'if u.path == "/agent/thread/new":' "${SERVER_TARGET}"
find_match 'if u.path == "/agent/thread/select":' "${SERVER_TARGET}"
find_match 'if u.path == "/agent/chat":' "${SERVER_TARGET}"
find_match 'if u.path == "/agent/chat/stream":' "${SERVER_TARGET}"
GUARD_COUNT="$(count_match 'guard = _legacy_execution_guard\(u.path\)' "${SERVER_TARGET}")"
if [[ "${GUARD_COUNT}" -lt 5 ]]; then
  echo "[check_legacy_exec_gate] expected >=5 legacy route guards, got ${GUARD_COUNT}"
  exit 1
fi
find_match '"error": "legacy_execution_disabled"' "${LEGACY_GATE_TARGET}"

echo "[check_legacy_exec_gate] PASS"

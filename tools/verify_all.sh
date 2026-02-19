#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

run() {
  echo
  echo "[verify] $*"
  "$@"
}

echo "[verify] root=${ROOT_DIR}"
echo "[verify] python=${PYTHON_BIN}"

cd "${ROOT_DIR}"

# Bridge and contract tests
run "${PYTHON_BIN}" -m pytest -q app/bridge/tests

# Agent tools sprint suites
run "${PYTHON_BIN}" -m pytest -q \
  app/bridge/tests/test_codex_t1_tools.py \
  app/bridge/tests/test_codex_t2_tools.py \
  app/bridge/tests/test_codex_t3_tools.py \
  app/bridge/tests/test_contract_v2_readiness.py

# Frontend checks
cd "${ROOT_DIR}/app/ui/ops-console"
run npx tsc --noEmit
run npm run -s test -- src/features/codex/ToolCallCard.test.tsx src/features/codex/UploadConfirmModal.test.tsx

echo
echo "[verify] all checks passed"


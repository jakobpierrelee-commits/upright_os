#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

RUN_LIVE_CLEAN_GATES="${RUN_LIVE_CLEAN_GATES:-0}"
BASE="${BASE:-http://127.0.0.1:8797}"
MODE="${MODE:-app_dev}"

echo "[ci_clean_lane] static checks..."
python3 -m py_compile app/bridge/server.py app/bridge/clean_preflight.py app/bridge/clean_codex_chat.py app/bridge/clean_route_helpers.py app/bridge/clean_auth_helpers.py app/bridge/clean_threads.py app/bridge/clean_status.py app/bridge/clean_request_parsers.py app/bridge/clean_sse.py app/bridge/clean_legacy_gate.py
bash -n tools/lean/check_clean_lane.sh
bash -n tools/lean/check_clean_parity.sh
bash -n tools/lean/check_clean_exec_intent.sh
bash -n tools/lean/check_manifest_fail_closed.sh
bash -n tools/lean/check_clean_sse_contract.sh
bash -n tools/lean/check_legacy_exec_gate.sh
bash -n tools/lean/check_prearm_signoff.sh
bash -n tools/lean/check_hardware_registry_contract.sh
bash -n tools/lean/check_module_size_guardrails.sh
bash -n tools/lean/check_release_version_contract.sh
bash -n tools/lean/check_sketch_nomenclature_contract.sh
bash -n tools/lean/preflight_clean.sh
bash -n tools/lean/update_scorecard.sh
bash -n tools/lean/new_sketch_version.sh

chmod +x tools/lean/check_clean_sse_contract.sh
./tools/lean/check_clean_sse_contract.sh
chmod +x tools/lean/check_legacy_exec_gate.sh
./tools/lean/check_legacy_exec_gate.sh
chmod +x tools/lean/check_module_size_guardrails.sh
./tools/lean/check_module_size_guardrails.sh
chmod +x tools/lean/check_release_version_contract.sh
./tools/lean/check_release_version_contract.sh
chmod +x tools/lean/check_sketch_nomenclature_contract.sh
./tools/lean/check_sketch_nomenclature_contract.sh

(
  cd app/bridge
  pytest -q tests/test_clean_auth_helpers.py tests/test_clean_threads.py tests/test_clean_status.py tests/test_clean_request_parsers.py tests/test_clean_sse.py tests/test_clean_codex_chat.py tests/test_clean_preflight.py tests/test_clean_route_helpers.py tests/test_clean_contracts.py tests/test_clean_firmware_ops.py tests/test_clean_legacy_gate.py tests/test_tuning_policy.py tests/test_server_tuning_guardrails.py tests/test_tuning_acceptance_pack.py
)

(
  cd app/ui/ops-console
  npm ci
  npm run -s build
)

if [[ "${RUN_LIVE_CLEAN_GATES}" != "1" ]]; then
  echo "[ci_clean_lane] live gates skipped (set RUN_LIVE_CLEAN_GATES=1 to enable)"
  exit 0
fi

echo "[ci_clean_lane] live gates enabled"
if ! command -v codex >/dev/null 2>&1; then
  echo "[ci_clean_lane] codex CLI missing"
  exit 1
fi

LOGIN_STATUS="$(codex login status 2>&1 || true)"
if ! echo "${LOGIN_STATUS}" | rg -q "Logged in using"; then
  echo "[ci_clean_lane] codex login required"
  echo "${LOGIN_STATUS}"
  exit 1
fi

APP_BRIDGE_MODE=detached APP_ALLOW_DETACHED_BRIDGE=1 ./tools/restart_bridge.sh
BASE="${BASE}" MODE="${MODE}" ./tools/lean/check_clean_lane.sh
BASE="${BASE}" MODE="${MODE}" ./tools/lean/check_clean_parity.sh
BASE="${BASE}" MODE="${MODE}" ./tools/lean/check_clean_exec_intent.sh
BASE="${BASE}" MODE="${MODE}" ./tools/lean/check_manifest_fail_closed.sh
BASE="${BASE}" ./tools/lean/check_hardware_registry_contract.sh
BASE="${BASE}" MODE="${MODE}" ./tools/lean/preflight_clean.sh

echo "[ci_clean_lane] PASS"

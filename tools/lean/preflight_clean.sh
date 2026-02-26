#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

BASE="${BASE:-http://127.0.0.1:8797}"
MODE="${MODE:-app_dev}"
WITH_COMPILE="${WITH_COMPILE:-0}"
COMPILE_FQBN="${COMPILE_FQBN:-arduino:avr:nano:cpu=atmega328old}"
COMPILE_SKETCH="${COMPILE_SKETCH:-app/bridge/firmware_templates/profiled_runtime_v1}"

echo "[preflight_clean] start BASE=${BASE} MODE=${MODE} WITH_COMPILE=${WITH_COMPILE}"

BASE="${BASE}" MODE="${MODE}" ./tools/lean/check_clean_lane.sh
BASE="${BASE}" MODE="${MODE}" ./tools/lean/check_clean_parity.sh
BASE="${BASE}" MODE="${MODE}" ./tools/lean/check_clean_exec_intent.sh

if [ "${WITH_COMPILE}" = "1" ]; then
  echo "[preflight_clean] compile sanity: ${COMPILE_SKETCH} (${COMPILE_FQBN})"
  arduino-cli compile --fqbn "${COMPILE_FQBN}" "${COMPILE_SKETCH}"
fi

echo "[preflight_clean] PASS"

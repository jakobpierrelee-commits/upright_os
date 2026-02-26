#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNLOG_DIR="${ROOT_DIR}/.runlogs"
mkdir -p "${RUNLOG_DIR}"

BRIDGE_INSTANCE="${APP_BRIDGE_INSTANCE:-upright-lean-v1}"
BRIDGE_HOST="${APP_BRIDGE_HOST:-127.0.0.1}"
BRIDGE_PORT="${APP_BRIDGE_PORT:-8797}"
HEALTH_URL="http://${BRIDGE_HOST}:${BRIDGE_PORT}/health"

SKETCH="${1:-app/bridge/firmware_templates/balance_mvp_v1}"
FQBN="${FQBN:-arduino:avr:nano}"
PORT="${PORT:-/dev/cu.usbserial-2210}"
ARDUINO_CLI="${ARDUINO_CLI:-arduino-cli}"

usage() {
  cat <<EOF
Usage:
  ./tools/flash_nano_guarded.sh [sketch_folder]

Environment overrides:
  PORT=/dev/cu.usbserial-XXXX
  FQBN=arduino:avr:nano
  ARDUINO_CLI=arduino-cli
EOF
}

if [ "${SKETCH}" = "-h" ] || [ "${SKETCH}" = "--help" ]; then
  usage
  exit 0
fi

cd "${ROOT_DIR}"

bridge_was_running=0
if curl -fsS --max-time 1 "${HEALTH_URL}" >/dev/null 2>&1; then
  bridge_was_running=1
fi

restore_bridge() {
  if [ "${bridge_was_running}" = "1" ]; then
    echo "[flash_guard] restoring bridge..."
    "${ROOT_DIR}/tools/start_bridge_isolated.sh" >/dev/null
    echo "[flash_guard] bridge restored"
  fi
}
trap restore_bridge EXIT

if [ "${bridge_was_running}" = "1" ]; then
  echo "[flash_guard] bridge is running; stopping to free serial port"
  "${ROOT_DIR}/tools/stop_bridge.sh" >/dev/null
fi

echo "[flash_guard] compiling ${SKETCH} (${FQBN})"
"${ARDUINO_CLI}" compile --clean --fqbn "${FQBN}" "${SKETCH}"
echo "[flash_guard] uploading to ${PORT}"
"${ARDUINO_CLI}" upload -p "${PORT}" --fqbn "${FQBN}" "${SKETCH}"
echo "[flash_guard] upload complete"

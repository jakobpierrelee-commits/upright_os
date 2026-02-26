#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNLOG_DIR="${ROOT_DIR}/.runlogs"
mkdir -p "${RUNLOG_DIR}"

if [ "${APP_ALLOW_DETACHED_BRIDGE:-0}" != "1" ]; then
  echo "[start_bridge] detached mode is disabled by default (stability policy)."
  echo "[start_bridge] run foreground bridge instead:"
  echo "  ./tools/start_bridge_fg.sh"
  echo "[start_bridge] set APP_ALLOW_DETACHED_BRIDGE=1 only when you explicitly need detached mode."
  exit 2
fi

BRIDGE_INSTANCE="${APP_BRIDGE_INSTANCE:-upright-lean-v1}"
BRIDGE_HOST="${APP_BRIDGE_HOST:-127.0.0.1}"
BRIDGE_PORT="${APP_BRIDGE_PORT:-8797}"
HEALTH_URL="http://${BRIDGE_HOST}:${BRIDGE_PORT}/health"
ENTRYPOINT="${ROOT_DIR}/tools/lean_bridge_entry.py"
PID_FILE="${RUNLOG_DIR}/bridge-${BRIDGE_INSTANCE}.pid"
LOG_FILE="${RUNLOG_DIR}/bridge-${BRIDGE_INSTANCE}.log"

health_ok() {
  curl -fsS --max-time 1 "${HEALTH_URL}" >/dev/null 2>&1
}

bridge_running() {
  if [ ! -f "${PID_FILE}" ]; then
    return 1
  fi
  local pid
  pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
  [ -n "${pid}" ] || return 1
  kill -0 "${pid}" 2>/dev/null || return 1
  ps -p "${pid}" -o args= 2>/dev/null | grep -q "${ENTRYPOINT} --supervised --instance ${BRIDGE_INSTANCE}"
}

if bridge_running; then
  echo "[start_bridge] bridge already running (pid=$(cat "${PID_FILE}"), instance=${BRIDGE_INSTANCE})"
else
  echo "[start_bridge] starting lean bridge process..."
  (
    cd "${ROOT_DIR}"
    nohup python3 -u "${ENTRYPOINT}" --supervised --instance "${BRIDGE_INSTANCE}" >"${LOG_FILE}" 2>&1 &
    echo $! >"${PID_FILE}"
  )
  echo "[start_bridge] started (pid=$(cat "${PID_FILE}"), instance=${BRIDGE_INSTANCE})"
fi

echo "[start_bridge] waiting for bridge health..."
tries=0
max_tries=50
until health_ok; do
  tries=$((tries + 1))
  if [ "${tries}" -ge "${max_tries}" ]; then
    echo "[start_bridge] bridge failed to become healthy at ${HEALTH_URL}"
    echo "[start_bridge] check logs: tail -f ${LOG_FILE}"
    exit 1
  fi
  sleep 0.25
done

stable_checks="${BRIDGE_START_STABLE_CHECKS:-20}"
stable_interval_s="${BRIDGE_START_STABLE_INTERVAL_S:-0.5}"
for _ in $(seq 1 "${stable_checks}"); do
  if ! health_ok; then
    echo "[start_bridge] health became unstable after startup at ${HEALTH_URL}"
    echo "[start_bridge] check logs: tail -f ${LOG_FILE}"
    exit 1
  fi
  sleep "${stable_interval_s}"
done

echo "[start_bridge] bridge healthy at ${HEALTH_URL}"

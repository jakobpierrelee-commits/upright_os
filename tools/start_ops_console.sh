#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNLOG_DIR="${ROOT_DIR}/.runlogs"
mkdir -p "${RUNLOG_DIR}"

BRIDGE_HOST="${APP_BRIDGE_HOST:-127.0.0.1}"
BRIDGE_PORT="${APP_BRIDGE_PORT:-8787}"
HEALTH_URL="http://${BRIDGE_HOST}:${BRIDGE_PORT}/health"
PID_FILE="${RUNLOG_DIR}/bridge.pid"
LOG_FILE="${RUNLOG_DIR}/bridge.log"
SUPERVISOR_PID_FILE="${RUNLOG_DIR}/bridge-supervisor.pid"
SUPERVISOR_LOG_FILE="${RUNLOG_DIR}/bridge-supervisor.log"
SUPERVISOR_SCRIPT="${ROOT_DIR}/tools/bridge_supervisor.sh"

health_ok() {
  curl -fsS --max-time 1 "${HEALTH_URL}" >/dev/null 2>&1
}

start_bridge_supervisor_if_needed() {
  if [ -f "${SUPERVISOR_PID_FILE}" ]; then
    SUP_PID="$(cat "${SUPERVISOR_PID_FILE}" 2>/dev/null || true)"
    if [ -n "${SUP_PID:-}" ] && kill -0 "${SUP_PID}" 2>/dev/null && ps -p "${SUP_PID}" -o args= 2>/dev/null | grep -q "tools/bridge_supervisor.sh"; then
      echo "[launcher] bridge supervisor already running (pid=${SUP_PID})"
      return 0
    fi
  fi

  echo "[launcher] starting bridge supervisor..."
  (
    cd "${ROOT_DIR}"
    nohup "${SUPERVISOR_SCRIPT}" >"${SUPERVISOR_LOG_FILE}" 2>&1 &
    echo $! >"${SUPERVISOR_PID_FILE}"
  )
}

wait_for_bridge() {
  if health_ok; then
    echo "[launcher] bridge already healthy at ${HEALTH_URL}"
    return 0
  fi

  local tries=0
  local max_tries=80
  until health_ok; do
    tries=$((tries + 1))
    if [ "${tries}" -ge "${max_tries}" ]; then
      echo "[launcher] bridge failed to become healthy at ${HEALTH_URL}"
      if [ -f "${LOG_FILE}" ]; then
        echo "[launcher] tail ${LOG_FILE}:"
        tail -n 80 "${LOG_FILE}" || true
      fi
      return 1
    fi
    sleep 0.25
  done
  echo "[launcher] bridge healthy at ${HEALTH_URL}"
}

start_ui() {
  local ui_mode="${APP_UI_MODE:-dev}"
  echo "[launcher] starting ops console UI (${ui_mode})..."
  cd "${ROOT_DIR}/app/ui/ops-console"
  if [ "${ui_mode}" = "preview" ]; then
    npm run build
    npm run preview -- --host 127.0.0.1 --port "${APP_UI_PORT:-4173}" --strictPort
  else
    npm run dev -- --host 127.0.0.1 --port "${APP_UI_PORT:-5173}" --strictPort
  fi
}

start_bridge_supervisor_if_needed
wait_for_bridge
start_ui

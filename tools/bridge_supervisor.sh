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

CHECK_INTERVAL_S="${BRIDGE_SUPERVISOR_CHECK_INTERVAL_S:-2}"
RESTART_BACKOFF_S="${BRIDGE_SUPERVISOR_RESTART_BACKOFF_S:-1}"
STARTUP_GRACE_S="${BRIDGE_SUPERVISOR_STARTUP_GRACE_S:-8}"

health_ok() {
  curl -fsS --max-time 1 "${HEALTH_URL}" >/dev/null 2>&1
}

bridge_pid() {
  if [ -f "${PID_FILE}" ]; then
    cat "${PID_FILE}" 2>/dev/null || true
  fi
}

pid_is_bridge() {
  local pid="$1"
  [ -n "${pid}" ] || return 1
  kill -0 "${pid}" 2>/dev/null || return 1
  ps -p "${pid}" -o args= 2>/dev/null | grep -q "app/bridge/server.py"
}

bridge_alive() {
  local pid
  pid="$(bridge_pid)"
  pid_is_bridge "${pid}"
}

start_bridge() {
  if bridge_alive; then
    return 0
  fi
  (
    cd "${ROOT_DIR}"
    nohup python3 -u app/bridge/server.py >"${LOG_FILE}" 2>&1 &
    echo $! >"${PID_FILE}"
  )
}

stop_stale_bridge() {
  local pid
  pid="$(bridge_pid)"
  if pid_is_bridge "${pid}"; then
    kill "${pid}" 2>/dev/null || true
    sleep 0.2
  fi
}

echo "[bridge-supervisor] watching ${HEALTH_URL}"
last_start_ts=0
while true; do
  if health_ok; then
    sleep "${CHECK_INTERVAL_S}"
    continue
  fi

  # If bridge was just started, give it time to bind ports before deciding it
  # is unhealthy and recycling it.
  if bridge_alive; then
    now_ts="$(date +%s)"
    if [ "${last_start_ts}" -gt 0 ] && [ $((now_ts - last_start_ts)) -lt "${STARTUP_GRACE_S}" ]; then
      sleep "${CHECK_INTERVAL_S}"
      continue
    fi
  fi

  # If health is down, restart the bridge process.
  echo "[bridge-supervisor] health check failed; restarting bridge..."
  stop_stale_bridge
  start_bridge
  last_start_ts="$(date +%s)"
  sleep "${RESTART_BACKOFF_S}"
done

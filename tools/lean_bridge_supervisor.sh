#!/usr/bin/env bash
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNLOG_DIR="${ROOT_DIR}/.runlogs"
mkdir -p "${RUNLOG_DIR}"

BRIDGE_INSTANCE="${APP_BRIDGE_INSTANCE:-upright-lean-v1}"
while [ $# -gt 0 ]; do
  case "$1" in
    --instance)
      BRIDGE_INSTANCE="${2:-${BRIDGE_INSTANCE}}"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done

BRIDGE_HOST="${APP_BRIDGE_HOST:-127.0.0.1}"
BRIDGE_PORT="${APP_BRIDGE_PORT:-8797}"
HEALTH_URL="http://${BRIDGE_HOST}:${BRIDGE_PORT}/health"
PID_FILE="${RUNLOG_DIR}/bridge-${BRIDGE_INSTANCE}.pid"
LOG_FILE="${RUNLOG_DIR}/bridge-${BRIDGE_INSTANCE}.log"
ENTRYPOINT="${ROOT_DIR}/tools/lean_bridge_entry.py"

CHECK_INTERVAL_S="${BRIDGE_SUPERVISOR_CHECK_INTERVAL_S:-2}"
RESTART_BACKOFF_S="${BRIDGE_SUPERVISOR_RESTART_BACKOFF_S:-1}"
STARTUP_GRACE_S="${BRIDGE_SUPERVISOR_STARTUP_GRACE_S:-8}"
HEALTH_MAX_TIME_S="${BRIDGE_SUPERVISOR_HEALTH_MAX_TIME_S:-2}"
FAIL_THRESHOLD="${BRIDGE_SUPERVISOR_FAIL_THRESHOLD:-3}"

health_ok() {
  curl -fsS --max-time "${HEALTH_MAX_TIME_S}" "${HEALTH_URL}" >/dev/null 2>&1
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
  ps -p "${pid}" -o args= 2>/dev/null | grep -q "${ENTRYPOINT} --supervised --instance ${BRIDGE_INSTANCE}"
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
    nohup python3 -u "${ENTRYPOINT}" --supervised --instance "${BRIDGE_INSTANCE}" >"${LOG_FILE}" 2>&1 &
    echo $! >"${PID_FILE}"
  )
  local new_pid
  new_pid="$(bridge_pid)"
  echo "[bridge-supervisor] started bridge pid=${new_pid:-unknown}"
  return 0
}

stop_stale_bridge() {
  local pid
  pid="$(bridge_pid)"
  if pid_is_bridge "${pid}"; then
    kill "${pid}" 2>/dev/null || true
    sleep 0.2
  fi
}

echo "[bridge-supervisor] watching ${HEALTH_URL} (instance=${BRIDGE_INSTANCE})"
last_start_ts=0
consecutive_failures=0
while true; do
  if health_ok; then
    consecutive_failures=0
    sleep "${CHECK_INTERVAL_S}"
    continue
  fi

  consecutive_failures=$((consecutive_failures + 1))
  echo "[bridge-supervisor] health check failed (${consecutive_failures}/${FAIL_THRESHOLD})"

  # If process is gone, restart immediately.
  if ! bridge_alive; then
    echo "[bridge-supervisor] bridge process not alive; starting immediately"
    stop_stale_bridge
    if ! start_bridge; then
      echo "[bridge-supervisor] bridge start attempt failed (will retry)"
    fi
    last_start_ts="$(date +%s)"
    consecutive_failures=0
    sleep "${RESTART_BACKOFF_S}"
    continue
  fi

  # Avoid restarts from transient misses while bridge is still warming up.
  # If bridge was just started, give it time to bind ports before deciding it
  # is unhealthy and recycling it.
  now_ts="$(date +%s)"
  if [ "${last_start_ts}" -gt 0 ] && [ $((now_ts - last_start_ts)) -lt "${STARTUP_GRACE_S}" ]; then
    sleep "${CHECK_INTERVAL_S}"
    continue
  fi

  # Require multiple consecutive failures before recycling a live process.
  if [ "${consecutive_failures}" -lt "${FAIL_THRESHOLD}" ]; then
    sleep "${CHECK_INTERVAL_S}"
    continue
  fi

  # If health is down, restart the bridge process.
  echo "[bridge-supervisor] health remained unhealthy; restarting bridge..."
  stop_stale_bridge
  if ! start_bridge; then
    echo "[bridge-supervisor] bridge start attempt failed (will retry)"
  fi
  last_start_ts="$(date +%s)"
  consecutive_failures=0
  sleep "${RESTART_BACKOFF_S}"
done

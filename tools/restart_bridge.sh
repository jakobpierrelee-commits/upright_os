#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNLOG_DIR="${ROOT_DIR}/.runlogs"
mkdir -p "${RUNLOG_DIR}"

BRIDGE_INSTANCE="${APP_BRIDGE_INSTANCE:-upright-lean-v1}"
ENTRYPOINT="${ROOT_DIR}/tools/lean_bridge_entry.py"
PID_FILE="${RUNLOG_DIR}/bridge-${BRIDGE_INSTANCE}.pid"
LOG_FILE="${RUNLOG_DIR}/bridge-${BRIDGE_INSTANCE}.log"
SUP_PID_FILE="${RUNLOG_DIR}/bridge-supervisor-${BRIDGE_INSTANCE}.pid"
SUP_LOG_FILE="${RUNLOG_DIR}/bridge-supervisor-${BRIDGE_INSTANCE}.log"

BRIDGE_HOST="${APP_BRIDGE_HOST:-127.0.0.1}"
BRIDGE_PORT="${APP_BRIDGE_PORT:-8797}"
HEALTH_URL="http://${BRIDGE_HOST}:${BRIDGE_PORT}/health"
BRIDGE_MODE="${APP_BRIDGE_MODE:-isolated}"

health_ok() {
  curl -fsS --max-time 1 "${HEALTH_URL}" >/dev/null 2>&1
}

kill_by_pidfile() {
  if [ ! -f "${PID_FILE}" ]; then
    return 0
  fi
  local pid
  pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
  if [ -n "${pid}" ] && kill -0 "${pid}" 2>/dev/null; then
    echo "[restart_bridge] stopping pid=${pid}"
    kill "${pid}" 2>/dev/null || true
    sleep 0.4
    if kill -0 "${pid}" 2>/dev/null; then
      kill -9 "${pid}" 2>/dev/null || true
    fi
  fi
  rm -f "${PID_FILE}"
}

kill_supervisor_by_pidfile() {
  if [ ! -f "${SUP_PID_FILE}" ]; then
    return 0
  fi
  local pid
  pid="$(cat "${SUP_PID_FILE}" 2>/dev/null || true)"
  if [ -n "${pid}" ] && kill -0 "${pid}" 2>/dev/null; then
    echo "[restart_bridge] stopping supervisor pid=${pid}"
    kill "${pid}" 2>/dev/null || true
    sleep 0.4
    if kill -0 "${pid}" 2>/dev/null; then
      kill -9 "${pid}" 2>/dev/null || true
    fi
  fi
  rm -f "${SUP_PID_FILE}"
}

kill_by_pattern() {
  local pids
  pids="$(pgrep -f -- "${ENTRYPOINT} --instance ${BRIDGE_INSTANCE}" || true)"
  if [ -n "${pids}" ]; then
    echo "[restart_bridge] stopping stale pattern pids: ${pids//$'\n'/ }"
    # shellcheck disable=SC2086
    kill ${pids} 2>/dev/null || true
    sleep 0.3
    # shellcheck disable=SC2086
    kill -9 ${pids} 2>/dev/null || true
  fi
  local sup_pids
  sup_pids="$(pgrep -f -- "lean_bridge_supervisor.sh --instance ${BRIDGE_INSTANCE}" || true)"
  if [ -n "${sup_pids}" ]; then
    echo "[restart_bridge] stopping stale supervisor pids: ${sup_pids//$'\n'/ }"
    # shellcheck disable=SC2086
    kill ${sup_pids} 2>/dev/null || true
    sleep 0.3
    # shellcheck disable=SC2086
    kill -9 ${sup_pids} 2>/dev/null || true
  fi
}

kill_by_pidfile
kill_supervisor_by_pidfile
kill_by_pattern

PORT_PID="$(lsof -tiTCP:${BRIDGE_PORT} -sTCP:LISTEN || true)"
if [ -n "${PORT_PID}" ]; then
  echo "[restart_bridge] evicting stale listener on :${BRIDGE_PORT} pid=${PORT_PID}"
  kill "${PORT_PID}" 2>/dev/null || true
  sleep 0.2
  if kill -0 "${PORT_PID}" 2>/dev/null; then
    kill -9 "${PORT_PID}" 2>/dev/null || true
  fi
fi

if [ "${BRIDGE_MODE}" = "foreground" ]; then
  echo "[restart_bridge] launching bridge in foreground mode (default override)"
  exec "${ROOT_DIR}/tools/start_bridge_fg.sh"
fi

if [ "${BRIDGE_MODE}" = "isolated" ]; then
  echo "[restart_bridge] launching bridge in isolated supervisor mode (IDE-safe default)"
  "${ROOT_DIR}/tools/start_bridge_isolated.sh"
elif [ "${BRIDGE_MODE}" = "detached" ]; then
  if [ "${APP_ALLOW_DETACHED_BRIDGE:-0}" != "1" ]; then
    echo "[restart_bridge] detached mode requested but APP_ALLOW_DETACHED_BRIDGE is not enabled."
    echo "[restart_bridge] use isolated mode (default) or foreground mode."
    exit 2
  fi
  "${ROOT_DIR}/tools/start_bridge.sh"
else
  echo "[restart_bridge] unknown APP_BRIDGE_MODE=${BRIDGE_MODE}; expected isolated|foreground|detached"
  exit 2
fi

for i in 1 2 3 4 5; do
  if ! health_ok; then
    echo "[restart_bridge] health check failed after restart (attempt ${i})"
    if [ "${BRIDGE_MODE}" = "isolated" ]; then
      echo "[restart_bridge] tail ${SUP_LOG_FILE}"
      tail -n 120 "${SUP_LOG_FILE}" || true
    else
      echo "[restart_bridge] tail ${LOG_FILE}"
      tail -n 120 "${LOG_FILE}" || true
    fi
    exit 1
  fi
  sleep 0.4
done

echo "[restart_bridge] bridge restart successful and stable at ${HEALTH_URL}"

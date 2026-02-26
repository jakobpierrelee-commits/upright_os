#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNLOG_DIR="${ROOT_DIR}/.runlogs"
mkdir -p "${RUNLOG_DIR}"

BRIDGE_INSTANCE="${APP_BRIDGE_INSTANCE:-upright-lean-v1}"
ENTRYPOINT="${ROOT_DIR}/tools/lean_bridge_entry.py"
PID_FILE="${RUNLOG_DIR}/bridge-${BRIDGE_INSTANCE}.pid"
SUP_PID_FILE="${RUNLOG_DIR}/bridge-supervisor-${BRIDGE_INSTANCE}.pid"

kill_pid_if_alive() {
  local pid="$1"
  local label="$2"
  if [ -n "${pid}" ] && kill -0 "${pid}" 2>/dev/null; then
    echo "[stop_bridge] stopping ${label} pid=${pid}"
    kill "${pid}" 2>/dev/null || true
    sleep 0.3
    if kill -0 "${pid}" 2>/dev/null; then
      kill -9 "${pid}" 2>/dev/null || true
    fi
  fi
}

if [ -f "${PID_FILE}" ]; then
  pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
  kill_pid_if_alive "${pid:-}" "bridge"
  rm -f "${PID_FILE}"
fi

if [ -f "${SUP_PID_FILE}" ]; then
  sup_pid="$(cat "${SUP_PID_FILE}" 2>/dev/null || true)"
  kill_pid_if_alive "${sup_pid:-}" "bridge supervisor"
  rm -f "${SUP_PID_FILE}"
fi

bridge_pids="$(pgrep -f -- "${ENTRYPOINT} --supervised --instance ${BRIDGE_INSTANCE}" || true)"
if [ -n "${bridge_pids}" ]; then
  echo "[stop_bridge] stopping stale bridge pids: ${bridge_pids//$'\n'/ }"
  # shellcheck disable=SC2086
  kill ${bridge_pids} 2>/dev/null || true
  sleep 0.3
  # shellcheck disable=SC2086
  kill -9 ${bridge_pids} 2>/dev/null || true
fi

sup_pids="$(pgrep -f -- "lean_bridge_supervisor.sh --instance ${BRIDGE_INSTANCE}" || true)"
if [ -n "${sup_pids}" ]; then
  echo "[stop_bridge] stopping stale supervisor pids: ${sup_pids//$'\n'/ }"
  # shellcheck disable=SC2086
  kill ${sup_pids} 2>/dev/null || true
  sleep 0.3
  # shellcheck disable=SC2086
  kill -9 ${sup_pids} 2>/dev/null || true
fi

echo "[stop_bridge] bridge stopped (instance=${BRIDGE_INSTANCE})"

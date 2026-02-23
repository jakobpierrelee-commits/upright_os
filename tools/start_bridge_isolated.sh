#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNLOG_DIR="${ROOT_DIR}/.runlogs"
mkdir -p "${RUNLOG_DIR}"

BRIDGE_INSTANCE="${APP_BRIDGE_INSTANCE:-upright-lean-v1}"
BRIDGE_HOST="${APP_BRIDGE_HOST:-127.0.0.1}"
BRIDGE_PORT="${APP_BRIDGE_PORT:-8797}"
HEALTH_URL="http://${BRIDGE_HOST}:${BRIDGE_PORT}/health"

SUP_PID_FILE="${RUNLOG_DIR}/bridge-supervisor-${BRIDGE_INSTANCE}.pid"
SUP_LOG_FILE="${RUNLOG_DIR}/bridge-supervisor-${BRIDGE_INSTANCE}.log"
SUP_SCRIPT="${ROOT_DIR}/tools/lean_bridge_supervisor.sh"
ENTRYPOINT="${ROOT_DIR}/tools/lean_bridge_entry.py"

health_ok() {
  curl -fsS --max-time 1 "${HEALTH_URL}" >/dev/null 2>&1
}

supervisor_running() {
  if [ ! -f "${SUP_PID_FILE}" ]; then
    return 1
  fi
  local pid
  pid="$(cat "${SUP_PID_FILE}" 2>/dev/null || true)"
  [ -n "${pid}" ] || return 1
  kill -0 "${pid}" 2>/dev/null || return 1
  ps -p "${pid}" -o args= 2>/dev/null | grep -q "lean_bridge_supervisor.sh --instance ${BRIDGE_INSTANCE}"
}

if supervisor_running; then
  echo "[start_bridge_isolated] supervisor already running (pid=$(cat "${SUP_PID_FILE}"), instance=${BRIDGE_INSTANCE})"
else
  echo "[start_bridge_isolated] starting bridge supervisor in isolated session..."
  (
    cd "${ROOT_DIR}"
    python3 - "${SUP_SCRIPT}" "${BRIDGE_INSTANCE}" "${SUP_LOG_FILE}" "${SUP_PID_FILE}" <<'PY'
import subprocess
import sys

script = sys.argv[1]
instance = sys.argv[2]
log_file = sys.argv[3]
pid_file = sys.argv[4]

with open(log_file, "ab", buffering=0) as log:
    proc = subprocess.Popen(
        [script, "--instance", instance],
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=log,
        start_new_session=True,
        close_fds=True,
    )

with open(pid_file, "w", encoding="utf-8") as f:
    f.write(str(proc.pid))
PY
  )
  echo "[start_bridge_isolated] supervisor started (pid=$(cat "${SUP_PID_FILE}"), instance=${BRIDGE_INSTANCE})"
fi

echo "[start_bridge_isolated] waiting for bridge health..."
tries=0
max_tries=80
until health_ok; do
  tries=$((tries + 1))
  if [ "${tries}" -ge "${max_tries}" ]; then
    echo "[start_bridge_isolated] bridge failed to become healthy at ${HEALTH_URL}"
    echo "[start_bridge_isolated] tail ${SUP_LOG_FILE}"
    tail -n 120 "${SUP_LOG_FILE}" || true
    exit 1
  fi
  sleep 0.25
done

stable_checks="${BRIDGE_START_STABLE_CHECKS:-20}"
stable_interval_s="${BRIDGE_START_STABLE_INTERVAL_S:-0.5}"
for _ in $(seq 1 "${stable_checks}"); do
  if ! health_ok; then
    echo "[start_bridge_isolated] health became unstable after startup at ${HEALTH_URL}"
    echo "[start_bridge_isolated] tail ${SUP_LOG_FILE}"
    tail -n 120 "${SUP_LOG_FILE}" || true
    exit 1
  fi
  sleep "${stable_interval_s}"
done

echo "[start_bridge_isolated] bridge healthy at ${HEALTH_URL}"

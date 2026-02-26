#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNLOG_DIR="${ROOT_DIR}/.runlogs"
mkdir -p "${RUNLOG_DIR}"

BRIDGE_INSTANCE="${APP_BRIDGE_INSTANCE:-upright-lean-v1}"
# Clean-lane hard lock: always route bridge traffic to localhost:8797.
BRIDGE_HOST="127.0.0.1"
BRIDGE_PORT="8797"
HEALTH_URL="http://${BRIDGE_HOST}:${BRIDGE_PORT}/health"
UI_HOST="${APP_UI_HOST:-0.0.0.0}"
UI_PORT="${APP_UI_PORT:-5173}"
PID_FILE="${RUNLOG_DIR}/bridge-${BRIDGE_INSTANCE}.pid"
LOG_FILE="${RUNLOG_DIR}/bridge-${BRIDGE_INSTANCE}.log"
BRIDGE_AUTOSTART="${APP_BRIDGE_AUTOSTART:-0}"

health_ok() {
  curl -fsS --max-time 1 "${HEALTH_URL}" >/dev/null 2>&1
}

port_in_use() {
  local p="$1"
  lsof -tiTCP:"${p}" -sTCP:LISTEN >/dev/null 2>&1
}

choose_ui_port() {
  local preferred="$1"
  local max_tries="${2:-20}"
  local p="${preferred}"
  local i=0
  while [ "${i}" -lt "${max_tries}" ]; do
    if ! port_in_use "${p}"; then
      echo "${p}"
      return 0
    fi
    p=$((p + 1))
    i=$((i + 1))
  done
  return 1
}

start_bridge_if_needed() {
  if [ "${APP_BRIDGE_HOST:-}" != "" ] && [ "${APP_BRIDGE_HOST}" != "127.0.0.1" ]; then
    echo "[launcher] ignoring APP_BRIDGE_HOST=${APP_BRIDGE_HOST}; clean lane is locked to 127.0.0.1"
  fi
  if [ "${APP_BRIDGE_PORT:-}" != "" ] && [ "${APP_BRIDGE_PORT}" != "8797" ]; then
    echo "[launcher] ignoring APP_BRIDGE_PORT=${APP_BRIDGE_PORT}; clean lane is locked to 8797"
  fi
  if [ "${BRIDGE_AUTOSTART}" != "1" ]; then
    echo "[launcher] bridge autostart disabled by default (APP_BRIDGE_AUTOSTART=${BRIDGE_AUTOSTART})"
    if ! health_ok; then
      echo "[launcher] bridge is not running."
      echo "[launcher] start it in foreground first:"
      echo "  ./tools/start_bridge_fg.sh"
      return 1
    fi
    return 0
  fi
  if [ -f "${PID_FILE}" ]; then
    BR_PID="$(cat "${PID_FILE}" 2>/dev/null || true)"
    if [ -n "${BR_PID:-}" ] && kill -0 "${BR_PID}" 2>/dev/null; then
      echo "[launcher] bridge process already running (pid=${BR_PID})"
      return 0
    fi
  fi
  echo "[launcher] starting bridge..."
  "${ROOT_DIR}/tools/start_bridge_isolated.sh"
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

check_clean_contract() {
  local payload
  if ! payload="$(curl -fsS --max-time 2 "${HEALTH_URL%/health}/agent/clean/status?mode=app_dev" 2>/dev/null)"; then
    echo "[launcher] failed to query clean status contract endpoint"
    echo "[launcher] restart bridge in foreground:"
    echo "  ./tools/restart_bridge.sh"
    return 1
  fi
  if ! python3 - "$payload" <<'PY'
import json, sys
raw = sys.argv[1]
try:
    d = json.loads(raw)
except Exception:
    raise SystemExit(2)
api = d.get("clean_api") if isinstance(d, dict) else {}
ver = int((api or {}).get("version") or 0)
caps = (api or {}).get("capabilities") or []
ok = ver >= 2 and "firmware_upload_precheck" in caps and "clean_chat_stream" in caps
raise SystemExit(0 if ok else 1)
PY
  then
    echo "[launcher] bridge contract is outdated for this UI (clean_api.version<2 or missing capabilities)."
    echo "[launcher] restart bridge in foreground on latest code:"
    echo "  ./tools/restart_bridge.sh"
    return 1
  fi
  echo "[launcher] clean API contract verified (v2)"
}

start_ui() {
  local ui_mode="${APP_UI_MODE:-dev}"
  local preferred_port="${UI_PORT}"
  local selected_port=""
  if ! selected_port="$(choose_ui_port "${preferred_port}" 30)"; then
    echo "[launcher] no free UI port found starting at ${preferred_port}"
    return 1
  fi
  if [ "${selected_port}" != "${preferred_port}" ]; then
    echo "[launcher] ui port ${preferred_port} busy, using ${selected_port}"
  fi

  echo "[launcher] starting ops console UI (${ui_mode}) at http://${UI_HOST}:${selected_port} ..."
  echo "[launcher] keep this terminal open while UI is running."
  cd "${ROOT_DIR}/app/ui/ops-console"
  export VITE_BRIDGE_BASE="http://127.0.0.1:8797"
  unset VITE_LEGACY_CONSOLE
  echo "[launcher] clean console mode enabled (hard-locked)"
  if [ "${ui_mode}" = "preview" ]; then
    npm run build
    exec npm run preview -- --host "${UI_HOST}" --port "${selected_port}" --strictPort
  else
    exec npm run dev -- --host "${UI_HOST}" --port "${selected_port}" --strictPort
  fi
}

start_bridge_if_needed
wait_for_bridge
check_clean_contract
start_ui

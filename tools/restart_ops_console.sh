#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UI_DIR="${ROOT_DIR}/app/ui/ops-console"
RUNLOG_DIR="${ROOT_DIR}/.runlogs"
mkdir -p "${RUNLOG_DIR}"

UI_HOST="${APP_UI_HOST:-0.0.0.0}"
UI_PORT="${APP_UI_PORT:-5173}"

kill_match() {
  local pattern="$1"
  local pids
  pids="$(pgrep -f -- "$pattern" || true)"
  if [ -z "${pids}" ]; then
    return 0
  fi
  echo "[restart_ui] stopping: ${pattern} -> ${pids//$'\n'/ }"
  # shellcheck disable=SC2086
  kill ${pids} 2>/dev/null || true
  sleep 0.4
  local alive=()
  while IFS= read -r pid; do
    [ -z "$pid" ] && continue
    if kill -0 "$pid" 2>/dev/null; then
      alive+=("$pid")
    fi
  done <<< "${pids}"
  if [ ${#alive[@]} -gt 0 ]; then
    echo "[restart_ui] force killing lingering pids: ${alive[*]}"
    kill -9 "${alive[@]}" 2>/dev/null || true
  fi
}

kill_match "app/ui/ops-console.*vite"
kill_match "npm run dev -- --host"
kill_match "vite --host"

PORT_PID="$(lsof -tiTCP:${UI_PORT} -sTCP:LISTEN || true)"
if [ -n "${PORT_PID}" ]; then
  echo "[restart_ui] evicting stale listener on :${UI_PORT} pid=${PORT_PID}"
  kill "${PORT_PID}" 2>/dev/null || true
  sleep 0.2
  if kill -0 "${PORT_PID}" 2>/dev/null; then
    kill -9 "${PORT_PID}" 2>/dev/null || true
  fi
fi

echo "[restart_ui] starting UI in foreground at http://${UI_HOST}:${UI_PORT}"
echo "[restart_ui] keep this terminal open while UI is running."
cd "${UI_DIR}"
exec npm run dev -- --host "${UI_HOST}" --port "${UI_PORT}" --strictPort

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

export APP_BRIDGE_AUTOSTART="${APP_BRIDGE_AUTOSTART:-0}"
export APP_UI_LEGACY=0

if ! curl -fsS --max-time 1 "http://${APP_BRIDGE_HOST:-127.0.0.1}:${APP_BRIDGE_PORT:-8797}/health" >/dev/null 2>&1; then
  echo "[start_clean_console] bridge is not running."
  echo "[start_clean_console] start bridge in foreground first:"
  echo "  ./tools/start_bridge_fg.sh"
  exit 1
fi

exec ./tools/start_ops_console.sh

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

BRIDGE_INSTANCE="${APP_BRIDGE_INSTANCE:-upright-lean-v1}"
BRIDGE_HOST="${APP_BRIDGE_HOST:-127.0.0.1}"
BRIDGE_PORT="${APP_BRIDGE_PORT:-8797}"
TELEMETRY_PORT="${APP_TELEMETRY_PORT:-8798}"

cd "${ROOT_DIR}"
echo "[start_bridge_fg] starting bridge in foreground (instance=${BRIDGE_INSTANCE})"
echo "[start_bridge_fg] http://$BRIDGE_HOST:$BRIDGE_PORT telemetry:$TELEMETRY_PORT"
exec python3 -u tools/lean_bridge_entry.py \
  --supervised \
  --instance "${BRIDGE_INSTANCE}" \
  --host "${BRIDGE_HOST}" \
  --http-port "${BRIDGE_PORT}" \
  --telemetry-port "${TELEMETRY_PORT}"

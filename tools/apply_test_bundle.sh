#!/usr/bin/env bash
set -euo pipefail

# Nano guardrail:
# Reapply+verify before each run to defend against observed runtime drift on
# constrained/dev-path hardware. Treat this as compat/nano policy, not a
# universal requirement for future MCU targets.

BRIDGE_URL="${BRIDGE_URL:-http://127.0.0.1:8797/command}"

# Current tuning bundle defaults (override via env when needed).
BUNDLE_PID_KP="${BUNDLE_PID_KP:-30.8}"
BUNDLE_PID_KI="${BUNDLE_PID_KI:-0}"
BUNDLE_PID_KD="${BUNDLE_PID_KD:-2.2}"
BUNDLE_MOTION_KV="${BUNDLE_MOTION_KV:-0.0061}"
BUNDLE_MOTION_KX="${BUNDLE_MOTION_KX:-0.0002}"
BUNDLE_LIMIT_OUT_MAX="${BUNDLE_LIMIT_OUT_MAX:-235}"
BUNDLE_LIMIT_TIP="${BUNDLE_LIMIT_TIP:-35}"
BUNDLE_LIMIT_3="${BUNDLE_LIMIT_3:-70}"
BUNDLE_LIMIT_4="${BUNDLE_LIMIT_4:-120}"

post_cmd() {
  local cmd="$1"
  curl -s "$BRIDGE_URL" \
    -H 'Content-Type: application/json' \
    -d "{\"cmd\":\"$cmd\"}" >/dev/null
}

post_cmd "PID ${BUNDLE_PID_KP} ${BUNDLE_PID_KI} ${BUNDLE_PID_KD}"
post_cmd "MOTION ${BUNDLE_MOTION_KV} ${BUNDLE_MOTION_KX}"
post_cmd "LIMITS ${BUNDLE_LIMIT_OUT_MAX} ${BUNDLE_LIMIT_TIP} ${BUNDLE_LIMIT_3} ${BUNDLE_LIMIT_4}"

# Verify active PID/MOTION values.
EXP_KP="$(printf '%.4f' "${BUNDLE_PID_KP}")" \
EXP_KI="$(printf '%.4f' "${BUNDLE_PID_KI}")" \
EXP_KD="$(printf '%.4f' "${BUNDLE_PID_KD}")" \
EXP_KV="$(printf '%.4f' "${BUNDLE_MOTION_KV}")" \
EXP_KX="$(printf '%.4f' "${BUNDLE_MOTION_KX}")" \
  "$(dirname "$0")/verify_tune.sh"

echo "OK BUNDLE pid=(${BUNDLE_PID_KP},${BUNDLE_PID_KI},${BUNDLE_PID_KD}) motion=(${BUNDLE_MOTION_KV},${BUNDLE_MOTION_KX}) limits=(${BUNDLE_LIMIT_OUT_MAX},${BUNDLE_LIMIT_TIP},${BUNDLE_LIMIT_3},${BUNDLE_LIMIT_4})"

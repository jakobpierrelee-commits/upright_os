#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

BASE="${BASE:-http://127.0.0.1:8797}"
BOT_ON_STAND_OK="${BOT_ON_STAND_OK:-1}"
AUTO_WHEEL_PROBE="${AUTO_WHEEL_PROBE:-1}"
AUTO_ESTOP_PROBE="${AUTO_ESTOP_PROBE:-1}"
WHEEL_PROBE_RETRIES="${WHEEL_PROBE_RETRIES:-3}"
WHEEL_PROBE_PWM="${WHEEL_PROBE_PWM:-110}"
WHEEL_PROBE_MS="${WHEEL_PROBE_MS:-160}"
LEFT_WHEEL_PULSE_OK="${LEFT_WHEEL_PULSE_OK:-0}"
RIGHT_WHEEL_PULSE_OK="${RIGHT_WHEEL_PULSE_OK:-0}"
ARTIFACT_DIR="${ARTIFACT_DIR:-.runlogs/prearm_signoff}"

need_jq() {
  command -v jq >/dev/null 2>&1
}

if ! need_jq; then
  echo "[check_prearm_signoff] jq is required"
  exit 1
fi

if [[ "${BOT_ON_STAND_OK}" != "1" ]]; then
  echo "[check_prearm_signoff] Refusing to run with BOT_ON_STAND_OK!=1."
  echo "[check_prearm_signoff] Lift robot / place on stand, then run with BOT_ON_STAND_OK=1."
  exit 1
fi

if [[ "${AUTO_WHEEL_PROBE}" != "1" ]]; then
  if [[ "${LEFT_WHEEL_PULSE_OK}" != "1" || "${RIGHT_WHEEL_PULSE_OK}" != "1" ]]; then
    echo "[check_prearm_signoff] AUTO_WHEEL_PROBE=0 requires LEFT_WHEEL_PULSE_OK=1 and RIGHT_WHEEL_PULSE_OK=1."
    exit 1
  fi
fi

echo "[check_prearm_signoff] BASE=${BASE}"
echo "[check_prearm_signoff] stand=${BOT_ON_STAND_OK} auto_wheel=${AUTO_WHEEL_PROBE} auto_estop=${AUTO_ESTOP_PROBE}"

mkdir -p "${ARTIFACT_DIR}"
ts="$(date +%Y%m%d_%H%M%S)"
artifact="${ARTIFACT_DIR}/prearm_signoff_${ts}.json"

health="$(curl -fsS "${BASE}/health")"
echo "${health}" | jq -e '.ok == true' >/dev/null

payload="$(
  jq -nc \
    --argjson stand "${BOT_ON_STAND_OK}" \
    --argjson auto_wheel "${AUTO_WHEEL_PROBE}" \
    --argjson auto_estop "${AUTO_ESTOP_PROBE}" \
    --argjson retries "${WHEEL_PROBE_RETRIES}" \
    --argjson pwm "${WHEEL_PROBE_PWM}" \
    --argjson ms "${WHEEL_PROBE_MS}" \
    --argjson left_ok "${LEFT_WHEEL_PULSE_OK}" \
    --argjson right_ok "${RIGHT_WHEEL_PULSE_OK}" \
    '{
      bot_on_stand_ok: ($stand == 1),
      auto_wheel_probe: ($auto_wheel == 1),
      auto_estop_probe: ($auto_estop == 1),
      wheel_probe_retries: $retries,
      wheel_probe_pwm: $pwm,
      wheel_probe_ms: $ms,
      left_wheel_pulse_ok: ($left_ok == 1),
      right_wheel_pulse_ok: ($right_ok == 1)
    }'
)"

resp="$(
  curl -fsS -X POST "${BASE}/arm/precheck" \
    -H "Content-Type: application/json" \
    -d "${payload}"
)"
echo "${resp}" > "${artifact}"

ok_prearm="$(echo "${resp}" | jq -r '.prearm_check.ok // false')"
ok_gate="$(echo "${resp}" | jq -r '.prearm_safety.passed // false')"
phase="$(echo "${resp}" | jq -r '.prearm_check.phase // "unknown"')"
summary="$(echo "${resp}" | jq -r '.prearm_check.summary // "n/a"')"
failed_checks="$(echo "${resp}" | jq -r '.prearm_check.checks // [] | map(select(.status!="pass") | .id) | join(",")')"

echo "[check_prearm_signoff] phase=${phase}"
echo "[check_prearm_signoff] summary=${summary}"
echo "[check_prearm_signoff] artifact=${artifact}"

if [[ "${ok_prearm}" == "true" && "${ok_gate}" == "true" ]]; then
  echo "[check_prearm_signoff] PASS"
  exit 0
fi

if [[ -z "${failed_checks}" ]]; then
  failed_checks="unknown"
fi
echo "[check_prearm_signoff] FAIL failed_checks=${failed_checks}"
exit 1


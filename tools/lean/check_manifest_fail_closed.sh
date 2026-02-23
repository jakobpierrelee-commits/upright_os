#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-http://127.0.0.1:8797}"
MODE="${MODE:-app_dev}"
MAX_TIME="${MAX_TIME:-20}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

if ! command -v jq >/dev/null 2>&1; then
  echo "[check_manifest_fail_closed] jq is required"
  exit 1
fi

SKETCH_DIR="${TMP_DIR}/manifest_fail_closed_case"
mkdir -p "${SKETCH_DIR}"
SKETCH_FILE="${SKETCH_DIR}/manifest_fail_closed_case.ino"

cat > "${SKETCH_FILE}" <<'INO'
void setup() {}
void loop() {}
INO

cat > "${SKETCH_DIR}/runtime_manifest_v1.json" <<'JSON'
{
  "version": "runtime_manifest_v1",
  "board": {
    "id": "nano",
    "family": "arduino_avr",
    "fqbn": "arduino:avr:nano"
  },
  "interfaces": {
    "imu": {"pins": {"sda": 18, "scl": 19}},
    "encoders": {"pins": {"left_a": 2, "left_b": 4, "right_a": 3, "right_b": 5}},
    "actuator": {"pins": {"left_pwm": 9, "left_dir": 7, "right_pwm": 10, "right_dir": 8}}
  },
  "telemetry_fields": ["mode", "ang", "raw", "gyro", "out", "fault", "estop", "kp", "ki", "kd", "set"],
  "commands": ["GET", "ARM", "DISARM", "PID", "SETPOINT"]
}
JSON

resp_ok="$(curl -fsS --max-time "${MAX_TIME}" -X POST "${BASE}/agent/clean/preflight" \
  -H 'Content-Type: application/json' \
  -d "{\"mode\":\"${MODE}\",\"sketch\":\"${SKETCH_DIR}\",\"gate_only\":true}")"

ok_val="$(echo "${resp_ok}" | jq -r '.ok')"
if [[ "${ok_val}" != "true" ]]; then
  echo "[check_manifest_fail_closed] expected baseline preflight pass, got: ${resp_ok}"
  exit 1
fi

cat > "${SKETCH_DIR}/runtime_manifest_v1.json" <<'JSON'
{
  "version": "runtime_manifest_v1",
  "board": {
    "id": "nano",
    "family": "arduino_avr",
    "fqbn": "arduino:avr:nano"
  },
  "interfaces": {
    "imu": {"pins": {"sda": 18, "scl": 19}},
    "encoders": {"pins": {"left_a": 2, "left_b": 4, "right_a": 3, "right_b": 5}},
    "actuator": {"pins": {"left_pwm": 9, "left_dir": 7, "right_pwm": 10, "right_dir": 8}}
  },
  "telemetry_fields": ["mode", "ang", "raw", "gyro", "out", "fault", "estop", "kp", "ki", "kd", "set"],
  "commands": ["GET", "ARM", "DISARM", "PID"]
}
JSON

resp_fail="$(curl -fsS --max-time "${MAX_TIME}" -X POST "${BASE}/agent/clean/preflight" \
  -H 'Content-Type: application/json' \
  -d "{\"mode\":\"${MODE}\",\"sketch\":\"${SKETCH_DIR}\",\"gate_only\":true}")"

fail_val="$(echo "${resp_fail}" | jq -r '.ok')"
if [[ "${fail_val}" != "false" ]]; then
  echo "[check_manifest_fail_closed] expected fail-closed preflight, got: ${resp_fail}"
  exit 1
fi

gate_reason="$(echo "${resp_fail}" | jq -r '.results[0].error // ""')"
if [[ "${gate_reason}" != runtime_manifest_invalid:* ]]; then
  echo "[check_manifest_fail_closed] expected runtime_manifest_invalid gate reason, got: ${gate_reason}"
  exit 1
fi

echo "[check_manifest_fail_closed] PASS"

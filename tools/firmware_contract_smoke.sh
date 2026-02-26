#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MVP_SKETCH="$ROOT_DIR/app/bridge/firmware_templates/upright_mvp_baseline_v1"
PROFILED_SKETCH="$ROOT_DIR/app/bridge/firmware_templates/profiled_runtime_v1"
FQBN="${FQBN:-arduino:avr:nano}"
PORT="${PORT:-}"

echo "[1/4] Compile MVP baseline"
arduino-cli compile --clean --fqbn "$FQBN" "$MVP_SKETCH"

echo
echo "[2/4] Compile profiled runtime (all profiles)"
arduino-cli compile --clean --fqbn "$FQBN" "$PROFILED_SKETCH"
arduino-cli compile --clean --fqbn "$FQBN" --build-property build.extra_flags="-DUPRIGHT_PROFILE=2" "$PROFILED_SKETCH"
arduino-cli compile --clean --fqbn "$FQBN" --build-property build.extra_flags="-DUPRIGHT_PROFILE=3" "$PROFILED_SKETCH"

echo
echo "[3/4] Static contract checks"
rg -n "STATUS mode=| ang=| raw=| gyro=| out=| kp=| ki=| kd=| set=|OK HELP GET ARM DISARM ESTOP PID SETPOINT LIMITS FILTER KAL" \
  "$ROOT_DIR/app/bridge/firmware_templates/upright_mvp_baseline_v1/upright_mvp_baseline_v1.ino" \
  "$ROOT_DIR/app/bridge/firmware_templates/profiled_runtime_v1/profiled_runtime_v1.ino"

echo
echo "[4/4] Optional live serial probe"
if [[ -z "$PORT" ]]; then
  echo "Skipping live probe (set PORT=/dev/cu.usb... to enable)."
  exit 0
fi

python3 - "$PORT" <<'PY'
import serial
import sys
import time

port = sys.argv[1]
print(f"Probing {port} at 115200...")
try:
    ser = serial.Serial(port, 115200, timeout=0.35)
except Exception as e:
    print(f"open_error: {e}")
    raise SystemExit(1)

try:
    ser.dtr = False
    time.sleep(0.2)
    ser.dtr = True
    time.sleep(1.0)
    ser.reset_input_buffer()
    cmds = ["IDENT\n", "HELP\n", "GET\n", "LOGT 1\n"]
    for cmd in cmds:
        ser.write(cmd.encode("utf-8"))
        time.sleep(0.2)
    time.sleep(0.9)
    payload = ser.read(8192).decode("utf-8", errors="ignore").strip()
    if not payload:
        print("no_response")
        raise SystemExit(2)
    print(payload)
finally:
    ser.close()
PY

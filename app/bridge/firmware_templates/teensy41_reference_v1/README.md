# Teensy 4.1 Reference Runtime (v1)

Reference non-AVR firmware template for clean-lane compatibility checks.

## Purpose
- Prove one end-to-end non-AVR profile path (Teensy 4.1) for runtime manifest validation and profile compatibility gates.
- Keep the same arming + telemetry contract surface used by the clean IDE and preflight flow.

## Contract surface
- Commands: `GET`, `ARM`, `DISARM`, `PID`, `SETPOINT`, `LIMITS`, `MOTION`, `CAL ZERO`, `SAVECFG`
- Telemetry fields: `mode`, `ang`, `raw`, `gyro`, `out`, `fault`, `estop`, `kp`, `ki`, `kd`, `set`, `wpos`, `wspd`

## Files
- `teensy41_reference_v1.ino` minimal command/status loop
- `runtime_manifest_v1.json` canonical Teensy 4.1 manifest used by validators

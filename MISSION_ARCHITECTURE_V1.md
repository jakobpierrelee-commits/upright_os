# Mission Architecture V1

## Goal
Build a repeatable self-balancing robotics platform that can be commissioned in minutes, verified automatically, and controlled by a web app.

## System Layers
1. Firmware (Nano, hard real-time):
- IMU fusion, balance loop, safety FSM, motor control, encoder capture.
- Deterministic command parser and telemetry output.

2. Commissioning (host Python):
- Baseline application, encoder validation, motor pulse validation, burst capture, metric scoring.
- Produces machine-readable artifacts for every run.

3. App Bridge (host/ESP32 service):
- Stable API surface for commands and telemetry.
- Connection lifecycle, command ack/retry, watchdog integration.

4. UI (web):
- Calibration wizard, tuning panels, test orchestration, charts, fault indicators.
- Profile management and one-click test execution.

## Canonical Command Contract
- `GET`
- `ARM`, `DISARM`, `STATE SAFE|ARM|BAL|FAULT`
- `PID <kp> <ki> <kd>`
- `MOTION <kv> <kx>`
- `SETPOINT <deg>`
- `LIMITS <out tip iMax>`
- `CAL ZERO`, `ZERO`
- `ENCMODE AUTO|LEFT|RIGHT`
- `SAVECFG`, `LOADCFG`, `DEFAULTCFG`
- `LOGCSV 1|0`, `LOGT 1|0`, `BURSTCSV <delay lines>`
- `MOTOR <l r>`, `MOTOROFF`

## Data Contract
Commissioning outputs:
- `tests/results/run_<ts>.csv`
- `tests/results/metrics_<ts>.json`

Required success flags:
- `enc_check_ok=1`
- `motor_pulse_ok=1`
- `ok=1` (burst quality passes)

## Commissioning Pipeline (Current 5-Phase)
1. Apply baseline config.
2. Encoder integrity check (manual wheel spins).
3. Motor pulse validation (deterministic actuator check).
4. Burst capture in upright support posture.
5. Metric evaluation and pass/fail.

## Refactor Track
1. Freeze current known-good commissioning behavior.
2. Formalize message schema and typed parser in host tools.
3. Add profile files:
- `profiles/bench_safe.json`
- `profiles/floor_stable.json`
- `profiles/floor_aggressive.json`
4. Build bridge service API.
5. Build UI workflow:
- Connect -> Calibrate -> Validate -> Balance -> Save profile.

## Exit Criteria for V1
1. Robot passes 5-phase commissioning in <5 minutes.
2. Repeat pass rate >= 90% across 10 consecutive sessions.
3. Ground-contact nudge test recovers without runaway.
4. App can run full commissioning + parameter save without Arduino IDE.

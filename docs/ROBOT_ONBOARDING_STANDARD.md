# UpRight.os Robot Onboarding Standard

## Goal
Make adding a new robot (new MCU, pins, parts) repeatable, fast, and safe with one guided flow and objective pass/fail criteria.

## User Flow (What the user sees)
1. `New Robot` wizard starts.
2. `Detect`: auto-scan port, board/FQBN, firmware profile guess, compatibility probe.
3. `Declare Hardware`: user confirms/edits motor driver, IMU model, encoder setup, wheel/chassis class, battery config.
4. `Map Pins`: user enters/loads pin map template for that board.
5. `Flash + Verify`: compile/upload, then automatic command + telemetry verification.
6. `Calibrate`: run `CAL ZERO`, verify stable upright angle.
7. `Stress Test`: 60s serial/telemetry reliability test.
8. `Save Profile`: profile becomes active and reusable.

## Done Criteria (must all pass)
1. Compatibility: required status fields present: `ang`, `raw`, `gyro|gyr|gx`.
2. Commands: `GET`, `ARM`, `DISARM`, `CAL ZERO`, `PID`, `MOTION`, `SETPOINT` all succeed.
3. Telemetry freshness: `last_status_age_ms < 500` for >=95% of samples in 60s.
4. Timeouts: serial command timeouts <= 1 in 60s stress run.
5. Queue health: queue depth remains <= 2 for >=95% of samples.
6. Safety: E-stop latch/reset works and disarm always drops output to idle.
7. Calibration: post-zero angle drift remains within configured threshold (default +/-2 deg at rest).

If any check fails, wizard stays `Not Ready` and lists exact failing checks with next action.

## Robot Profile Contract
Store one JSON profile per robot:
- `profile_id` (stable UUID)
- `label`
- `board`: MCU family, FQBN, upload port defaults
- `parts`: IMU, motor driver, encoder type, voltage sense
- `pinmap`: semantic pins (`motor_left_pwm`, `imu_sda`, etc.)
- `firmware`: sketch path, protocol version, firmware profile
- `limits`: safety thresholds (tip angle, output limits)
- `calibration`: zero offset and timestamp
- `validation`: last test run summary and pass/fail

Profiles are local-first and export/importable.

## Protocol Rule (critical)
UI/bridge remain robot-agnostic. Firmware adapts to hardware.
- Keep command/status protocol stable.
- Change board-specific firmware internals only (pins, drivers, ISR wiring, timing).
- Do not change UI contracts per robot unless protocol version increments.

## Fast Path for Repeat Builds
1. Select existing profile template (same board/chassis).
2. Update only label + port + calibration.
3. Re-run Verify + Stress Test.
4. Save as new profile revision.

## Implementation Plan in this codebase
1. Re-surface `Connect Wizard` as first-class tab/page in `App.tsx`.
2. Add a typed `RobotProfile` model in `app/ui/ops-console/src/api.ts`.
3. Add bridge endpoints:
   - `POST /profiles/validate`
   - `POST /profiles/save`
   - `GET /profiles`
   - `POST /profiles/activate`
4. Use existing probes:
   - `/probe/compat`
   - `/probe/connect`
   - `/diag/serial`
   - `app/bridge/rugged_probe.py` logic for stress metrics.
5. Gate activation on `Done Criteria` only.

## UX Requirements
1. Single progress rail with explicit step state: `Pending`, `Running`, `Pass`, `Fail`.
2. No silent failure: every fail state includes command output and direct remediation.
3. One-click `Re-test failed checks`.
4. Exportable validation report for support/debug.

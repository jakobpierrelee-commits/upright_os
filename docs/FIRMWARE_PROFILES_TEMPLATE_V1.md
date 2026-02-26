# Firmware Profiles Template V1

## Files
1. `/Users/jvke/Documents/UpRight.os/app/bridge/firmware_templates/profiled_runtime_v1/feature_profile.h`
2. `/Users/jvke/Documents/UpRight.os/app/bridge/firmware_templates/profiled_runtime_v1/module_contracts.h`
3. `/Users/jvke/Documents/UpRight.os/app/bridge/firmware_templates/profiled_runtime_v1/profiled_runtime_v1.ino`

## Goal
Use one core runtime with strict safety/determinism rules and enable non-critical features by profile.

## Profiles
1. `UPRIGHT_PROFILE_TEST_MINIMAL`
- Minimal feature surface for repeatable tests.
- Keep core safety and telemetry only.
2. `UPRIGHT_PROFILE_LAB_FULL`
- Enables diagnostics and tuning helpers for development.
3. `UPRIGHT_PROFILE_FIELD_HARDENED`
- Keeps only field-vetted options.
- Disables high-risk tuning/debug commands.

## Non-Optional Core Rules
1. Fixed-rate loop
2. Safety state machine + estop latch
3. Watchdog and loop overrun detection
4. Sensor plausibility checks
5. No dynamic allocation in real-time path
6. Implement `FAULTCLR` command (required by Tune `Clear Fault` control + compat policy)

These are always enabled in `feature_profile.h`.

## Optional Feature Rules
1. Optional module must fail safe (`failOff()`), never fail dangerous.
2. Optional module health must not gate core safety path.
3. Optional modules can be disabled by compile profile without changing core behavior.

## How To Apply In A Real Sketch
1. Copy the template folder to a new generated firmware target.
2. Keep command compatibility:
- `GET`, `HELP`, `ARM`, `DISARM`, `ESTOP`, `PID`, `SETPOINT`, `IDENT`, `FAULTCLR`
3. Keep status compatibility keys:
- `mode`, `estop`, `ang`, `raw`, `gyro`, `out`, `kp`, `ki`, `kd`, `set`
4. Wire real sensors/actuators in the placeholder sections.
5. Add any new fields as additive telemetry only.

## Fault semantics (v1.1 update)
1. Loop overrun fault (code 11) is based on consecutive overruns:
- Latch after 5 consecutive control steps exceeding `MAX_CONTROL_STEP_US`.
- Reset the consecutive counter on an in-budget control step.
2. This reduces false latching from sporadic serial/host jitter while preserving deterministic fail-safe behavior.

## CI Build Matrix Recommendation
1. Build `TEST_MINIMAL` on every commit.
2. Build `LAB_FULL` on every commit.
3. Build `FIELD_HARDENED` on release branches.
4. Require all profile builds to pass before merge.

## Immediate Next Step
Use this template as the base for your next hardware-integrated sketch, then add:
1. Real IMU path
2. Real motor driver path
3. Encoder path
4. EEPROM-backed config

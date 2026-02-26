# upright_mvp_baseline_v1

Minimal starter demonstration firmware for UpRight.os.

## Why this exists
Use this when you want the smallest reliable baseline that still:
1. Boots safely
2. Speaks the UpRight-style serial contract
3. Emits stable `STATUS` telemetry
4. Demonstrates left/right encoder interrupt plumbing (`D2` + `D4 PCINT`)

## Command set
1. `GET`
2. `HELP`
3. `IDENT`
4. `ARM`
5. `DISARM`
6. `ESTOP 1|0`
7. `PID <kp> <ki> <kd>`
8. `SETPOINT <deg>`
9. `LIMITS <out_max> <tip_deg>`
10. `LOGT 1|0`

## STATUS keys
`mode estop ang raw gyro set out kp ki kd encL encR overrun`

## Notes
1. Sensor and motor functions are stubs by design in this MVP.
2. Replace `read*Stub()` and `applyMotorOutputStub()` for hardware integration.
3. Loop runs at 200 Hz with simple overrun counting.

## Three-demo model
1. `upright_mvp_baseline_v1`: minimal stable baseline
2. `templates/profiled_runtime_v1`: safety/profile architecture template
3. `upright_control_lab_v1`: advanced control-feature demo (windup, filters, CC, TF)

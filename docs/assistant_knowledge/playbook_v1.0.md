# UpRight Balancer Tuning Playbook v1.0

## Goal
Minimize tilt error and recovery oscillation while preserving motor smoothness and avoiding fail-safe events.

## Required telemetry
- `ang` (filtered angle, deg)
- `raw` (accelerometer angle, deg)
- `gyro|gyr|gx` (rate, dps)
- `out` (controller output)
- `kp,ki,kd,kv,kx,set`
- `mode,estop`

## Fast decision loop
1. Check safety state: only tune while `mode=SAFE_IDLE` or controlled test conditions.
2. Run short test (15-30 s).
3. Classify symptom (overshoot, jitter, drift, sluggish response).
4. Apply one bounded change.
5. Re-test and compare.

## Symptom -> action
- Underdamped oscillation / overshoot:
  - Increase `kd` first.
  - If still weak response, small increase `kp`.
- High-frequency jitter / twitchy output:
  - Decrease `kd`.
  - If still noisy, reduce `kp`.
- Slow correction / lag:
  - Increase `kp` slightly.
  - If steady-state bias remains, increase `ki` slightly.
- Drift from setpoint over time:
  - Increase `ki` (small steps).
  - Verify sensor bias / zero first.
- Integral windup behavior (long recovery after disturbance):
  - Reduce `ki` or tighten limits.

## Motion feedforward guidance
- `kv`/`kx` too high causes unnecessary thrust and chatter.
- `kv`/`kx` too low causes sluggish translational compensation.
- Tune core balance (`kp,ki,kd`) first, then motion terms.

## Apply cadence
- One variable family per step (`pid` or `motion` or `setpoint`).
- One to two increments max before re-test.
- Save snapshot before each apply; revert on regression.


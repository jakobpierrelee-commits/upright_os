# Rules + Constraints v1.0

## Telemetry field mapping (UpRight)
- Filtered angle: `ang`
- Raw accel angle: `raw`
- Gyro rate: `gyro|gyr|gx`
- Controller output: `out`
- Setpoint: `set`
- PID params: `kp,ki,kd`
- Motion params: `kv,kx`
- Safety/mode: `mode,estop`

## Delta limits (single apply step)
- PID:
  - `kp`: +/- 1.0
  - `ki`: +/- 0.05
  - `kd`: +/- 0.2
- Motion:
  - `kv`: +/- 0.05
  - `kx`: +/- 0.002
- Setpoint:
  - `set`: +/- 0.5 deg

## Bounded strategy
1. If large correction is needed, split into multiple steps.
2. Apply change -> short burst test -> evaluate.
3. If metrics worsen, revert to previous snapshot.

## Evaluation metrics (preferred)
- `mean_abs_angle_deg` lower is better.
- `max_abs_angle_deg` lower is better.
- Motor pulse/chatter proxy lower is better.
- Zero watchdog/estop incidents required.

## Deterministic policy templates
- Overshoot dominated:
  - `kd += 0.05` (or `0.1` for strong overshoot), hold others.
- Jitter dominated:
  - `kd -= 0.05`; if unchanged then `kp -= 0.5`.
- Slow response:
  - `kp += 0.5`; if bias remains then `ki += 0.01`.
- Steady-state lean bias:
  - `ki += 0.01` and validate zero/calibration.

## Safety triggers
- Never auto-arm as part of tuning logic.
- If `mode` enters fail/unsafe state, stop auto-tune sequence.
- Keep revert snapshot from immediately prior state for every apply.

## Versioning policy
- Minor tactic updates: `v1.1`, `v1.2`, ...
- Major control philosophy change: `v2.0`
- Record changelog in manifest for traceability.


# Rules + Constraints v1.1 (Trusted Sources)

## Telemetry mapping
- Filtered angle: `ang`
- Raw accel angle: `raw`
- Gyro rate: `gyro|gyr|gx`
- Controller output: `out`
- Setpoint: `set`
- PID params: `kp,ki,kd`
- Motion params: `kv,kx`
- Safety/mode: `mode,estop`

## Source-backed control rules
- Favor PD-first stabilization for upright balance; add I only for persistent bias.
- Treat derivative as noise-sensitive.
- Handle actuator saturation with anti-windup discipline.
- Apply small bounded steps with immediate retest.

## Delta limits (single apply)
- PID:
  - `kp`: +/- 1.0
  - `ki`: +/- 0.05
  - `kd`: +/- 0.2
- Motion:
  - `kv`: +/- 0.05
  - `kx`: +/- 0.002
- Setpoint:
  - `set`: +/- 0.5 deg

## Deterministic policies
- Overshoot-dominant:
  - `kd += 0.05` (up to `+0.1` if severe)
- Jitter-dominant:
  - `kd -= 0.05`; if persistent, `kp -= 0.5`
- Sluggish response:
  - `kp += 0.5`; if persistent bias, `ki += 0.01`
- Steady-state lean:
  - verify zero/calibration, then `ki += 0.01`
- Windup signature:
  - `ki -= 0.01` to `0.03`, reduce aggressive integral accumulation

## Evaluation metrics
- `mean_abs_angle_deg` lower is better
- `max_abs_angle_deg` lower is better
- motor pulse/chatter proxy lower is better
- watchdog/estop events must remain zero

## Safety constraints
- Never auto-arm inside tuning actions.
- Abort tuning sequence on unsafe mode transition.
- Keep immediate pre-apply snapshot for revert.

## Versioning intent
- Minor edits: `v1.x`
- Major control philosophy shift: `v2.0`

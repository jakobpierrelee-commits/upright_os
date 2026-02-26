# Tuning Stage Tracker (One-Screen, v2 Core)

Use once per run. Keep entries short and exact.
Target firmware: `balance_mvp_v2_core`

## Run Header

- Run ID:
- Date/time:
- Operator:
- Firmware runtime/tune version:
- Surface:
- Battery state note:
- Valid for scoring: `yes/no`

## Structured Tuning Order

- Current stage:
  - `0 Preflight/parity gate`
  - `1 Sensor integrity + IMU zero`
  - `2 Setpoint neutrality (motion off)`
  - `3 Authority envelope (LIMITS/SLEW/RAMP)`
  - `4 Core PD (KI held at 0)`
  - `5 Large-error shaping (MOTIONCFG/GSCHED)`
  - `6 Motion recenter (MOTION kv/kx)`
  - `7 Integral + anti-windup polish`
  - `8 Safety thresholds/fault behavior polish`
- Direction: `forward/backtrack`
- If backtrack: implicated stage + reason

## Variable Universe Check

- Sensor/frame: `Locked-good / Suspect / Active-tuning`
- Setpoint/bias: `Locked-good / Suspect / Active-tuning`
- Envelope/shapers: `Locked-good / Suspect / Active-tuning`
- Core PID: `Locked-good / Suspect / Active-tuning`
- Motion/recenter: `Locked-good / Suspect / Active-tuning`
- Safety/fault: `Locked-good / Suspect / Active-tuning`

## Intended Full Bundle (Pre-Run)

- PID:
- SETPOINT:
- LIMITS:
- MOTION:
- SLEW:
- RAMP:
- MOTIONCFG:
- GSCHED:
- DCFG:
- AUTORUN:

## Parity Gate (Required Every Run)

- `GET` before apply captured: `yes/no`
- Full bundle applied: `yes/no`
- `GET` after apply parity exact: `yes/no`
- `SAVECFG` issued after accepted change: `yes/no`
- If `no`, which fields mismatched:

## Stage Gates (Entry/Exit)

- Stage `2` gate:
  - Entry: `MOTION 0 0`, `KI=0`
  - Exit: neutral drift minimized and directional behavior symmetric
- Stage `3` gate:
  - Entry: setpoint stable
  - Exit: no obvious slew/ramp bottleneck during moderate perturbance catch
- Stage `4` gate:
  - Entry: authority envelope acceptable
  - Exit: low shimmy and no immediate correction throw on small perturbances
- Stage `5` gate:
  - Entry: PD baseline stable
  - Exit: improved large-perturbance catch threshold without new shimmy mode
- Stage `6` gate:
  - Entry: symmetry already validated
  - Exit: recenter behavior improved without masking directional bias
- Stage `7` gate:
  - Entry: PD + shaping stable
  - Exit: less slow drift accumulation/runaway under progressive error

## Observed Outcome

- Balance time:
- First correction direction:
- Shimmy severity: `none/low/med/high`
- Failure class:
  - `reversal_miss`
  - `reversal_runaway`
  - `correction_throw`
  - `shimmy_induced_fall`
  - `authority_limited_fall`
- Reversal outcome: `caught/missed/not_applicable`
- Large perturbance catch distance: `short/medium/long`

## Decision

- Next move:
- Changed group (only one):
- Expected effect:
- Regression risk:
- Rollback target bundle ID:

## Decision Map (Fast)

1. `big errors undercorrect + small errors acceptable`:
   - check `SLEW` and `LIMITS out_max` first
   - then `GSCHED` / `MOTIONCFG`
   - then `P`
2. `small errors overcorrect + shimmy`:
   - raise damping via `D`/`DCFG`
   - only then reduce `P` if needed
3. `asymmetric behavior by direction`:
   - set `MOTION 0 0`
   - re-check `SETPOINT`
   - only then re-enable motion terms
4. `reversal_miss/reversal_runaway`:
   - check `SLEW` and `RAMP`
   - then `GSCHED`/`MOTIONCFG`
   - then `D` and finally `P`

## Current Session Notes (Carry Forward)

- Motion terms can mask setpoint/bias issues; verify symmetry with `MOTION 0 0` before deep PID changes.
- Reuse sequence first, numeric values second.
- Numeric values are bot-, motor-, calibration-, and surface-specific.

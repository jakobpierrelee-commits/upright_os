# Tuning Agent Ground Rules v1

Purpose: run balance tuning with zero ambiguity, minimal wasted runs, and explicit anti-regression control.

Scope: `app/bridge/firmware_templates/balance_mvp_v1/balance_mvp_v1.ino` on Nano test bot.

Operational form:
- `docs/TUNING_STAGE_TRACKER_TEMPLATE.md` is the required per-run worksheet.
- `docs/AGENT_SESSION_BRIEFING_STANDARD_V1.md` is the required new-session briefing standard.

## 1) Mission Rules (Hard)

1. One hypothesis per run.
2. One variable group change per run.
3. Reapply full intended runtime bundle before every run.
4. Record outcomes with fixed taxonomy only.
5. If any variable cannot be verified, run is `process_invalid_for_scoring`.
6. No PID changes before control-envelope verification (limits/slew/ramp/motion gates).
7. Every decision must consider all balance-relevant variable groups, even if only one group is changed.
8. Default direction is forward through ordered stages; backtracking is allowed only with explicit evidence.

## 2) Runtime-Adjustable High-Impact Variables

- Core gains/setpoint:
  - `PID <kp> <ki> <kd>`
  - `SETPOINT <deg>`
- Control envelope and shaping:
  - `LIMITS <out_max> <tip_deg> [i_max] [i_term_max]`
  - `SLEW <out_slew_per_s>`
  - `RAMP <arm_engage_ramp_ms>`
  - `MOTIONCFG <motion_angle_gate_deg> <motion_term_max_deg>`
  - `DCFG <d_cutoff_hz> <kaw>`
- Motion/recenter:
  - `MOTION <kv> <kx>`
- Adaptive trim:
  - `AUTOZERO <0|1>`
  - `AZCFG <step_max> <angle_gate> <gyro_gate> <out_frac_gate> <arm_holdoff_ms> <reversal_holdoff_ms> <out_sign_deadband> <wspd_gate_counts>`
  - `AZFAST <window_ms> <fast_step_max> <fast_angle_gate> <fast_gyro_gate> <fast_out_frac_gate>`
  - `AZLIMS <trim_max_deg> <err_deadband_deg>`

## 3) Required Start-of-Session Sequence

1. `GET` and save snapshot in notes as baseline.
2. `PREARM_CHECK` must pass.
3. Apply full intended bundle (all active tuning variables, not just changed variable).
4. `GET` again and verify parity with intended bundle.
5. `SAVECFG` if this run should persist.
6. Run test.

## 4) Required Per-Run Sequence

1. Reapply full intended bundle.
2. `GET` parity check.
3. `FAULTCLR` if needed.
4. Run.
5. Record:
   - balance time
   - failure class
   - first correction direction
   - reversal behavior (`caught`/`missed`)
   - shimmy severity (`none`/`low`/`med`/`high`)
6. Decide next run from symptom map only.

## 4A) Variable Universe Check (Every Run)

Before selecting next delta, quickly classify each group as:
- `Locked-good`
- `Suspect`
- `Active-tuning`

Groups:
- Sensor/frame integrity (IMU zero, axis/sign, encoder sign)
- Control envelope (`LIMITS`, `SLEW`, `RAMP`, `MOTIONCFG`, `DCFG`)
- Core stabilization (`PID`)
- Bias/trim (`SETPOINT`, `AUTOZERO`, `AZ*`)
- Motion/recenter (`MOTION kv/kx`)
- Safety/fault behavior (trip thresholds and latch behavior)

Rule:
- Change only one active group per run.
- Keep a full-bundle parity check so non-active groups cannot silently drift.

## 5) Failure Taxonomy (Use Exact Labels)

- `reversal_miss`: catches first fall, misses opposite follow-up.
- `reversal_runaway`: opposite-direction runaway after catch.
- `correction_throw`: falls in correction direction after aggressive correction.
- `shimmy_induced_fall`: oscillation grows into failure.
- `authority_limited_fall`: output insufficient to get under fall.

## 6) Decision Map

- `small errors overreact + big errors underreact`:
  - check `SLEW`, `LIMITS out_max`, `MOTIONCFG`, `MOTION` before raising `kp`.
- `reversal_miss/reversal_runaway`:
  - check `SLEW`, `RAMP`, `DCFG(kaw)`, then `kd`/`kp`.
- `correction_throw`:
  - raise damping (`kd` or derivative filtering strategy) and/or reduce aggressiveness.
- persistent directional drift:
  - tune `SETPOINT`, then adaptive trim (`AUTOZERO`, `AZ*`).

## 6A) Rational Tuning Order (Default Progression)

1. Sensor/frame integrity
2. Control envelope/shapers
3. Setpoint/bias trim
4. Core `P/D`
5. Motion/recenter (`kv/kx`)
6. Integral behavior (`ki`, anti-windup details)
7. Safety threshold optimization

Backtracking policy:
- Backtrack only when new observed evidence clearly implicates a prior stage.
- Record: `reason`, `implicated stage`, `expected effect`, `re-entry stage`.
- After backtrack adjustment, re-run forward validation at least one stage ahead before new exploration.

## 7) Regression Guard

A run is regression if any of these worsen versus prior accepted baseline:
- shorter balance time,
- lower runaway trigger threshold,
- higher shimmy severity,
- new failure mode introduced.

Regression action:
1. Reapply prior accepted bundle.
2. Verify with `GET`.
3. Re-run once to confirm rollback recovery.

## 8) “New Agent” Operating Contract

The agent must always:
1. Echo active intended bundle before run.
2. Require `GET` parity confirmation.
3. Ask for missing contextual result fields after each run.
4. Propose next step from the decision map, not ad-hoc intuition.
5. Mark any uncertain run as `process_invalid_for_scoring`.
6. Show stage position (current stage + next stage) on every recommendation.
7. Explicitly state whether it is moving forward or backtracking, and why.

## 9) Minimal Run Report Template

```
Run ID:
Bundle applied:
- PID:
- SETPOINT:
- LIMITS:
- MOTION:
- SLEW:
- RAMP:
- MOTIONCFG:
- DCFG:
- AUTOZERO/AZCFG/AZFAST/AZLIMS:

Observed:
- Balance time:
- First correction direction:
- Shimmy severity:
- Failure class:
- Reversal outcome:

Decision:
- Keep / Revert / Next delta:
- Rationale:
```

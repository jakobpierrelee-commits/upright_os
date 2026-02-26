# UpRight Balancer Tuning Playbook v1.2 (Event-Valid First)

## Mission priority
1. Prove autonomous balancing behavior.
2. Ensure fall/runaway evidence is valid and coherent.
3. Tune only from valid baseline/post pairs.

## Non-negotiable gates
- Safety gates stay fail-closed.
- One variable change per tuning run.
- Reject runs labeled `invalid_window` or `bad_data_incoherent_event` from scoring.

## Event-valid workflow
1. Pre-run setup:
   - `DISARM`, `FAULTCLR`, `ESTOP 0`
   - Apply current test tune (`PID/MOTION/LIMITS`)
   - Arm burst capture in trigger-first mode.
2. Run test.
3. Record operator outcome label:
   - `fell_forward`, `fell_backward`,
   - `runaway_forward_saved`, `runaway_backward_saved`,
   - `stable_window`.
4. Validate event contract in summary:
   - `fall_detected`, `runaway_detected`, `data_coherence_ok`,
   - `invalid_window`, `bad_data_incoherent_event`.
5. Only if valid:
   - run post-change test with one bounded parameter delta.

## Trigger-first capture defaults (nano compat)
- `delay_ms=30000`
- `lines=220`
- `freq_hz=25`
- `prebuffer_lines=80`
- `trigger_angle_deg=3.0`
- `trigger_out_frac=0.35`
- `trigger_runaway=0.06`
- `post_trigger_lines=140`

## Current runtime constraints that matter
- AVR Nano flash near ceiling (very low headroom).
- ASCII low-rate telemetry path is compatibility mode; avoid architecture lock-in.
- `out_max` and output slew can limit catch-up authority during fast falls.
- If operator sees runaways/falls but logs look low-signal, treat capture as invalid and refine trigger/window before tuning.

## Practical tuning order
1. Calibration sanity (IMU/zero) and safe prearm pass.
2. Base control (`kp/kd`, minimal `ki`) before motion shaping.
3. Motion terms (`kv/kx`) once base loop can hold upright windows.
4. Authority envelope (`LIMITS`, slew implications) when catch-up is insufficient.

## High-reliability practices (aerospace-style)
- Envelope expansion: start conservative, then widen authority only with evidence.
- Test-as-you-fly discipline: use matched procedures between baseline and post-change runs.
- Single-fault mindset: treat missing/low-coherence telemetry as a fault in evidence chain, not as success.
- FDIR mindset (fault detection, isolation, recovery): log fault class, onset cues, and operator recovery action every run.
- Configuration control: promote only versioned, reproducible settings with rollback path.

## Promotion criteria for accepted tuning deltas
- Gate A valid capture.
- Matched baseline/post conditions.
- No safety regression.
- Measured lift in stability/recovery or explicit, acceptable tradeoff.

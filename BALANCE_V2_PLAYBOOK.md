# Tumbller V2 Playbook (Commissioning + App Handoff)

## Purpose
This file captures the current repeatable workflow for `tumbller_v06_nano_balance_v2` and the architecture needed to turn this into an app-driven system.

Related:
- `MISSION_ARCHITECTURE_V1.md` (target structure and rollout)
- `SESSION_FAILURE_LEARNINGS.md` (postmortem + corrective actions)

## Current Firmware + Tools
- Firmware: `/Users/jvke/Documents/UpRight.os/tumbller_v06_nano_balance_v2/tumbller_v06_nano_balance_v2.ino`
- Runner: `/Users/jvke/Documents/UpRight.os/tools/commissioning_runner.py`
- Runner config: `/Users/jvke/Documents/UpRight.os/tests/commissioning_config.json`

## Key Reality Today
- Motion control currently uses single-encoder fallback mode.
- Right encoder channel is not active in tests (`encR` remains zero).
- Use `ENCMODE LEFT` until right encoder hardware is resolved.

## Baseline Command Set (Known Safe Start)
Run in Serial Monitor (or host script):

```text
DISARM
ENCMODE LEFT
CAL ZERO
SETPOINT 0
PID 18 0 0.6
LIMITS 90 26 50
MOTION 0 0
SAVECFG
```

Verify:

```text
GET
```

Expected:
- `mode=SAFE_IDLE`
- `encmode=LEFT`
- `set=0.000`
- `kp=18.000 ki=0.000 kd=0.600`
- `kv=0.0000 kx=0.00000`
- `ang` near zero when held upright.

## Manual Test Sequence (Operator)
1. Motor path check (robot lifted):
   - `STATE SAFE`
   - `MOTOR 150 150`
   - `MOTOROFF`
2. Upright calibration:
   - Hold robot upright and still.
   - `CAL ZERO`
3. Controlled engage:
   - Hold upright.
   - `ARM`
   - confirm transition to `MODE BALANCING`.

## Commissioning Runner
Run:

```bash
cd "/Users/jvke/Documents/UpRight.os" && \
python3 tools/commissioning_runner.py \
  --port /dev/cu.usbserial-2210 \
  --config "/Users/jvke/Documents/UpRight.os/tests/commissioning_config.json" \
  --out-dir "/Users/jvke/Documents/UpRight.os/tests/results"
```

Notes:
- Close Arduino Serial Monitor before running.
- Runner now includes a dedicated motor pulse validation phase before burst capture.
- Runner supports manual prompts and fallback capture.

## Known Failure Modes
1. **MCU resets on mode engage**
   - Symptom: boot banner appears unexpectedly.
   - Likely cause: power/battery noise or serial auto-reset behavior.
2. **No CSV capture**
   - Symptom: burst returns 0 samples.
   - Use fallback capture path in runner.
3. **False drift performance failures**
   - If not actually balancing, drift metrics are meaningless.
4. **Single encoder only**
   - Position/return-to-origin loop quality is limited until right encoder is fixed.

## App Migration Architecture (Next)
Build app as supervisory layer, not hard real-time controller.

### Recommended split
- Nano: hard real-time balance + safety + command parser.
- App/ESP32/Host: UI, presets, telemetry charts, workflows.

### App command contract (minimum)
- `GET`
- `ARM`, `DISARM`
- `PID <kp> <ki> <kd>`
- `MOTION <kv> <kx>`
- `SETPOINT <deg>`
- `LIMITS <out tip iMax>`
- `CAL ZERO`
- `SAVECFG`, `LOADCFG`
- `LOGCSV 1|0`, `BURSTCSV <delay_ms> <lines>`

### App milestones
1. Baseline profile management (save/load parameter sets).
2. Guided calibration wizard (`CAL ZERO`, verify `ang` near zero).
3. Real-time telemetry pane (mode/angle/output/encoder).
4. One-click commissioning run (runner logic in app flow).
5. Safety dashboard (fault reason, estop, watchdog state).

## Definition of Done for "Repeatable Unit"
All must pass:
1. Motor preflight command works.
2. Encoder check passes (current: LEFT mode path).
3. Motor pulse validation passes (`motor_pulse_ok=1`) with measurable encoder delta.
4. Can reliably enter and hold `BALANCING` for test window.
5. Commissioning metrics pass configured thresholds.
6. Config persists across reboot (`SAVECFG` -> reboot -> `GET` confirms).

## Next Critical Engineering Task
Fix right encoder path and return to dual-encoder mode (`ENCMODE AUTO`), then retune motion loop (`kv`, `kx`) for nudge recovery + return-to-origin.

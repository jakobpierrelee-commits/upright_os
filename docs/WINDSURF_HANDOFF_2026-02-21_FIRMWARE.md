# Windsurf Firmware Handoff (2026-02-21)

## Handoff Snapshot
- Branch: `recover/uiux-restore-2026-02-19`
- Head SHA: `32dcc71`
- Working Tree: dirty (broad in-progress repo state; this pass added durable firmware templates, new firmware demos, and firmware handoff docs)

## Scope Completed
- Files changed:
  - `app/bridge/firmware_templates/README.md`
  - `app/bridge/firmware_templates/upright_mvp_baseline_v1/upright_mvp_baseline_v1.ino`
  - `app/bridge/firmware_templates/upright_mvp_baseline_v1/README.md`
  - `app/bridge/firmware_templates/upright_control_lab_v1/upright_control_lab_v1.ino`
  - `app/bridge/firmware_templates/profiled_runtime_v1/feature_profile.h`
  - `app/bridge/firmware_templates/profiled_runtime_v1/module_contracts.h`
  - `app/bridge/firmware_templates/profiled_runtime_v1/profiled_runtime_v1.ino`
  - `generated_firmware/upright_mvp_baseline_v1/upright_mvp_baseline_v1.ino`
  - `generated_firmware/upright_mvp_baseline_v1/README.md`
  - `generated_firmware/upright_control_lab_v1/upright_control_lab_v1.ino`
  - `generated_firmware/templates/profiled_runtime_v1/feature_profile.h`
  - `generated_firmware/templates/profiled_runtime_v1/module_contracts.h`
  - `generated_firmware/templates/profiled_runtime_v1/profiled_runtime_v1.ino`
  - `docs/AGENT_HANDOFF_UPRIGHT_CONTROL_LAB_V1.md`
  - `docs/FIRMWARE_PROFILES_TEMPLATE_V1.md`
- Behavior changes:
  - Added a 3-demo firmware set:
    - baseline MVP demo
    - profile/reliability architecture demo
    - advanced control-lab demo
  - Promoted these demos to durable path `app/bridge/firmware_templates/*` so they are less likely to be lost when generated outputs are cleaned.
  - Added profile/feature-flag architecture with `TEST_MINIMAL`, `LAB_FULL`, `FIELD_HARDENED`.
  - Added control-lab implementations for:
    - anti-windup
    - conditional integration
    - clamping
    - derivative LPF via cutoff
    - filter alpha telemetry
    - integral back-calculation path
    - Cohen-Coon helper command
    - transfer function print command
  - Added right encoder support on Nano classic using `D4` PCINT while keeping left on `D2` external interrupt.

## Verification
- Commands run:
  - `git -C /Users/jvke/Documents/UpRight.os branch --show-current`
  - `git -C /Users/jvke/Documents/UpRight.os rev-parse --short HEAD`
  - `git -C /Users/jvke/Documents/UpRight.os status --short`
  - `find /Users/jvke/Documents/UpRight.os/app/bridge/firmware_templates -maxdepth 3 -type f | sort`
  - `find /Users/jvke/Documents/UpRight.os/generated_firmware -maxdepth 3 -type f | rg 'upright_control_lab_v1|upright_mvp_baseline_v1|profiled_runtime_v1' | sort`
  - `rg -n "UPRIGHT_PROFILE_|FEAT_|MAX_CONTROL_STEP_US|STATUS mode=|OK HELP" /Users/jvke/Documents/UpRight.os/app/bridge/firmware_templates/profiled_runtime_v1/*`
  - `rg -n "PCINT20|STATUS mode=|OK HELP|filter_alpha|CC PID|TF controller" /Users/jvke/Documents/UpRight.os/app/bridge/firmware_templates/upright_control_lab_v1/upright_control_lab_v1.ino`
- Results:
  - All expected files exist in durable template path.
  - Commands/keys/features are present by static inspection.
  - No compile/upload/hardware-run verification performed in this pass.

## Risks / Open Issues
- New sketches are intentionally stubbed in sensor/motor sections and need hardware integration before field use.
- `String`-based command parsing is still used in demos; for hardened runtime, migrate to fixed buffers to reduce fragmentation risk on AVR.
- Working tree is broadly dirty across unrelated UI/bridge work; any commit must be path-scoped.
- Duplicate copies exist in `generated_firmware/*` and durable `app/bridge/firmware_templates/*`; treat `app/bridge/firmware_templates/*` as canonical.

## New Bench Findings (Post-Handoff)
1. Runtime ident in field test was `UPRIGHT_MVP_BASELINE_V1_1` (not older MVP).
2. `ESTOP 0` can return `ERR FAULT_LATCHED` when non-estop fault is active.
- Correct recovery flow: `FAULTCLR` -> `ESTOP 0` -> `ARM`.
3. Observed `FAULT code=13 note=encoder_stale`.
- Trigger condition in sketch: high output (`abs(out) > 70`) and no encoder edges for >500 ms.
4. Observed apparent mixed fault output:
- `FAULT code=13 note=loop_overrun`
- Root cause: prior logger printed latched code with latest note.

## Patch Applied For Fault Clarity
- Updated `latchFault()` in:
  - `app/bridge/firmware_templates/upright_mvp_baseline_v1/upright_mvp_baseline_v1.ino`
  - `generated_firmware/upright_mvp_baseline_v1/upright_mvp_baseline_v1.ino`
- New behavior:
  - first fault: `FAULT code=<latched> note=<event>`
  - subsequent faults while latched: `FAULT2 latched=<latched> code=<new> note=<event>`

## Strategy Improvements Requested (Windsurf Side)
1. Keep fault latch behavior, but improve operator diagnostics:
- Add human-readable fault label mapping in `STATUS` (e.g., `fault_name=encoder_stale`).
2. Add bench-safe mode for commissioning:
- either lower stale sensitivity or gate `encoder_stale` check behind `MODE_BALANCING && motor_enable_confirmed`.
3. Improve loop-overrun resilience:
- temporarily suspend heavy telemetry during overrun streaks, then auto-recover.
4. Preserve strict clear flow:
- `FAULTCLR` required for non-estop latched faults.

## Next Task
- Integrate real IMU + motor driver paths into `app/bridge/firmware_templates/upright_mvp_baseline_v1/upright_mvp_baseline_v1.ino` and run board compile/upload smoke test with command-contract verification (`GET/HELP/ARM/DISARM/ESTOP/PID/SETPOINT/LIMITS`).

---

## Firmware Inventory (Canonical)
1. Baseline MVP:
- `app/bridge/firmware_templates/upright_mvp_baseline_v1/upright_mvp_baseline_v1.ino`

2. Reliability/Profile Template:
- `app/bridge/firmware_templates/profiled_runtime_v1/profiled_runtime_v1.ino`
- `app/bridge/firmware_templates/profiled_runtime_v1/feature_profile.h`
- `app/bridge/firmware_templates/profiled_runtime_v1/module_contracts.h`

3. Control Lab Demo:
- `app/bridge/firmware_templates/upright_control_lab_v1/upright_control_lab_v1.ino`

4. Catalog:
- `app/bridge/firmware_templates/README.md`

## Control-Lab Feature Coverage
1. Integral windup mitigation: implemented.
2. Runtime limit adjustment: implemented (`LIMITS`).
3. Conditional integration: implemented (`FILTER` arg).
4. Clamping: implemented (output, integrator state, I-term).
5. Low-pass cutoff filter: implemented (derivative LPF).
6. Laplace-domain transfer printout: implemented (`TF`).
7. Integral feedback path: implemented (`kaw` back-calc).
8. Filter coefficient telemetry: implemented (`filter_alpha`).
9. Cohen-Coon helper: implemented (`CC K T L`).

## Right Encoder Clarification (Nano Classic)
- Left encoder reading path: `D2` via `attachInterrupt`.
- Right encoder reading path: `D4` via pin-change interrupt (`PCINT20`).
- This resolves the prior `D4` interrupt limitation when only external interrupts were used.

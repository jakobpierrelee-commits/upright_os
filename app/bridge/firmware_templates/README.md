# Firmware Templates (Durable)

This directory is the durable location for reusable starter firmware.
Use these instead of `generated_firmware/*` when you want sketches to survive generated-output cleanup.

## Available starter demos
0. `balance_mvp_v1_1_gsched/`
- Nano balancer with runtime gain scheduling command (`GSCHED`)
- Includes `tuning_seed_profiles.json` for known-good starting bundles

1. `upright_mvp_baseline_v1/`
- Minimal stable baseline demo
- Safe defaults + deterministic loop + UpRight-style command/STATUS contract

2. `profiled_runtime_v1/`
- Reliability architecture template
- Compile profiles (`TEST_MINIMAL`, `LAB_FULL`, `FIELD_HARDENED`)
- Core-vs-optional module pattern and timing budgets

3. `upright_control_lab_v1/`
- Advanced control-lab demo
- Anti-windup, conditional integration, LPF cutoff/alpha, Cohen-Coon helper, transfer function printouts

4. `teensy41_reference_v1/`
- Non-AVR reference runtime for Teensy 4.1
- Includes `runtime_manifest_v1.json` + minimal arming/telemetry command contract

## Guidance
1. Keep generated agent output under `generated_firmware/`.
2. Promote stable, user-critical starters into this folder.
3. Preserve serial command compatibility (`GET`, `HELP`, `ARM`, `DISARM`, `ESTOP`, `PID`, `SETPOINT`, etc.).
4. `FAULTCLR` is required for all production-ready sketches.
5. Tune-page controls are contractual:
- If a control exists in UI (for example `Clear Fault`), firmware must expose the matching command handler.

## Safety behavior notes
1. `profiled_runtime_v1` and `upright_mvp_baseline_v1` now use consecutive loop-overrun faulting:
- fault 11 (`FAULT_LOOP_OVERRUN`) latches after 5 consecutive overruns, not cumulative overruns across long runtime.
2. This behavior takes effect only after flashing a sketch built from the updated templates.

## Versioning policy (runtime vs tuning)
1. Treat scaffold/runtime architecture and tuning as separate version tracks.
2. `runtime_version`: bump only when structural firmware code/contract/scaffold behavior changes.
3. `tune_version`: bump for parameter/profile/tuning-only changes (`kp/ki/kd`, limits, filter cutoffs, etc.).
4. Do not bump `runtime_version` for tuning-only edits.
5. Expose both in firmware (`IDENT` and `STATUS`) so app and board can be matched exactly.
6. Source of truth is `profiled_runtime_v1/release.json`.
7. After editing `release.json`, run `python3 tools/lean/sync_release_metadata.py`.

## Nomenclature contract (enforced)
1. Sketch folder name and primary `.ino` filename must match exactly.
2. `runtime_version` in `release.json` must start with `<folder_name>.`.
3. `release_version.h` and `runtime_manifest_v1.json` release fields must match `release.json`.
4. `runtime_manifest_v1.json` field `generated_by` must equal sketch folder name.
5. Enforcement check: `tools/lean/check_sketch_nomenclature_contract.sh` (wired into clean-lane CI).

## Sketch rollback policy (major changes)
1. Do not land major runtime/scaffold changes by mutating an existing released sketch folder in place.
2. Create a new versioned sketch folder for structural changes, then promote only after acceptance gates pass.
3. Keep prior sketch folders flashable as known-good rollback targets.
4. Use:
- `tools/lean/new_sketch_version.sh --from <existing_folder> --to <new_folder> --runtime-version <new_runtime_version>`
5. For parameter-only tuning changes, keep the same sketch folder and bump `tune_version` only.

## Flash troubleshooting (Nano-class boards)
1. If upload fails with `programmer is not responding` or `not in sync`, retry with:
- `arduino:avr:nano`
- `arduino:avr:nano:cpu=atmega328old`
2. Some CH340 Nano clones require manual reset timing during upload start.

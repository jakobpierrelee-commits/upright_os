# Firmware Templates (Durable)

This directory is the durable location for reusable starter firmware.
Use these instead of `generated_firmware/*` when you want sketches to survive generated-output cleanup.

## Available starter demos
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

## Flash troubleshooting (Nano-class boards)
1. If upload fails with `programmer is not responding` or `not in sync`, retry with:
- `arduino:avr:nano`
- `arduino:avr:nano:cpu=atmega328old`
2. Some CH340 Nano clones require manual reset timing during upload start.

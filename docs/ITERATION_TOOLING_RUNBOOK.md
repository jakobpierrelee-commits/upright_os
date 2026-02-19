# Iteration Tooling Runbook

## Purpose
Use this runbook to run the new iteration tooling safely and consistently:
- Phase 1: control math parity checks
- Phase 2: trace replay regression checks
- Phase 3: hardware parameter sweep
- Phase 4: acceptance gate

## Safety Rules
- Keep robot on a safe stand or controlled test surface for sweeps.
- Be ready to physically ESTOP/disconnect power.
- Do not run sweep and other serial write tools concurrently.
- Use conservative ranges first; expand only after stable results.

## Quick Start
From repository root:

```bash
python3 scripts/iteration_tooling_gate.py
```

Expected:
- Gate should pass on non-hardware checks.
- Report written to `tests/results/iteration_tooling/phase4_gate_report.json`.

## Phase 1 Commands
Control math parity:

```bash
python3 -m pytest app/bridge/tests/test_control_math_parity.py -v
```

## Phase 2 Commands
Trace replay unit tests:

```bash
python3 -m pytest app/bridge/tests/test_trace_replay_runner.py -v
```

Run replay on known-good fixture:

```bash
python3 tools/trace_replay_runner.py \
  --input app/bridge/tests/fixtures/trace_replay_nominal.csv \
  --cmd-rmse-max 1 \
  --cmd-abs-max 3
```

Run replay on intentionally regressed fixture (expected exit code `1`):

```bash
python3 tools/trace_replay_runner.py \
  --input app/bridge/tests/fixtures/trace_replay_regressed.csv \
  --cmd-rmse-max 5 \
  --cmd-abs-max 10
```

## Phase 3 Commands
Parameter sweep dry setup (real hardware required):

```bash
python3 tools/param_sweep_runner.py \
  --port /dev/cu.usbserial-XXXX \
  --kp 31,32 \
  --ki 0.05,0.06 \
  --kd 1.0,1.2 \
  --observe-s 2 \
  --settle-s 1 \
  --max-candidates 20 \
  --output tests/results/iteration_tooling/sweep.json \
  --csv-output tests/results/iteration_tooling/sweep.csv
```

What to check:
- Console prints `BEST kp=... ki=... kd=...`.
- JSON contains `ranked_top` and `best_candidate_summary`.
- CSV contains one row per candidate with pass/fail fields.

## Phase 4 Acceptance Gate
Non-hardware gate:

```bash
python3 scripts/iteration_tooling_gate.py
```

Hardware smoke gate:

```bash
python3 scripts/iteration_tooling_gate.py \
  --with-hardware \
  --port /dev/cu.usbserial-XXXX \
  --baud 115200
```

## Output Artifacts
- Gate report JSON:
  - `tests/results/iteration_tooling/phase4_gate_report.json`
- Sweep artifacts:
  - `tests/results/iteration_tooling/*.json`
  - `tests/results/iteration_tooling/*.csv`

## Troubleshooting
- `serial_not_connected`:
  - Check cable, port, and bridge process ownership of serial device.
- `serial_busy`:
  - Stop other processes writing to the same serial port.
- Replay failures on known-good fixture:
  - Verify thresholds and fixture integrity.
- Sweep degrades stability:
  - Narrow ranges and keep rollback enabled.

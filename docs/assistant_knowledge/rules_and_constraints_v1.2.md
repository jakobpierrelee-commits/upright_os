# Rules + Constraints v1.2 (Event-Contract + Hardware Reality)

## Required telemetry for valid tuning evidence
- `mode`, `estop`
- `fault`, `fault_count`
- `ang`, `raw`, `gyro`
- `out`
- `wposRaw`, `wdelta`, `wspd`
- `kp`, `ki`, `kd`, `kv`, `kx`

## Event contract v1 interpretation
- `fall_detected`:
  - latched fault OR sustained high-angle behavior.
- `runaway_detected`:
  - sustained high output with monotonic wheel-position growth.
- `invalid_window`:
  - low-signal/no-event capture; not eligible for tuning scoring.
- `bad_data_incoherent_event`:
  - event claimed but signals do not cohere.

## Run acceptance rules
1. Reject from tuning score if:
   - `invalid_window=true`, or
   - `bad_data_incoherent_event=true`.
2. Require operator label for each run.
3. If operator label conflicts with telemetry:
   - mark run as unresolved,
   - refine capture settings first,
   - do not advance tuning score.

## Single-step delta bounds (current lane)
- PID:
  - `kp`: +/- 1.0
  - `ki`: +/- 0.02
  - `kd`: +/- 0.1
- Motion:
  - `kv`: +/- 0.05
  - `kx`: +/- 0.002
- Limits:
  - `out_max`: +/- 20
  - `tip_deg`: +/- 2

## Safety constraints
- Never disable fail-closed behavior to force pass.
- Never bypass prearm checks.
- Never apply multi-variable jumps in one run.

## Nano compatibility constraints
- Treat low-rate ASCII telemetry as temporary compatibility path.
- Keep compatibility heuristics additive and removable.
- Do not encode Nano limitations as permanent global policy.

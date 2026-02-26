# Lean Console Bootstrap

Purpose: create a stripped copy of UpRight.os focused on robot bring-up, telemetry, and safe command execution.

## Target scope (keep)
- Bridge API + serial transport:
  - `app/bridge/server.py`
  - `app/bridge/serial_gateway.py`
  - `app/bridge/firmware_templates/**`
- Minimal Ops UI:
  - one telemetry panel (status + stream)
  - one control panel (`ARM`, `DISARM`, `ESTOP`, `FAULTCLR`, `CAL ZERO`)
  - one firmware panel (compile/upload/status)
- Contract tests for required protocol keys/commands.

## Out of scope for phase 1 (defer)
- Multi-stage setup workflow gating UI.
- Non-essential docs generation flows.
- Advanced simulation/playground flows.
- Rich assistant workspace UX (tool cards, long thread history panes).

## Required command + status contract
Commands:
- `GET`, `HELP`, `ARM`, `DISARM`, `ESTOP`, `FAULTCLR`, `PID`, `SETPOINT`, `LIMITS`, `CAL ZERO`

Status keys:
- `mode`, `ang`, `raw`, `gyro`, `out`, `kp`, `ki`, `kd`, `set`

## Phase plan
1. Inventory existing UI features and map to keep/remove buckets.
2. Add a `lean mode` route/app shell that renders only minimal panels.
3. Wire compat probes to strict essentials (no MVP quota assumptions).
4. Keep current app untouched; run lean app from parallel entrypoint.
5. After stabilization, remove legacy surfaces in this repo copy.

## First acceptance criteria
- UI can connect to bridge and display live STATUS fields.
- Arm flow works when status contract is valid.
- Compat probe passes for profiled runtime v1.1 sketch.
- Upload pipeline can be run without supervisor serial race.

## Operator flow
1. Flash firmware.
2. Verify `/status` required keys.
3. `CAL ZERO` -> `FAULTCLR`.
4. `ARM` sequence.
5. Observe telemetry + issue `DISARM`/`ESTOP` safely.

## Lean mode launch
- UI toggle:
  - query param: `?lean=1`
  - env: `VITE_LEAN_CONSOLE=1`
- Example:
  - `cd app/ui/ops-console`
  - `npm install`
  - `npm run dev`
  - open `http://127.0.0.1:5173/?lean=1`

## Notes
- Keep serial supervisor off during flash operations.
- Keep this copy independent from the main repo until phase 1 passes.

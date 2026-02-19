# UpRight.os

UpRight.os is a bridge + UI + agent stack for operating and tuning self-balancing robots.

## Repo Layout
- `app/bridge` — serial bridge, safety policy, probes, API, telemetry stream, codex tools/agent.
- `app/ui/ops-console` — React operations console.
- `app/bridge/firmware_templates` — generated firmware scaffolds/contracts.
- `docs` — PRDs, contracts, runbooks, governance.
- `tools` — launchers and verification scripts.

## Prerequisites
- Python 3.11+ (tested with Python 3.14 in this workspace)
- Node.js 18+
- npm
- Optional for firmware build/upload: `arduino-cli`

## Quick Start
From repo root:

```bash
./tools/start_ops_console.sh
```

This:
1. Starts the bridge (`app/bridge/server.py`) if not already healthy.
2. Starts the ops console dev server (`app/ui/ops-console`).

Default bridge endpoint: `http://127.0.0.1:8787`

## Bridge Runtime (Direct)
If you want to run bridge manually:

```bash
cd app/bridge
python3 server.py --port /dev/cu.usbserial-2210 --baud 115200 --host 127.0.0.1 --http-port 8787 --telemetry-port 8788 --watchdog-timeout 2.0
```

Telemetry websocket:
- `ws://127.0.0.1:8788/telemetry`

## Safety Notes
- Bridge is the single authority for serial ownership.
- E-stop latching blocks risky commands.
- Arming requires a fresh heartbeat.
- Watchdog disarms on stale session while armed/balancing.

Read: `app/bridge/README.md`

## Contracts
- v1 telemetry contract remains backward-compatible.
- v2 readiness/factory-readiness is additive.

Read:
- `docs/contracts/telemetry_contract_v2.md`
- `docs/ENGINEERING_GOVERNANCE.md`

## Development Workflow
1. Update scaffold/contracts first.
2. Update bridge readiness/probes.
3. Update UI types/rendering.
4. Update agent assumptions/tools.
5. Run verification before merge.

## Verification (Required Before PR)
From repo root:

```bash
./tools/verify_all.sh
```

This runs:
- full bridge tests
- T1/T2/T3 + contract readiness suites
- frontend typecheck
- frontend codex tests

## Useful Commands
- Bridge tests:
```bash
python3 -m pytest -q app/bridge/tests
```

- UI typecheck:
```bash
cd app/ui/ops-console && npx tsc --noEmit
```

- UI tests:
```bash
cd app/ui/ops-console && npm run test
```

## Troubleshooting

### Bridge shows offline
1. Check bridge health:
```bash
curl -fsS http://127.0.0.1:8787/health
```
2. Restart launcher:
```bash
./tools/start_ops_console.sh
```
3. Inspect bridge log:
```bash
tail -n 120 .runlogs/bridge.log
```

### Serial connected but writes fail (`SERIAL_BUSY` / device not configured)
1. Ensure no other app owns the serial port (Arduino IDE serial monitor, other bridge instance).
2. Reconnect USB and restart bridge.
3. Run setup compatibility probe in UI to validate contract and link health.

### Telemetry missing while connected
1. Run compatibility probe from Setup.
2. Verify firmware emits `STATUS` keys: `mode`, `ang`, `raw`, `gyro|gyr|gx`, `out`, `kp`, `ki`, `kd`, `set`.
3. Check status freshness in diagnostics (`last_status_age_ms`).

### Codex auth error: `Failed to fetch`
1. Confirm bridge is healthy and reachable at `127.0.0.1:8787`.
2. Confirm browser/app can reach local HTTP endpoints (CORS/proxy issues).
3. Re-login after bridge restart.

### Login button disabled
Common causes:
1. Missing required auth fields in UI form.
2. Bridge/auth endpoint unavailable.
3. UI in stale state after bridge restart (refresh app once).

### Verification failures before PR
Run:
```bash
./tools/verify_all.sh
```
Then fix failing suites before opening PR.

# Bridge Failure Runbook

Purpose: recover bridge quickly without repeated trial-and-error.

## Rule: Max 2 Attempts
- Attempt `tools/restart_bridge.sh` at most **2 times**.
- If still offline after 2 attempts, stop retrying and switch to fallback path.

## Fast Path (Attempt 1, Attempt 2)
```bash
bash tools/restart_bridge.sh
curl -sS http://127.0.0.1:8787/health
```

Expected result: JSON with `"ok": true`.

## Fallback Path (After 2 failed attempts)
1. Kill stale processes:
```bash
pkill -f "tools/bridge_supervisor.sh" || true
pkill -f "app/bridge/server.py" || true
```

2. Start bridge directly in a dedicated terminal and leave it running:
```bash
python3 -u app/bridge/server.py --supervised
```

3. Verify from another terminal:
```bash
curl -sS http://127.0.0.1:8787/health
```

## Picker Route Verification (for Sketch Folder Picker)
Use this to confirm the running bridge has latest route wiring:
```bash
curl -sS -X POST http://127.0.0.1:8787/firmware/sketch-folder/pick \
  -H 'Content-Type: application/json' \
  -d '{}'
```

Interpretation:
- `{"ok":true,...}`: picker route loaded and working.
- `{"ok":false,"error":"not_found"}`: bridge runtime is stale/outdated; restart required.

## Minimal Triage Snapshot
Collect these once (do not loop endlessly):
```bash
pgrep -fal "app/bridge/server.py|bridge_supervisor.sh"
tail -n 120 .runlogs/bridge.log
tail -n 120 .runlogs/bridge-supervisor.log
```

## Known Good Recovery Pattern
- If supervisor appears to flap or health alternates up/down:
  - Stop supervisor.
  - Run bridge directly (`python3 -u app/bridge/server.py --supervised`) in one stable terminal.
  - Continue app usage in another terminal/window.

## Operator Notes
- Keep bridge and UI in separate terminals.
- If serial device is busy, close Arduino IDE / Serial Monitor before restart.
- Prefer one clean command sequence over repeated mixed restarts.

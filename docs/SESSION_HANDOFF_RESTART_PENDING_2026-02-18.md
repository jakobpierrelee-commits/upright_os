# UpRight.os Handoff (Restart Pending)

## Current Situation
- You asked to stop all terminals and relaunch clean.
- Runtime process cleanup was noisy due multiple stale interactive sessions.
- We are pausing here so you can restart Windsurf cleanly.

## What Was Implemented Right Before Pause

### 1) New Robot setup flow (full phase execution)
- Added Setup tab and made onboarding first-class in UI.
- Added detect/validate/save/activate profile flow.
- Activation is gated by validation pass.

Files:
- `app/ui/ops-console/src/App.tsx`
- `app/ui/ops-console/src/api.ts`
- `app/ui/ops-console/src/strings.ts`
- `app/ui/ops-console/src/styles.css`
- `docs/ROBOT_ONBOARDING_STANDARD.md`

### 2) Bridge robot profile APIs
- Added profile manager + persistence.
- Added endpoints:
  - `GET /profiles`
  - `POST /profiles/validate`
  - `POST /profiles/save`
  - `POST /profiles/activate`
  - `POST /profiles/delete`

File:
- `app/bridge/server.py`

### 3) Serial reliability changes
- Firmware status heartbeat is enabled (10 Hz) and includes required Kalman fields.
- Gateway falls back to cached status for short windows when `GET` fails.
- Added rugged probe script for stress checks.

Files:
- `tumbller_v06_nano_balance_v2/tumbller_v06_nano_balance_v2.ino`
- `app/bridge/serial_gateway.py`
- `app/bridge/rugged_probe.py`

## Active Issue At Pause
- Serial queue can still be overwhelmed when probes hit too often.
- Symptom in UI: Serial tail appears to freeze around `Calibrating gyro... keep still`.

Likely contributors:
- Repeated probe traffic (`/probe/compat` and related calls).
- Backlogged serial queue from earlier sessions.
- Worker needed to drain spontaneous firmware lines while idle.

## Additional Patches Applied in This Last Segment
- `useBridgePolling` now uses refs so compat probe runs once per app session, not repeatedly on rerender.
- Gateway worker now drains serial line input while idle.
- `/status` changed to cached-only (no live fallback GET).
- Telemetry websocket payload no longer issues aggressive live GET polling.
- Added server-side cache/throttle behavior for `/probe/compat` and `/probe/connect`.

Files:
- `app/ui/ops-console/src/hooks/useBridgePolling.ts`
- `app/bridge/serial_gateway.py`
- `app/bridge/server.py`

## Important Note
- The final server-side throttling patch was applied but not fully re-verified in a clean post-restart environment because session/process state was messy.

## Clean Resume Procedure (Do This First After Restart)
1. Stop all runtime processes from the IDE UI.
2. In terminal:
```bash
pkill -f "app/bridge/server.py" || true
pkill -f "npm run preview" || true
pkill -f "vite preview" || true
pkill -f "vite --host" || true
```
3. Verify clean:
```bash
lsof -iTCP:8787 -sTCP:LISTEN || true
lsof -iTCP:5173 -sTCP:LISTEN || true
lsof /dev/cu.usbserial-2210 || true
```
4. Start bridge:
```bash
cd /Users/jvke/Documents/UpRight.os
python3 app/bridge/server.py --port /dev/cu.usbserial-2210 --http-port 8787 --telemetry-port 8788
```
5. Start UI:
```bash
cd /Users/jvke/Documents/UpRight.os/app/ui/ops-console
npm run build
npm run preview -- --host 0.0.0.0 --port 5173
```

## First Validation Checklist After Restart
1. `GET /health` and `GET /status` respond.
2. Serial tab -> `Refresh Tail` returns quickly.
3. `Show Commands` returns output (or local fallback), no freeze.
4. `/diag/serial` queue depth stays bounded (does not continuously climb).
5. Setup tab runs Detect + Validation without spamming queue.

## Quick Commands
```bash
curl -sS http://127.0.0.1:8787/health | head
curl -sS http://127.0.0.1:8787/status | head
curl -sS http://127.0.0.1:8787/diag/serial | head
curl -sS "http://127.0.0.1:8787/lines?n=40"
python3 app/bridge/rugged_probe.py --seconds 15 --interval 0.3 --timeout 0.8
```

## Where To Resume
- Start by confirming queue depth behavior in `/diag/serial` while the app is idle.
- If queue still rises rapidly, temporarily disable automatic compat probe calls entirely and run probe only on manual button.

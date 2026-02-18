# Ops Console (React/Vite/TS)

## Purpose
Operational console first:
- connection health
- status telemetry (polling now, websocket next)
- two-step arm (`Prepare Arm` + `Confirm Arm`)
- latching E-Stop
- bounded tuning controls while balancing
- commissioning panel placeholder (runner remains canonical for now)
- recent serial logs

## Install
```bash
cd "/Users/jvke/Documents/UpRight.os/app/ui/ops-console"
npm install
```

## Run
```bash
npm run dev
```

Set bridge base URL if needed:
```bash
VITE_BRIDGE_BASE=http://127.0.0.1:8787 npm run dev
```

## Build
```bash
npm run build
npm run preview
```

## Notes
- Canonical bridge runtime is at `/Users/jvke/Documents/UpRight.os/app/bridge/server.py`.
- UI sends heartbeat to bridge; stale session blocks arm and can trigger auto-disarm via watchdog.
- Full commissioning orchestration endpoints will be added in the next bridge iteration.

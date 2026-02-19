# UpRight.os Fresh Start Handoff

## Current State
- UI has been simplified to an MVP focused on calibration + tuning.
- Firmware/bridge now enforce and check Kalman telemetry contract (`ang`, `raw`, `gyro|gyr|gx`).
- Bridge is patched to start without requiring device readiness.
- Browser access was unstable in dev mode, so we switched to stable preview serving.

## Key Files Changed
- `app/ui/ops-console/src/App.tsx` (MVP calibration+tuning console)
- `app/ui/ops-console/src/features/workbench/WorkbenchPanel.tsx`
- `app/ui/ops-console/src/pages/stage1/ConnectPreflightPage.tsx`
- `app/bridge/server.py` (no-device startup + safer `/status`)
- `tumbller_v06_nano_balance_v2/tumbller_v06_nano_balance_v2.ino` (`STATUS raw` + `STATUS gyro` now explicit)

## Clean Restart Commands

### 1) Stop everything
```bash
pkill -f "app/bridge/server.py" || true
pkill -f "vite --host" || true
pkill -f "vite preview" || true
```

### 2) Start bridge
```bash
cd /Users/jvke/Documents/UpRight.os
python3 app/bridge/server.py --port /dev/cu.usbserial-2210 --http-port 8787 --telemetry-port 8788
```

### 3) Start UI (stable mode)
```bash
cd /Users/jvke/Documents/UpRight.os/app/ui/ops-console
npm run build
npm run preview -- --host 0.0.0.0 --port 5173
```

### 4) Open in browser
- `http://127.0.0.1:5173/`
- `http://localhost:5173/`

## Quick Health Checks
```bash
curl -sS http://127.0.0.1:8787/health | head
curl -sS http://127.0.0.1:8787/status | head
curl -I http://127.0.0.1:5173/
```

## If Chrome Still Says “Refused to Connect”
1. Use a private/incognito window.
2. Make sure URL is `http://` not `https://`.
3. Temporarily disable VPN/proxy.
4. Try Safari once to confirm machine-level vs Chrome-level issue.

## Next Step After Fresh Open
- Run **Compat Probe** in app.
- Confirm Kalman telemetry fields present (no missing `ang/raw/gyro`).
- Continue calibration flow: `Cal Zero` -> arm/disarm safety -> PID/MOTION/SETPOINT tuning.

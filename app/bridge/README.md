# Bridge Service (Canonical Runtime)

This service is the single authority over Nano serial I/O.

## Responsibilities
- Maintain one serial session.
- Expose HTTP control endpoints.
- Expose websocket telemetry stream.
- Enforce command safety policy.
- Enforce latching E-Stop policy.
- Enforce UI heartbeat watchdog (auto-disarm on stale session during `ARMED`/`BALANCING`).

## Run
```bash
cd "/Users/jvke/Documents/UpRight.os/app/bridge"
python3 server.py --port /dev/cu.usbserial-2210 --baud 115200 --host 127.0.0.1 --http-port 8787 --telemetry-port 8788 --watchdog-timeout 2.0
```

## HTTP Endpoints
- `GET /health`
- `GET /status`
- `GET /lines?n=100`
- `POST /session/heartbeat`
- `POST /command`
- `POST /arm/prepare`
- `POST /arm/confirm`
- `POST /arm` (legacy)
- `POST /disarm`
- `POST /estop/latch`
- `POST /estop/reset`
- `POST /cal_zero`
- `POST /savecfg`
- `POST /pid`
- `POST /motion`
- `POST /setpoint`
- `POST /limits`
- `POST /commissioning/run`
- `GET /commissioning/status`
- `GET /commissioning/artifacts`
- `GET /probe/compat`

## Websocket
- `ws://127.0.0.1:8788/telemetry`

## Commissioning Ownership Rule
Because the bridge owns the serial port, `POST /commissioning/run` returns:
- `409 serial_port_in_use_by_bridge`

Use one of these patterns:
1. Stop bridge, run `tools/commissioning_runner.py` directly.
2. Implement step-mode commissioning through bridge-owned serial (future path).

## Notes
- While `estop_latched=true`, risky command traffic is blocked.
- Arming requires a fresh heartbeat via `/session/heartbeat`.
- Watchdog stale session disarms robot if mode is `ARMED` or `BALANCING`.

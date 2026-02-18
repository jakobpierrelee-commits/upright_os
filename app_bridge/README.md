# app_bridge (Compatibility Layer)

Canonical bridge runtime moved to:
- `/Users/jvke/Documents/UpRight.os/app/bridge/server.py`
- `/Users/jvke/Documents/UpRight.os/app/bridge/serial_gateway.py`

This folder remains as a compatibility shim so older commands still work.

## Canonical Run

```bash
cd "/Users/jvke/Documents/UpRight.os/app/bridge"
python3 server.py --port /dev/cu.usbserial-2210 --baud 115200 --host 127.0.0.1 --http-port 8787
```

## Legacy Run (still works)

```bash
cd "/Users/jvke/Documents/UpRight.os/app_bridge"
python3 api.py --port /dev/cu.usbserial-2210 --baud 115200 --host 127.0.0.1 --http-port 8787
```

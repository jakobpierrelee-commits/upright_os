#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request


def fetch_json(url: str, timeout: float) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Rugged serial/bridge probe for UpRight.os")
    ap.add_argument("--base", default="http://127.0.0.1:8787", help="Bridge base URL")
    ap.add_argument("--seconds", type=int, default=45, help="Total probe duration")
    ap.add_argument("--interval", type=float, default=0.25, help="Seconds between probes")
    ap.add_argument("--timeout", type=float, default=1.0, help="HTTP timeout")
    args = ap.parse_args()

    end = time.monotonic() + max(1, args.seconds)
    latencies_ms: list[float] = []
    status_ok = 0
    status_err = 0
    diag_err = 0
    last_diag: dict | None = None
    last_print = 0.0

    while time.monotonic() < end:
        started = time.monotonic()
        try:
            payload = fetch_json(f"{args.base}/status", timeout=args.timeout)
            _ = payload.get("status", {})
            status_ok += 1
            latencies_ms.append((time.monotonic() - started) * 1000.0)
        except Exception:
            status_err += 1

        try:
            last_diag = fetch_json(f"{args.base}/diag/serial", timeout=args.timeout)
        except Exception:
            diag_err += 1

        now = time.monotonic()
        if now - last_print >= 1.0:
            last_print = now
            p50 = statistics.median(latencies_ms) if latencies_ms else 0.0
            p95 = sorted(latencies_ms)[int(len(latencies_ms) * 0.95)] if latencies_ms else 0.0
            queue_depth = (
                ((last_diag or {}).get("serial") or {}).get("queue_depth")
                if isinstance(last_diag, dict)
                else None
            )
            print(
                f"ok={status_ok} err={status_err} diag_err={diag_err} "
                f"lat_ms_p50={p50:.1f} lat_ms_p95={p95:.1f} queue={queue_depth}"
            )

        sleep_for = args.interval - (time.monotonic() - started)
        if sleep_for > 0:
            time.sleep(sleep_for)

    p50 = statistics.median(latencies_ms) if latencies_ms else 0.0
    p95 = sorted(latencies_ms)[int(len(latencies_ms) * 0.95)] if latencies_ms else 0.0
    print("\nFinal:")
    print(f"status_ok={status_ok} status_err={status_err} diag_err={diag_err}")
    print(f"status_latency_ms_p50={p50:.1f} status_latency_ms_p95={p95:.1f}")
    if isinstance(last_diag, dict):
        serial = (last_diag.get("serial") or {})
        metrics = (serial.get("serial_metrics") or {})
        print(
            "serial_metrics:"
            f" connected={serial.get('connected')}"
            f" worker_alive={serial.get('worker_alive')}"
            f" queue_depth={serial.get('queue_depth')}"
            f" status_age_ms={serial.get('last_status_age_ms')}"
            f" ok={metrics.get('commands_ok')}"
            f" err={metrics.get('commands_err')}"
            f" timeouts={metrics.get('timeouts')}"
            f" p50={metrics.get('latency_p50_ms')}"
            f" p95={metrics.get('latency_p95_ms')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

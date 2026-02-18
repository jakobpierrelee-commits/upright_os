#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

try:
    import websockets
except Exception:
    websockets = None

try:
    from app.bridge.serial_gateway import NanoSerialGateway
except ImportError:
    from serial_gateway import NanoSerialGateway


class BridgeControlState:
    def __init__(self, watchdog_timeout_s: float = 2.0) -> None:
        self._lock = threading.Lock()
        self.arm_prepared = False
        self.estop_latched = False
        self._heartbeat_ts: Optional[float] = None
        self.watchdog_timeout_s = watchdog_timeout_s
        self._watchdog_tripped = False
        self.watchdog_disarm_count = 0
        self.watchdog_last_reason = ""

    def _heartbeat_age_s_unlocked(self) -> Optional[float]:
        if self._heartbeat_ts is None:
            return None
        return max(0.0, time.monotonic() - self._heartbeat_ts)

    def _snapshot_unlocked(self) -> Dict[str, Any]:
        return {
            "arm_prepared": self.arm_prepared,
            "estop_latched": self.estop_latched,
            "heartbeat_age_s": self._heartbeat_age_s_unlocked(),
            "watchdog_timeout_s": self.watchdog_timeout_s,
            "watchdog_tripped": self._watchdog_tripped,
            "watchdog_disarm_count": self.watchdog_disarm_count,
            "watchdog_last_reason": self.watchdog_last_reason,
        }

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return self._snapshot_unlocked()

    def heartbeat(self) -> Dict[str, Any]:
        with self._lock:
            self._heartbeat_ts = time.monotonic()
            self._watchdog_tripped = False
            return self._snapshot_unlocked()

    def session_fresh(self) -> bool:
        with self._lock:
            age = self._heartbeat_age_s_unlocked()
            return age is not None and age <= self.watchdog_timeout_s

    def prepare_arm(self) -> Dict[str, Any]:
        with self._lock:
            if self.estop_latched:
                raise RuntimeError("estop_latched")
            self.arm_prepared = True
            return self._snapshot_unlocked()

    def consume_arm_prepare(self) -> Dict[str, Any]:
        with self._lock:
            if self.estop_latched:
                raise RuntimeError("estop_latched")
            if not self.arm_prepared:
                raise RuntimeError("arm_not_prepared")
            self.arm_prepared = False
            return self._snapshot_unlocked()

    def clear_arm_prepare(self) -> Dict[str, Any]:
        with self._lock:
            self.arm_prepared = False
            return self._snapshot_unlocked()

    def latch_estop(self) -> Dict[str, Any]:
        with self._lock:
            self.estop_latched = True
            self.arm_prepared = False
            return self._snapshot_unlocked()

    def reset_estop(self) -> Dict[str, Any]:
        with self._lock:
            self.estop_latched = False
            self.arm_prepared = False
            return self._snapshot_unlocked()

    def check_and_trip_watchdog(self) -> bool:
        with self._lock:
            if self.estop_latched:
                return False
            age = self._heartbeat_age_s_unlocked()
            if age is None or age <= self.watchdog_timeout_s:
                return False
            if self._watchdog_tripped:
                return False
            self._watchdog_tripped = True
            return True

    def record_watchdog_disarm(self, reason: str) -> Dict[str, Any]:
        with self._lock:
            self.arm_prepared = False
            self.watchdog_disarm_count += 1
            self.watchdog_last_reason = reason
            return self._snapshot_unlocked()


class CommissioningManager:
    def __init__(self, repo_root: pathlib.Path, default_port: str, default_baud: int) -> None:
        self.repo_root = repo_root
        self.default_port = default_port
        self.default_baud = default_baud
        self.default_config = repo_root / "tests" / "commissioning_config.json"
        self.default_out_dir = repo_root / "tests" / "results"
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._state = "idle"
        self._started_at: Optional[float] = None
        self._finished_at: Optional[float] = None
        self._returncode: Optional[int] = None
        self._log: list[str] = []
        self._last_cmd: list[str] = []

    def _set(self, **kwargs: Any) -> None:
        with self._lock:
            for k, v in kwargs.items():
                setattr(self, k, v)

    def _append_log(self, line: str) -> None:
        with self._lock:
            self._log.append(line)
            self._log = self._log[-500:]

    def run(self, *, port: Optional[str] = None, baud: Optional[int] = None, config: Optional[str] = None, out_dir: Optional[str] = None, auto_prompts: bool = True) -> Dict[str, Any]:
        with self._lock:
            if self._running:
                raise RuntimeError("commissioning_running")
            self._running = True
            self._state = "running"
            self._started_at = time.time()
            self._finished_at = None
            self._returncode = None
            self._log = []

        p = port or self.default_port
        b = str(baud or self.default_baud)
        c = config or str(self.default_config)
        o = out_dir or str(self.default_out_dir)
        cmd = [
            "python3",
            str(self.repo_root / "tools" / "commissioning_runner.py"),
            "--port",
            p,
            "--baud",
            b,
            "--config",
            c,
            "--out-dir",
            o,
        ]
        if auto_prompts:
            cmd.append("--auto-prompts")
        self._set(_last_cmd=cmd)

        def worker() -> None:
            rc = -1
            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(self.repo_root),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                assert proc.stdout is not None
                for ln in proc.stdout:
                    self._append_log(ln.rstrip())
                rc = proc.wait()
            except Exception as exc:
                self._append_log(f"ERROR: {exc}")
            finally:
                self._set(
                    _running=False,
                    _state="passed" if rc == 0 else "failed",
                    _finished_at=time.time(),
                    _returncode=rc,
                )

        t = threading.Thread(target=worker, daemon=True)
        self._set(_thread=t)
        t.start()
        return self.status()

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "state": self._state,
                "running": self._running,
                "started_at": self._started_at,
                "finished_at": self._finished_at,
                "returncode": self._returncode,
                "last_cmd": self._last_cmd,
                "log_tail": self._log[-120:],
            }

    def artifacts(self, out_dir: Optional[str] = None) -> Dict[str, Any]:
        target = pathlib.Path(out_dir) if out_dir else self.default_out_dir
        metrics = sorted(target.glob("metrics_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        runs = sorted(target.glob("run_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
        return {
            "out_dir": str(target),
            "latest_metrics": str(metrics[0]) if metrics else None,
            "latest_run": str(runs[0]) if runs else None,
            "metrics": [str(p) for p in metrics[:20]],
            "runs": [str(p) for p in runs[:20]],
        }


class TelemetryHub:
    def __init__(self, gateway: NanoSerialGateway, control: BridgeControlState, host: str, port: int) -> None:
        self.gateway = gateway
        self.control = control
        self.host = host
        self.port = port
        self.enabled = websockets is not None
        self._stop_evt = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if not self.enabled:
            return
        self._thread = threading.Thread(target=self._run_thread, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_evt.set()

    def _run_thread(self) -> None:
        asyncio.run(self._run_async())

    async def _run_async(self) -> None:
        clients: set[Any] = set()

        async def handler(ws):
            clients.add(ws)
            try:
                while not self._stop_evt.is_set():
                    await asyncio.sleep(0.5)
            finally:
                clients.discard(ws)

        async with websockets.serve(handler, self.host, self.port):
            while not self._stop_evt.is_set():
                payload = {
                    "ts": time.time(),
                    "status": {},
                    "control": self.control.snapshot(),
                }
                try:
                    payload["status"] = self.gateway.get_status()
                except Exception as exc:
                    payload["error"] = str(exc)

                if clients:
                    msg = json.dumps(payload)
                    dead = []
                    for ws in list(clients):
                        try:
                            await ws.send(msg)
                        except Exception:
                            dead.append(ws)
                    for ws in dead:
                        clients.discard(ws)
                await asyncio.sleep(0.05)


def _json(handler: BaseHTTPRequestHandler, code: int, body: Dict[str, Any]) -> None:
    payload = json.dumps(body).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(payload)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    handler.end_headers()
    handler.wfile.write(payload)


def _read_json(handler: BaseHTTPRequestHandler) -> Dict[str, Any]:
    n = int(handler.headers.get("Content-Length", "0"))
    if n <= 0:
        return {}
    raw = handler.rfile.read(n)
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _normalize_cmd(cmd: str) -> str:
    return " ".join(cmd.strip().split()).upper()


def _blocked_while_latched(cmd: str) -> bool:
    c = _normalize_cmd(cmd)
    safe_prefixes = ("GET", "DISARM", "HELP", "LOGCSV", "LOGT")
    return not c.startswith(safe_prefixes)


def build_handler(gateway: NanoSerialGateway, control: BridgeControlState, commissioning: CommissioningManager, telemetry_port: int):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def do_OPTIONS(self) -> None:
            _json(self, 200, {"ok": True})

        def do_GET(self) -> None:
            try:
                u = urlparse(self.path)
                if u.path == "/health":
                    return _json(
                        self,
                        200,
                        {
                            "ok": True,
                            "health": gateway.health(),
                            "control": control.snapshot(),
                            "telemetry_ws": f"ws://127.0.0.1:{telemetry_port}/telemetry",
                            "telemetry_enabled": websockets is not None,
                        },
                    )
                if u.path == "/status":
                    return _json(self, 200, {"ok": True, "status": gateway.get_status(), "control": control.snapshot()})
                if u.path == "/lines":
                    q = parse_qs(u.query)
                    n = int(q.get("n", ["100"])[0])
                    return _json(self, 200, {"ok": True, "lines": gateway.recent_lines(n)})
                if u.path == "/commissioning/status":
                    return _json(self, 200, {"ok": True, "commissioning": commissioning.status()})
                if u.path == "/commissioning/artifacts":
                    return _json(self, 200, {"ok": True, "artifacts": commissioning.artifacts()})
                return _json(self, 404, {"ok": False, "error": "not_found"})
            except Exception as exc:
                return _json(self, 500, {"ok": False, "error": str(exc)})

        def do_POST(self) -> None:
            try:
                u = urlparse(self.path)
                body = _read_json(self)

                if u.path == "/session/heartbeat":
                    return _json(self, 200, {"ok": True, "control": control.heartbeat()})

                if u.path == "/commissioning/run":
                    if gateway.health().get("connected", False):
                        return _json(self, 409, {"ok": False, "error": "serial_port_in_use_by_bridge", "hint": "Run commissioning_runner.py directly when bridge is stopped, or add step-mode commissioning through the bridge."})
                    st = commissioning.run(
                        port=body.get("port"),
                        baud=body.get("baud"),
                        config=body.get("config"),
                        out_dir=body.get("out_dir"),
                        auto_prompts=bool(body.get("auto_prompts", True)),
                    )
                    return _json(self, 200, {"ok": True, "commissioning": st})

                if u.path == "/commissioning/step":
                    return _json(self, 501, {"ok": False, "error": "not_implemented", "hint": "Use /commissioning/run for now"})

                if u.path == "/command":
                    cmd = str(body.get("cmd", "")).strip()
                    if not cmd:
                        return _json(self, 400, {"ok": False, "error": "missing cmd"})
                    if control.snapshot()["estop_latched"] and _blocked_while_latched(cmd):
                        return _json(self, 423, {"ok": False, "error": "estop_latched", "control": control.snapshot()})
                    expect = body.get("expect")
                    timeout = float(body.get("timeout", 2.0))
                    res = gateway.command(cmd, expect_contains=str(expect), timeout=timeout) if expect else gateway.command(cmd, timeout=timeout)
                    return _json(self, 200, {"ok": True, "result": res, "control": control.snapshot()})

                if u.path == "/arm/prepare":
                    if not control.session_fresh():
                        return _json(self, 428, {"ok": False, "error": "session_stale", "control": control.snapshot()})
                    return _json(self, 200, {"ok": True, "control": control.prepare_arm()})

                if u.path == "/arm/confirm":
                    if not control.session_fresh():
                        return _json(self, 428, {"ok": False, "error": "session_stale", "control": control.snapshot()})
                    control.consume_arm_prepare()
                    gateway.command("ARM", timeout=1.0)
                    return _json(self, 200, {"ok": True, "status": gateway.get_status(), "control": control.snapshot()})

                if u.path == "/arm":
                    if not control.session_fresh():
                        return _json(self, 428, {"ok": False, "error": "session_stale", "control": control.snapshot()})
                    if control.snapshot()["estop_latched"]:
                        return _json(self, 423, {"ok": False, "error": "estop_latched", "control": control.snapshot()})
                    gateway.command("ARM", timeout=1.0)
                    control.clear_arm_prepare()
                    return _json(self, 200, {"ok": True, "status": gateway.get_status(), "control": control.snapshot()})

                if u.path == "/disarm":
                    gateway.command("DISARM", timeout=1.0)
                    control.clear_arm_prepare()
                    return _json(self, 200, {"ok": True, "status": gateway.get_status(), "control": control.snapshot()})

                if u.path == "/estop/latch":
                    gateway.command("DISARM", timeout=1.0)
                    return _json(self, 200, {"ok": True, "status": gateway.get_status(), "control": control.latch_estop()})

                if u.path == "/estop/reset":
                    gateway.command("DISARM", timeout=1.0)
                    return _json(self, 200, {"ok": True, "status": gateway.get_status(), "control": control.reset_estop()})

                if u.path == "/cal_zero":
                    if control.snapshot()["estop_latched"]:
                        return _json(self, 423, {"ok": False, "error": "estop_latched", "control": control.snapshot()})
                    res = gateway.command("CAL ZERO", expect_contains="OK CAL ZERO", timeout=4.0)
                    return _json(self, 200, {"ok": True, "result": res, "status": gateway.get_status(), "control": control.snapshot()})

                if u.path == "/savecfg":
                    res = gateway.command("SAVECFG", expect_contains="OK SAVECFG", timeout=2.0)
                    return _json(self, 200, {"ok": True, "result": res, "control": control.snapshot()})

                if u.path == "/pid":
                    kp = float(body["kp"])
                    ki = float(body["ki"])
                    kd = float(body["kd"])
                    res = gateway.command(f"PID {kp} {ki} {kd}", expect_contains="OK PID", timeout=2.0)
                    return _json(self, 200, {"ok": True, "result": res, "status": gateway.get_status(), "control": control.snapshot()})

                if u.path == "/motion":
                    kv = float(body["kv"])
                    kx = float(body["kx"])
                    res = gateway.command(f"MOTION {kv} {kx}", expect_contains="OK MOTION", timeout=2.0)
                    return _json(self, 200, {"ok": True, "result": res, "status": gateway.get_status(), "control": control.snapshot()})

                if u.path == "/setpoint":
                    deg = float(body["deg"])
                    res = gateway.command(f"SETPOINT {deg}", expect_contains="OK SETPOINT", timeout=2.0)
                    return _json(self, 200, {"ok": True, "result": res, "status": gateway.get_status(), "control": control.snapshot()})

                if u.path == "/limits":
                    out_max = float(body["out_max"])
                    tip_deg = float(body["tip_deg"])
                    i_max = float(body["i_max"])
                    res = gateway.command(f"LIMITS {out_max} {tip_deg} {i_max}", expect_contains="OK LIMITS", timeout=2.0)
                    return _json(self, 200, {"ok": True, "result": res, "status": gateway.get_status(), "control": control.snapshot()})

                return _json(self, 404, {"ok": False, "error": "not_found"})
            except KeyError as exc:
                return _json(self, 400, {"ok": False, "error": f"missing field: {exc}"})
            except RuntimeError as exc:
                msg = str(exc)
                if msg in {"estop_latched", "session_stale"}:
                    return _json(self, 423, {"ok": False, "error": msg, "control": control.snapshot()})
                if msg == "arm_not_prepared":
                    return _json(self, 409, {"ok": False, "error": msg, "control": control.snapshot()})
                if msg == "commissioning_running":
                    return _json(self, 409, {"ok": False, "error": msg, "commissioning": commissioning.status()})
                return _json(self, 500, {"ok": False, "error": msg})
            except Exception as exc:
                return _json(self, 500, {"ok": False, "error": str(exc)})

    return Handler


def watchdog_loop(gateway: NanoSerialGateway, control: BridgeControlState, stop_evt: threading.Event) -> None:
    while not stop_evt.wait(0.1):
        try:
            if not control.check_and_trip_watchdog():
                continue
            status = gateway.get_status()
            mode = str(status.get("mode", "UNKNOWN"))
            if mode in {"BALANCING", "ARMED"}:
                gateway.command("DISARM", timeout=1.0)
                control.record_watchdog_disarm(f"heartbeat_timeout:{mode}")
        except Exception:
            continue


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default=os.environ.get("NANO_PORT", "/dev/cu.usbserial-2210"))
    ap.add_argument("--baud", type=int, default=int(os.environ.get("NANO_BAUD", "115200")))
    ap.add_argument("--host", default=os.environ.get("APP_BRIDGE_HOST", "127.0.0.1"))
    ap.add_argument("--http-port", type=int, default=int(os.environ.get("APP_BRIDGE_PORT", "8787")))
    ap.add_argument("--telemetry-port", type=int, default=int(os.environ.get("APP_TELEMETRY_PORT", "8788")))
    ap.add_argument("--watchdog-timeout", type=float, default=float(os.environ.get("APP_WATCHDOG_TIMEOUT_S", "2.0")))
    args = ap.parse_args()

    repo_root = pathlib.Path(__file__).resolve().parents[2]
    gw = NanoSerialGateway(args.port, args.baud)
    gw.connect()
    ready = gw.wait_ready(timeout=20.0)
    control = BridgeControlState(watchdog_timeout_s=max(0.5, args.watchdog_timeout))
    commissioning = CommissioningManager(repo_root, args.port, args.baud)
    telemetry = TelemetryHub(gw, control, args.host, args.telemetry_port)
    telemetry.start()

    print(f"bridge connected: {args.port} @ {args.baud}")
    print(f"initial status: {ready}")
    print(f"telemetry websocket: ws://{args.host}:{args.telemetry_port}/telemetry enabled={websockets is not None}")

    stop_evt = threading.Event()
    wd = threading.Thread(target=watchdog_loop, args=(gw, control, stop_evt), daemon=True)
    wd.start()

    server = ThreadingHTTPServer((args.host, args.http_port), build_handler(gw, control, commissioning, args.telemetry_port))
    print(f"bridge listening on http://{args.host}:{args.http_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_evt.set()
        telemetry.stop()
        server.server_close()
        gw.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

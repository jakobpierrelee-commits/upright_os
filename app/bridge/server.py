#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import hmac
import json
import os
import pathlib
import shutil
import sqlite3
import subprocess
import secrets
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse
from urllib import error as urlerror
from urllib import request as urlrequest

try:
    import websockets
except Exception:
    websockets = None

try:
    import certifi
except Exception:
    certifi = None

try:
    from serial.tools import list_ports
except Exception:
    list_ports = None

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


class FirmwareManager:
    def __init__(self, repo_root: pathlib.Path, default_port: str) -> None:
        self.repo_root = repo_root
        self.default_port = default_port
        self.default_sketch = repo_root / "tumbller_v06_nano_balance_v2"
        self.default_fqbn = "arduino:avr:nano"
        self.arduino_cli = self._resolve_arduino_cli()
        self._lock = threading.Lock()
        self._running = False
        self._state = "idle"
        self._phase = "none"
        self._started_at: Optional[float] = None
        self._finished_at: Optional[float] = None
        self._returncode: Optional[int] = None
        self._log: list[str] = []
        self._last_cmd: list[str] = []

    def _resolve_arduino_cli(self) -> str:
        env_override = os.environ.get("ARDUINO_CLI_BIN", "").strip()
        candidates = [env_override] if env_override else []
        candidates.extend(
            [
                shutil.which("arduino-cli") or "",
                str(pathlib.Path.home() / ".local" / "bin" / "arduino-cli"),
                "/opt/homebrew/bin/arduino-cli",
                "/usr/local/bin/arduino-cli",
            ]
        )
        for c in candidates:
            if not c:
                continue
            p = pathlib.Path(c).expanduser()
            if p.exists() and p.is_file():
                return str(p)
        return "arduino-cli"

    def _set(self, **kwargs: Any) -> None:
        with self._lock:
            for k, v in kwargs.items():
                setattr(self, k, v)

    def _append_log(self, line: str) -> None:
        with self._lock:
            self._log.append(line)
            self._log = self._log[-500:]

    def _run_subprocess(self, cmd: list[str], *, phase: str) -> Dict[str, Any]:
        with self._lock:
            if self._running:
                raise RuntimeError("firmware_running")
            self._running = True
            self._state = "running"
            self._phase = phase
            self._started_at = time.time()
            self._finished_at = None
            self._returncode = None
            self._log = []
            self._last_cmd = cmd

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
        t.start()
        return self.status()

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "state": self._state,
                "phase": self._phase,
                "running": self._running,
                "started_at": self._started_at,
                "finished_at": self._finished_at,
                "returncode": self._returncode,
                "last_cmd": self._last_cmd,
                "log_tail": self._log[-120:],
                "defaults": {
                    "sketch": str(self.default_sketch),
                    "fqbn": self.default_fqbn,
                    "port": self.default_port,
                },
            }

    def check(self) -> Dict[str, Any]:
        self.arduino_cli = self._resolve_arduino_cli()
        cmd = [self.arduino_cli, "board", "list", "--format", "json"]
        try:
            version = subprocess.check_output([self.arduino_cli, "version"], text=True, cwd=str(self.repo_root), stderr=subprocess.STDOUT).strip()
            listing = subprocess.check_output(cmd, text=True, cwd=str(self.repo_root), stderr=subprocess.STDOUT).strip()
            parsed = json.loads(listing) if listing else {}
            ports = parsed.get("detected_ports", []) if isinstance(parsed, dict) else []
            return {
                "ok": True,
                "version": version,
                "binary": self.arduino_cli,
                "detected_ports": ports,
                "raw": parsed,
            }
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc),
                "hint": "Install arduino-cli, then retry check.",
                "install_suggestion": "Use UI button 'Install Arduino CLI' or run: curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | BINDIR=$HOME/.local/bin sh",
            }

    def compile(self, *, sketch: Optional[str] = None, fqbn: Optional[str] = None) -> Dict[str, Any]:
        self.arduino_cli = self._resolve_arduino_cli()
        sketch_path = sketch or str(self.default_sketch)
        board = fqbn or self.default_fqbn
        cmd = [self.arduino_cli, "compile", "--fqbn", board, sketch_path]
        return self._run_subprocess(cmd, phase="compile")

    def upload(self, *, sketch: Optional[str] = None, fqbn: Optional[str] = None, port: Optional[str] = None) -> Dict[str, Any]:
        self.arduino_cli = self._resolve_arduino_cli()
        sketch_path = sketch or str(self.default_sketch)
        board = fqbn or self.default_fqbn
        upload_port = port or self.default_port
        cmd = [self.arduino_cli, "upload", "-p", upload_port, "--fqbn", board, sketch_path]
        return self._run_subprocess(cmd, phase="upload")

    def upload_guarded(
        self,
        *,
        gateway: NanoSerialGateway,
        sketch: Optional[str] = None,
        fqbn: Optional[str] = None,
        port: Optional[str] = None,
    ) -> Dict[str, Any]:
        self.arduino_cli = self._resolve_arduino_cli()
        sketch_path = sketch or str(self.default_sketch)
        board = fqbn or self.default_fqbn
        upload_port = port or self.default_port
        cmd = [self.arduino_cli, "upload", "-p", upload_port, "--fqbn", board, sketch_path]

        with self._lock:
            if self._running:
                raise RuntimeError("firmware_running")
            self._running = True
            self._state = "running"
            self._phase = "upload_guarded"
            self._started_at = time.time()
            self._finished_at = None
            self._returncode = None
            self._log = []
            self._last_cmd = cmd

        def worker() -> None:
            rc = -1
            reconnect_ok = False
            try:
                self._append_log("guarded flash: disarm -> close serial -> upload -> reconnect")
                try:
                    gateway.command("DISARM", timeout=1.0)
                    self._append_log("disarm command sent")
                except Exception as exc:
                    self._append_log(f"warn: disarm failed ({exc})")

                gateway.close()
                self._append_log("serial bridge closed for flashing")

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
                self._append_log(f"upload return code={rc}")
            except Exception as exc:
                self._append_log(f"ERROR: guarded upload failed: {exc}")
            finally:
                try:
                    gateway.connect()
                    ready = gateway.wait_ready(timeout=10.0)
                    reconnect_ok = True
                    self._append_log(f"bridge reconnected: mode={ready.get('mode', 'UNKNOWN')}")
                except Exception as exc:
                    self._append_log(f"ERROR: reconnect failed: {exc}")

                final_pass = rc == 0 and reconnect_ok
                self._set(
                    _running=False,
                    _state="passed" if final_pass else "failed",
                    _finished_at=time.time(),
                    _returncode=0 if final_pass else (rc if rc != 0 else -2),
                )

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        return self.status()

    def install_cli(self) -> Dict[str, Any]:
        script = r"""
set -euo pipefail
if command -v arduino-cli >/dev/null 2>&1; then
  echo "arduino-cli already installed: $(arduino-cli version)"
  exit 0
fi
OS="$(uname -s)"
ARCH="$(uname -m)"
TARGET=""
if [ "$OS" = "Darwin" ] && [ "$ARCH" = "arm64" ]; then
  TARGET="macOS_ARM64"
elif [ "$OS" = "Darwin" ] && [ "$ARCH" = "x86_64" ]; then
  TARGET="macOS_64bit"
elif [ "$OS" = "Linux" ] && [ "$ARCH" = "x86_64" ]; then
  TARGET="Linux_64bit"
elif [ "$OS" = "Linux" ] && [ "$ARCH" = "aarch64" ]; then
  TARGET="Linux_ARM64"
else
  echo "Unsupported platform for auto-install: $OS $ARCH"
  exit 2
fi
VER="$(curl -fsSL https://api.github.com/repos/arduino/arduino-cli/releases/latest | python3 -c 'import sys,json; print(json.load(sys.stdin)["tag_name"].lstrip("v"))')"
URL="https://downloads.arduino.cc/arduino-cli/arduino-cli_${VER}_${TARGET}.tar.gz"
echo "Installing arduino-cli ${VER} for ${TARGET}"
mkdir -p "$HOME/.local/bin"
TMPD="$(mktemp -d)"
trap 'rm -rf "$TMPD"' EXIT
cd "$TMPD"
curl -fL "$URL" -o arduino-cli.tar.gz
tar -xzf arduino-cli.tar.gz
install -m 0755 arduino-cli "$HOME/.local/bin/arduino-cli"
echo "Installed at $HOME/.local/bin/arduino-cli"
"$HOME/.local/bin/arduino-cli" version
"""
        cmd = ["/bin/bash", "-lc", script]
        self.arduino_cli = self._resolve_arduino_cli()
        return self._run_subprocess(cmd, phase="install_cli")

    def _default_sketch_file(self) -> pathlib.Path:
        folder = pathlib.Path(self.default_sketch)
        preferred = folder / f"{folder.name}.ino"
        if preferred.exists():
            return preferred
        ino_files = sorted(folder.glob("*.ino"))
        if not ino_files:
            raise FileNotFoundError(f"No .ino file found in {folder}")
        return ino_files[0]

    def read_sketch(self, path: Optional[str] = None) -> Dict[str, Any]:
        target = pathlib.Path(path) if path else self._default_sketch_file()
        if not target.exists() or not target.is_file():
            raise FileNotFoundError(str(target))
        content = target.read_text(encoding="utf-8")
        return {"path": str(target), "content": content}

    def write_sketch(self, *, content: str, path: Optional[str] = None) -> Dict[str, Any]:
        target = pathlib.Path(path) if path else self._default_sketch_file()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"path": str(target), "bytes": len(content.encode("utf-8"))}

    def list_boards(self) -> Dict[str, Any]:
        self.arduino_cli = self._resolve_arduino_cli()
        cmd = [self.arduino_cli, "board", "list", "--format", "json"]
        try:
            raw = subprocess.check_output(cmd, text=True, cwd=str(self.repo_root), stderr=subprocess.STDOUT).strip()
            parsed = json.loads(raw) if raw else {}
            detected_ports = parsed.get("detected_ports", []) if isinstance(parsed, dict) else []
            simplified = []
            for p in detected_ports:
                addr = p.get("port", {}).get("address")
                label = p.get("port", {}).get("label")
                protocol = p.get("port", {}).get("protocol")
                boards = p.get("matching_boards", []) or []
                fqbn = boards[0].get("fqbn") if boards else None
                name = boards[0].get("name") if boards else None
                simplified.append(
                    {
                        "address": addr,
                        "label": label,
                        "protocol": protocol,
                        "fqbn": fqbn,
                        "board_name": name,
                    }
                )
            recommended = next((p for p in simplified if p.get("fqbn")), None)
            return {
                "ok": True,
                "ports": simplified,
                "recommended_fqbn": recommended.get("fqbn") if recommended else self.default_fqbn,
                "recommended_port": recommended.get("address") if recommended else self.default_port,
                "raw": parsed,
            }
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc),
                "ports": [],
                "recommended_fqbn": self.default_fqbn,
                "recommended_port": self.default_port,
            }


class AIManager:
    def __init__(self) -> None:
        self.default_api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        self.default_model = os.environ.get("OPENAI_MODEL", "gpt-5-mini")
        self.base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.ssl_context = self._build_ssl_context()
        self._lock = threading.Lock()
        self._history: Dict[str, list[Dict[str, Any]]] = {}

    @staticmethod
    def _build_ssl_context() -> ssl.SSLContext:
        # Allow explicit override if the host needs a custom CA bundle.
        ca_bundle = os.environ.get("OPENAI_CA_BUNDLE", "").strip()
        if ca_bundle:
            return ssl.create_default_context(cafile=ca_bundle)
        if certifi is not None:
            return ssl.create_default_context(cafile=certifi.where())
        return ssl.create_default_context()

    def _append(self, session_key: str, role: str, text: str) -> None:
        with self._lock:
            bucket = self._history.setdefault(session_key, [])
            bucket.append({"ts": time.time(), "role": role, "text": text})
            self._history[session_key] = bucket[-80:]

    def status(self, *, configured: bool, model: str, session_key: str) -> Dict[str, Any]:
        with self._lock:
            hlen = len(self._history.get(session_key, []))
        return {"configured": configured, "model": model, "history_len": hlen}

    def history(self, session_key: str) -> list[Dict[str, Any]]:
        with self._lock:
            return list(self._history.get(session_key, []))

    @staticmethod
    def _extract_output_text(resp: Dict[str, Any]) -> str:
        out = []
        if isinstance(resp.get("output_text"), str) and resp.get("output_text"):
            out.append(resp["output_text"])
        for item in resp.get("output", []) or []:
            for c in item.get("content", []) or []:
                t = c.get("text")
                if isinstance(t, str) and t:
                    out.append(t)
        return "\n".join([x for x in out if x]).strip()

    def chat(self, *, message: str, context: Dict[str, Any], session_key: str, api_key: str, model: str) -> Dict[str, Any]:
        if not api_key:
            raise RuntimeError("openai_api_key_missing")
        user_msg = message.strip()
        if not user_msg:
            raise RuntimeError("empty_message")

        context_blob = json.dumps(context, separators=(",", ":"), ensure_ascii=True)
        system_prompt = (
            "You are Codex for UpRight.os, a robotics tuning copilot. "
            "Be concise, practical, and safe. Never claim actions already executed unless tool output confirms it. "
            "Prefer explicit next commands and safety checks."
        )

        payload = {
            "model": model,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
                {"role": "system", "content": [{"type": "input_text", "text": f"live_context={context_blob}"}]},
                {"role": "user", "content": [{"type": "input_text", "text": user_msg}]},
            ],
        }
        data = json.dumps(payload).encode("utf-8")
        req = urlrequest.Request(
            f"{self.base_url.rstrip('/')}/responses",
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        try:
            with urlrequest.urlopen(req, timeout=30, context=self.ssl_context) as r:
                raw = r.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw)
        except urlerror.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            raise RuntimeError(f"openai_http_error:{exc.code}:{body}") from exc
        except Exception as exc:
            emsg = str(exc)
            if "CERTIFICATE_VERIFY_FAILED" in emsg:
                raise RuntimeError("openai_tls_cert_verify_failed") from exc
            raise RuntimeError(f"openai_request_failed:{exc}") from exc

        answer = self._extract_output_text(parsed) or "(no output)"
        self._append(session_key, "user", user_msg)
        self._append(session_key, "assistant", answer)
        return {"answer": answer, "raw_id": parsed.get("id")}


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
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Session-Token")
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


def _extract_auth_token(handler: BaseHTTPRequestHandler, body: Optional[Dict[str, Any]] = None) -> Optional[str]:
    auth_header = handler.headers.get("Authorization", "").strip()
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip() or None
    x_token = handler.headers.get("X-Session-Token", "").strip()
    if x_token:
        return x_token
    if body:
        tok = str(body.get("session_token", "")).strip()
        if tok:
            return tok
    return None


class AuthManager:
    def __init__(self, repo_root: pathlib.Path) -> None:
        self.repo_root = repo_root
        self.db_path = repo_root / "app" / "bridge" / "upright_auth.db"
        self.secret_path = repo_root / "app" / "bridge" / ".auth_secret"
        self._lock = threading.Lock()
        self._secret = self._load_or_create_secret()
        self._init_db()

    def _load_or_create_secret(self) -> bytes:
        env = os.environ.get("UPRIGHT_AUTH_SECRET", "").strip()
        if env:
            return env.encode("utf-8")
        if self.secret_path.exists():
            return self.secret_path.read_bytes()
        self.secret_path.parent.mkdir(parents=True, exist_ok=True)
        val = secrets.token_urlsafe(48).encode("utf-8")
        self.secret_path.write_bytes(val)
        try:
            os.chmod(self.secret_path, 0o600)
        except Exception:
            pass
        return val

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    def _init_db(self) -> None:
        with self._connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  email TEXT UNIQUE NOT NULL,
                  pw_salt BLOB NOT NULL,
                  pw_hash BLOB NOT NULL,
                  created_at REAL NOT NULL
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                  token_hash TEXT PRIMARY KEY,
                  user_id INTEGER NOT NULL,
                  created_at REAL NOT NULL,
                  expires_at REAL NOT NULL,
                  FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS user_openai (
                  user_id INTEGER PRIMARY KEY,
                  api_key_cipher TEXT NOT NULL,
                  model TEXT NOT NULL,
                  updated_at REAL NOT NULL,
                  FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """
            )
            con.commit()

    @staticmethod
    def _normalize_email(email: str) -> str:
        return email.strip().lower()

    def _hash_password(self, password: str, salt: bytes) -> bytes:
        return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000, dklen=32)

    def _hash_token(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _derive_enc_key(self) -> bytes:
        return hashlib.pbkdf2_hmac("sha256", self._secret, b"upright-openai-key", 120_000, dklen=32)

    def _encrypt(self, plain: str) -> str:
        key = self._derive_enc_key()
        p = plain.encode("utf-8")
        out = bytes([p[i] ^ key[i % len(key)] for i in range(len(p))])
        return base64.b64encode(out).decode("ascii")

    def _decrypt(self, cipher_b64: str) -> str:
        key = self._derive_enc_key()
        b = base64.b64decode(cipher_b64.encode("ascii"))
        out = bytes([b[i] ^ key[i % len(key)] for i in range(len(b))])
        return out.decode("utf-8")

    def register(self, email: str, password: str) -> Dict[str, Any]:
        em = self._normalize_email(email)
        if not em or "@" not in em:
            raise RuntimeError("invalid_email")
        if len(password) < 8:
            raise RuntimeError("weak_password")
        salt = secrets.token_bytes(16)
        pwh = self._hash_password(password, salt)
        now = time.time()
        with self._lock, self._connect() as con:
            try:
                con.execute(
                    "INSERT INTO users(email,pw_salt,pw_hash,created_at) VALUES(?,?,?,?)",
                    (em, salt, pwh, now),
                )
                con.commit()
            except sqlite3.IntegrityError as exc:
                raise RuntimeError("email_exists") from exc
        return self.login(email, password)

    def login(self, email: str, password: str) -> Dict[str, Any]:
        em = self._normalize_email(email)
        with self._lock, self._connect() as con:
            row = con.execute("SELECT id,email,pw_salt,pw_hash FROM users WHERE email=?", (em,)).fetchone()
            if not row:
                raise RuntimeError("invalid_credentials")
            calc = self._hash_password(password, row["pw_salt"])
            if not hmac.compare_digest(calc, row["pw_hash"]):
                raise RuntimeError("invalid_credentials")
            token = secrets.token_urlsafe(32)
            token_hash = self._hash_token(token)
            now = time.time()
            exp = now + 60 * 60 * 24 * 14
            con.execute("INSERT OR REPLACE INTO sessions(token_hash,user_id,created_at,expires_at) VALUES(?,?,?,?)", (token_hash, row["id"], now, exp))
            con.commit()
            return {"session_token": token, "user": {"id": row["id"], "email": row["email"]}}

    def me(self, token: Optional[str]) -> Optional[Dict[str, Any]]:
        if not token:
            return None
        tokh = self._hash_token(token)
        now = time.time()
        with self._lock, self._connect() as con:
            row = con.execute(
                """
                SELECT u.id AS id, u.email AS email, s.expires_at AS expires_at
                FROM sessions s
                JOIN users u ON u.id=s.user_id
                WHERE s.token_hash=?
                """,
                (tokh,),
            ).fetchone()
            if not row:
                return None
            if float(row["expires_at"]) < now:
                con.execute("DELETE FROM sessions WHERE token_hash=?", (tokh,))
                con.commit()
                return None
            krow = con.execute("SELECT model FROM user_openai WHERE user_id=?", (row["id"],)).fetchone()
            return {
                "id": int(row["id"]),
                "email": str(row["email"]),
                "openai_configured": bool(krow),
                "openai_model": (krow["model"] if krow else None),
            }

    def logout(self, token: Optional[str]) -> None:
        if not token:
            return
        tokh = self._hash_token(token)
        with self._lock, self._connect() as con:
            con.execute("DELETE FROM sessions WHERE token_hash=?", (tokh,))
            con.commit()

    def set_openai_key(self, user_id: int, api_key: str, model: Optional[str]) -> Dict[str, Any]:
        k = api_key.strip()
        if not k.startswith("sk-"):
            raise RuntimeError("invalid_openai_key")
        m = (model or "gpt-5-mini").strip() or "gpt-5-mini"
        cipher = self._encrypt(k)
        now = time.time()
        with self._lock, self._connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO user_openai(user_id,api_key_cipher,model,updated_at) VALUES(?,?,?,?)",
                (user_id, cipher, m, now),
            )
            con.commit()
        return {"configured": True, "model": m}

    def clear_openai_key(self, user_id: int) -> Dict[str, Any]:
        with self._lock, self._connect() as con:
            con.execute("DELETE FROM user_openai WHERE user_id=?", (user_id,))
            con.commit()
        return {"configured": False, "model": None}

    def get_openai_key(self, user_id: int) -> Optional[Dict[str, Any]]:
        with self._lock, self._connect() as con:
            row = con.execute("SELECT api_key_cipher,model FROM user_openai WHERE user_id=?", (user_id,)).fetchone()
            if not row:
                return None
            return {"api_key": self._decrypt(row["api_key_cipher"]), "model": row["model"]}


def _normalize_cmd(cmd: str) -> str:
    return " ".join(cmd.strip().split()).upper()


def _blocked_while_latched(cmd: str) -> bool:
    c = _normalize_cmd(cmd)
    safe_prefixes = ("GET", "DISARM", "HELP", "LOGCSV", "LOGT")
    return not c.startswith(safe_prefixes)


def run_compat_probe(gateway: NanoSerialGateway) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "ok": False,
        "profile": "unknown",
        "firmware_id": None,
        "required_fields": ["mode", "ang", "raw", "out", "kp", "ki", "kd", "set"],
        "missing_fields": [],
        "supported_commands": [],
        "missing_commands": [],
        "warnings": [],
    }

    # 1) Firmware identity probe (best-effort fallback chain)
    firmware_id = None
    for ident_cmd in ("GET_ID", "ID", "WHOAMI"):
        try:
            resp = gateway.command(ident_cmd, timeout=1.0)
            lines = [ln for ln in resp.get("lines", []) if ln]
            if any("ERR UNKNOWN" in ln for ln in lines):
                continue
            if lines:
                firmware_id = lines[-1]
                break
        except Exception:
            continue
    report["firmware_id"] = firmware_id

    # 2) Required status schema check
    status = gateway.get_status()
    report["status"] = status
    missing_fields = [f for f in report["required_fields"] if f not in status]
    report["missing_fields"] = missing_fields

    # 3) Command support probe from HELP output (safe, read-only)
    help_lines: list[str] = []
    try:
        h = gateway.command("HELP", timeout=1.5)
        help_lines = h.get("lines", [])
    except Exception as exc:
        report["warnings"].append(f"help_probe_failed:{exc}")

    help_blob = "\n".join(help_lines).upper()
    command_expect = [
        "GET",
        "ARM",
        "DISARM",
        "PID",
        "MOTION",
        "SETPOINT",
        "LIMITS",
        "CAL ZERO",
        "SAVECFG",
    ]
    supported = []
    missing = []
    for c in command_expect:
        if c in help_blob:
            supported.append(c)
        else:
            missing.append(c)

    report["supported_commands"] = supported
    report["missing_commands"] = missing

    # 4) Profile guess
    axis = str(status.get("axis", ""))
    if axis in {"X", "Y"} and "encmode" in status:
        report["profile"] = "upright_nano_balance_v2"
    elif axis in {"X", "Y"}:
        report["profile"] = "upright_nano_balance_core_like"

    report["ok"] = len(missing_fields) == 0 and len(missing) <= 2
    if missing_fields:
        report["warnings"].append("status schema mismatch")
    if firmware_id is None:
        report["warnings"].append("no explicit firmware identity command detected")

    return report


def _get_port_meta(port: str) -> Dict[str, Any]:
    meta: Dict[str, Any] = {
        "device": port,
        "description": None,
        "manufacturer": None,
        "product": None,
        "serial_number": None,
        "vid": None,
        "pid": None,
        "hwid": None,
    }
    if list_ports is None:
        return meta

    try:
        for p in list_ports.comports():
            if p.device != port:
                continue
            meta.update(
                {
                    "description": p.description,
                    "manufacturer": p.manufacturer,
                    "product": p.product,
                    "serial_number": p.serial_number,
                    "vid": p.vid,
                    "pid": p.pid,
                    "hwid": p.hwid,
                }
            )
            break
    except Exception:
        return meta
    return meta


def _guess_mcu(port_meta: Dict[str, Any]) -> str:
    blob = " ".join(
        str(port_meta.get(k, "") or "")
        for k in ("description", "manufacturer", "product", "hwid")
    ).upper()

    if "CH340" in blob or "CH341" in blob or "WCH" in blob:
        return "ATmega328P-class Nano via CH340 USB-UART"
    if "CP210" in blob:
        return "ESP-class MCU via CP210x USB bridge"
    if "FT232" in blob or "FTDI" in blob:
        return "MCU with FTDI USB-UART bridge"
    if "16U2" in blob or "ATMEGA16U2" in blob:
        return "ATmega-class Arduino USB interface (16U2)"
    if "CDC" in blob or "USB SERIAL" in blob:
        return "Generic USB CDC serial MCU"
    return "Unknown (serial bridge not fingerprinted)"


def run_connect_probe(gateway: NanoSerialGateway) -> Dict[str, Any]:
    health = gateway.health()
    connected = bool(health.get("connected", False))
    port = str(health.get("port", ""))
    baud = int(health.get("baud", 0) or 0)

    report: Dict[str, Any] = {
        "ok": False,
        "connected": connected,
        "port": port,
        "baud": baud,
        "port_meta": _get_port_meta(port),
        "mcu_guess": "unknown",
        "firmware_profile": "unknown",
        "confidence_pct": 0,
        "status_schema_ok": False,
        "status_error": None,
        "components": {
            "imu": False,
            "motor_driver": False,
            "encoder_feedback": False,
            "voltage_telemetry": False,
            "wheel_model": False,
            "persistent_calibration": False,
        },
        "commands": [],
        "missing_commands": [],
        "warnings": [],
        "next_questions": [
            "Which wheel+gearbox+motor set are you using on this bot build?",
            "Which motor driver board/chip is wired (for example TB6612, L298N)?",
            "Do encoders exist on both wheels, or only one side?",
            "Is external motor power currently connected and enabled?",
        ],
    }
    report["mcu_guess"] = _guess_mcu(report["port_meta"])

    if not connected:
        report["warnings"].append("bridge not connected to serial target")
        return report

    compat: Dict[str, Any]
    try:
        compat = run_compat_probe(gateway)
    except Exception as exc:
        compat = {"ok": False, "error": str(exc), "missing_fields": [], "missing_commands": []}
        report["warnings"].append(f"compat probe failed: {exc}")

    status = compat.get("status") if isinstance(compat, dict) else None
    if not status:
        try:
            status = gateway.get_status()
        except Exception as exc:
            report["status_error"] = str(exc)
            status = {}

    report["compat"] = compat
    report["firmware_profile"] = str(compat.get("profile", "unknown"))
    report["commands"] = list(compat.get("supported_commands", []))
    report["missing_commands"] = list(compat.get("missing_commands", []))

    required_fields = ("mode", "ang", "raw", "out", "kp", "ki", "kd", "set")
    report["status_schema_ok"] = all(f in status for f in required_fields)
    report["components"]["imu"] = "ang" in status and "raw" in status
    report["components"]["motor_driver"] = "out" in status
    report["components"]["encoder_feedback"] = "encL" in status or "encR" in status
    report["components"]["voltage_telemetry"] = "volRaw" in status
    report["components"]["wheel_model"] = "wspd" in status and "wpos" in status
    cmds = set(report["commands"])
    report["components"]["persistent_calibration"] = "CAL ZERO" in cmds and "SAVECFG" in cmds

    score = 0.0
    score += 0.2 if connected else 0.0
    score += 0.2 if report["status_schema_ok"] else 0.0
    score += 0.2 if report["firmware_profile"] != "unknown" else 0.0
    score += 0.2 if len(report["missing_commands"]) <= 2 else 0.0
    component_hits = sum(1 for v in report["components"].values() if v)
    score += 0.2 * (component_hits / max(1, len(report["components"])))
    report["confidence_pct"] = int(round(100 * min(1.0, score)))

    report["ok"] = report["status_schema_ok"] and report["confidence_pct"] >= 60
    if not report["status_schema_ok"]:
        report["warnings"].append("status schema mismatch")
    if report["missing_commands"]:
        report["warnings"].append("some expected commands were not found in HELP output")

    return report


def build_handler(
    gateway: NanoSerialGateway,
    control: BridgeControlState,
    commissioning: CommissioningManager,
    firmware: FirmwareManager,
    ai: AIManager,
    auth: AuthManager,
    telemetry_port: int,
):
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
                if u.path == "/firmware/status":
                    return _json(self, 200, {"ok": True, "firmware": firmware.status()})
                if u.path == "/ai/status":
                    tok = _extract_auth_token(self)
                    me = auth.me(tok)
                    if not me:
                        return _json(self, 200, {"ok": True, "ai": ai.status(configured=False, model="gpt-5-mini", session_key="anon"), "history": []})
                    model = str(me.get("openai_model") or "gpt-5-mini")
                    configured = bool(me.get("openai_configured"))
                    skey = f"user:{me['id']}"
                    return _json(self, 200, {"ok": True, "ai": ai.status(configured=configured, model=model, session_key=skey), "history": ai.history(skey)[-40:]})
                if u.path == "/auth/me":
                    tok = _extract_auth_token(self)
                    me = auth.me(tok)
                    if not me:
                        return _json(self, 401, {"ok": False, "error": "unauthenticated"})
                    return _json(self, 200, {"ok": True, "user": me})
                if u.path == "/auth/openai-key/status":
                    tok = _extract_auth_token(self)
                    me = auth.me(tok)
                    if not me:
                        return _json(self, 401, {"ok": False, "error": "unauthenticated"})
                    return _json(
                        self,
                        200,
                        {
                            "ok": True,
                            "openai": {
                                "configured": bool(me.get("openai_configured")),
                                "model": me.get("openai_model"),
                            },
                        },
                    )
                if u.path == "/firmware/sketch":
                    q = parse_qs(u.query)
                    path = q.get("path", [None])[0]
                    return _json(self, 200, {"ok": True, "sketch": firmware.read_sketch(path=path)})
                if u.path == "/firmware/boards":
                    return _json(self, 200, {"ok": True, "boards": firmware.list_boards()})
                if u.path == "/probe/compat":
                    return _json(self, 200, {"ok": True, "compat": run_compat_probe(gateway)})
                if u.path == "/probe/connect":
                    return _json(self, 200, {"ok": True, "probe": run_connect_probe(gateway)})
                return _json(self, 404, {"ok": False, "error": "not_found"})
            except Exception as exc:
                return _json(self, 500, {"ok": False, "error": str(exc)})

        def do_POST(self) -> None:
            try:
                u = urlparse(self.path)
                body = _read_json(self)

                if u.path == "/auth/register":
                    email = str(body.get("email", ""))
                    password = str(body.get("password", ""))
                    out = auth.register(email, password)
                    return _json(self, 200, {"ok": True, "session_token": out["session_token"], "user": out["user"]})

                if u.path == "/auth/login":
                    email = str(body.get("email", ""))
                    password = str(body.get("password", ""))
                    out = auth.login(email, password)
                    return _json(self, 200, {"ok": True, "session_token": out["session_token"], "user": out["user"]})

                if u.path == "/auth/logout":
                    tok = _extract_auth_token(self, body)
                    auth.logout(tok)
                    return _json(self, 200, {"ok": True})

                if u.path == "/auth/openai-key":
                    tok = _extract_auth_token(self, body)
                    me = auth.me(tok)
                    if not me:
                        return _json(self, 401, {"ok": False, "error": "unauthenticated"})
                    api_key = str(body.get("api_key", ""))
                    model = str(body.get("model", "gpt-5-mini"))
                    out = auth.set_openai_key(int(me["id"]), api_key, model)
                    return _json(self, 200, {"ok": True, "openai": out})

                if u.path == "/auth/openai-key/delete":
                    tok = _extract_auth_token(self, body)
                    me = auth.me(tok)
                    if not me:
                        return _json(self, 401, {"ok": False, "error": "unauthenticated"})
                    out = auth.clear_openai_key(int(me["id"]))
                    return _json(self, 200, {"ok": True, "openai": out})

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

                if u.path == "/firmware/check":
                    return _json(self, 200, {"ok": True, "firmware_check": firmware.check()})

                if u.path == "/firmware/compile":
                    st = firmware.compile(sketch=body.get("sketch"), fqbn=body.get("fqbn"))
                    return _json(self, 200, {"ok": True, "firmware": st})

                if u.path == "/firmware/upload":
                    st = firmware.upload(
                        sketch=body.get("sketch"),
                        fqbn=body.get("fqbn"),
                        port=body.get("port"),
                    )
                    return _json(self, 200, {"ok": True, "firmware": st})

                if u.path == "/firmware/upload-guarded":
                    st = firmware.upload_guarded(
                        gateway=gateway,
                        sketch=body.get("sketch"),
                        fqbn=body.get("fqbn"),
                        port=body.get("port"),
                    )
                    return _json(self, 200, {"ok": True, "firmware": st})

                if u.path == "/firmware/install-cli":
                    st = firmware.install_cli()
                    return _json(self, 200, {"ok": True, "firmware": st})

                if u.path == "/firmware/sketch":
                    content = str(body.get("content", ""))
                    path = body.get("path")
                    sk = firmware.write_sketch(content=content, path=path)
                    return _json(self, 200, {"ok": True, "sketch": sk})

                if u.path == "/ai/chat":
                    tok = _extract_auth_token(self, body)
                    me = auth.me(tok)
                    if not me:
                        return _json(self, 401, {"ok": False, "error": "unauthenticated"})
                    creds = auth.get_openai_key(int(me["id"]))
                    if not creds:
                        return _json(self, 403, {"ok": False, "error": "openai_key_not_configured"})
                    msg = str(body.get("message", "")).strip()
                    if not msg:
                        return _json(self, 400, {"ok": False, "error": "missing message"})
                    ctx = {
                        "status": gateway.get_status(),
                        "control": control.snapshot(),
                        "firmware": firmware.status(),
                    }
                    skey = f"user:{me['id']}"
                    out = ai.chat(
                        message=msg,
                        context=ctx,
                        session_key=skey,
                        api_key=creds["api_key"],
                        model=str(creds["model"] or "gpt-5-mini"),
                    )
                    return _json(
                        self,
                        200,
                        {
                            "ok": True,
                            "reply": out["answer"],
                            "ai": ai.status(configured=True, model=str(creds["model"] or "gpt-5-mini"), session_key=skey),
                            "history": ai.history(skey)[-40:],
                        },
                    )

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
                if msg in {"invalid_email", "weak_password", "email_exists", "invalid_credentials", "invalid_openai_key", "empty_message"}:
                    return _json(self, 400, {"ok": False, "error": msg})
                if msg in {"unauthenticated", "openai_api_key_missing"}:
                    return _json(self, 401, {"ok": False, "error": msg})
                if msg in {"estop_latched", "session_stale"}:
                    return _json(self, 423, {"ok": False, "error": msg, "control": control.snapshot()})
                if msg == "arm_not_prepared":
                    return _json(self, 409, {"ok": False, "error": msg, "control": control.snapshot()})
                if msg == "commissioning_running":
                    return _json(self, 409, {"ok": False, "error": msg, "commissioning": commissioning.status()})
                if msg == "firmware_running":
                    return _json(self, 409, {"ok": False, "error": msg, "firmware": firmware.status()})
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
    firmware = FirmwareManager(repo_root, args.port)
    ai = AIManager()
    auth = AuthManager(repo_root)
    telemetry = TelemetryHub(gw, control, args.host, args.telemetry_port)
    telemetry.start()

    print(f"bridge connected: {args.port} @ {args.baud}")
    print(f"initial status: {ready}")
    print(f"telemetry websocket: ws://{args.host}:{args.telemetry_port}/telemetry enabled={websockets is not None}")

    stop_evt = threading.Event()
    wd = threading.Thread(target=watchdog_loop, args=(gw, control, stop_evt), daemon=True)
    wd.start()

    server = ThreadingHTTPServer(
        (args.host, args.http_port),
        build_handler(gw, control, commissioning, firmware, ai, auth, args.telemetry_port),
    )
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

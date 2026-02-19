#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import base64
import collections
import hashlib
import hmac
import json
import logging
import os
import pathlib
import re
import shutil
import sqlite3
import subprocess
import secrets
import ssl
import threading
import time

logger = logging.getLogger(__name__)
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Optional
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

try:
    from app.bridge.codex_agent import CodexAgent, create_codex_agent
    from app.bridge.codex_db import get_codex_db
    from app.bridge.codex_rag import get_codex_rag
except ImportError:
    try:
        from codex_agent import CodexAgent, create_codex_agent
        from codex_db import get_codex_db
        from codex_rag import get_codex_rag
    except ImportError:
        CodexAgent = None  # type: ignore
        create_codex_agent = None  # type: ignore
        get_codex_db = None  # type: ignore
        get_codex_rag = None  # type: ignore


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
        self._unified_templates_dir = repo_root / "app" / "bridge" / "firmware_templates" / "unified_v1"
        self._generated_root = repo_root / "generated_firmware"

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

    def write_sketch_with_backup(self, *, content: str, path: Optional[str] = None, source: str = "assistant") -> Dict[str, Any]:
        target = pathlib.Path(path) if path else self._default_sketch_file()
        target.parent.mkdir(parents=True, exist_ok=True)
        backup_dir = self.repo_root / "generated_firmware" / "_sketch_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = int(time.time())
        backup_name = f"{target.name}.{source}.{stamp}.bak"
        backup_path = backup_dir / backup_name
        if target.exists() and target.is_file():
            shutil.copy2(target, backup_path)
        target.write_text(content, encoding="utf-8")
        return {
            "path": str(target),
            "bytes": len(content.encode("utf-8")),
            "backup_path": str(backup_path) if backup_path.exists() else None,
        }

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

    def unified_schema(self) -> Dict[str, Any]:
        return {
            "version": "unified.v1",
            "required": {
                "profile": ["label", "board", "hardware", "pins"],
                "board": ["fqbn"],
                "hardware": ["imu_type", "motor_driver"],
                "pins": [
                    "motor_l_pwm",
                    "motor_l_dir",
                    "motor_r_pwm",
                    "motor_r_dir",
                    "imu_sda",
                    "imu_scl",
                    "gate_enable",
                    "led",
                ],
            },
            "optional_pins": ["enc_l_a", "enc_l_b", "enc_r_a", "enc_r_b"],
            "notes": [
                "Pin values must be integers. Use -1 for optional pins that are not present.",
                "Board detection can infer FQBN/port, but wiring pins must come from user profile.",
            ],
        }

    @staticmethod
    def _safe_name(raw: str, fallback: str) -> str:
        candidate = re.sub(r"[^a-zA-Z0-9_]+", "_", raw.strip()).strip("_")
        return candidate[:64] if candidate else fallback

    def _validate_unified_profile(self, profile: Dict[str, Any]) -> tuple[Dict[str, Any], list[str]]:
        errors: list[str] = []
        if not isinstance(profile, dict):
            return {}, ["profile must be an object"]

        label = str(profile.get("label", "")).strip()
        board = profile.get("board")
        hardware = profile.get("hardware")
        pins = profile.get("pins")
        if not label:
            errors.append("profile.label is required")
        if not isinstance(board, dict):
            errors.append("profile.board must be an object")
            board = {}
        if not isinstance(hardware, dict):
            errors.append("profile.hardware must be an object")
            hardware = {}
        if not isinstance(pins, dict):
            errors.append("profile.pins must be an object")
            pins = {}

        fqbn = str(board.get("fqbn", "")).strip()
        if not fqbn:
            errors.append("profile.board.fqbn is required")
        imu_type = str(hardware.get("imu_type", "")).strip()
        if not imu_type:
            errors.append("profile.hardware.imu_type is required")
        motor_driver = str(hardware.get("motor_driver", "")).strip()
        if not motor_driver:
            errors.append("profile.hardware.motor_driver is required")

        required_pin_keys = [
            "motor_l_pwm",
            "motor_l_dir",
            "motor_r_pwm",
            "motor_r_dir",
            "imu_sda",
            "imu_scl",
            "gate_enable",
            "led",
        ]
        optional_pin_keys = ["enc_l_a", "enc_l_b", "enc_r_a", "enc_r_b"]
        parsed_pins: Dict[str, int] = {}
        for key in required_pin_keys + optional_pin_keys:
            raw = pins.get(key, -1 if key in optional_pin_keys else None)
            if raw is None:
                errors.append(f"profile.pins.{key} is required")
                continue
            try:
                parsed_pins[key] = int(raw)
            except Exception:
                errors.append(f"profile.pins.{key} must be an integer")

        normalized = {
            "label": label,
            "board": {
                "fqbn": fqbn,
                "port": str(board.get("port", "")).strip(),
                "mcu_family": str(board.get("mcu_family", "unknown")).strip() or "unknown",
            },
            "hardware": {
                "imu_type": imu_type,
                "motor_driver": motor_driver,
            },
            "pins": parsed_pins,
            "generated_at": int(time.time()),
            "schema_version": "unified.v1",
        }
        return normalized, errors

    def generate_unified(self, *, profile: Dict[str, Any], sketch_name: Optional[str] = None) -> Dict[str, Any]:
        norm, errors = self._validate_unified_profile(profile)
        if errors:
            raise RuntimeError("invalid_unified_profile: " + "; ".join(errors))
        if not self._unified_templates_dir.exists():
            raise RuntimeError(f"template_dir_missing: {self._unified_templates_dir}")

        ts = int(time.time())
        base_name = self._safe_name(sketch_name or norm["label"], f"upright_unified_{ts}")
        out_dir = self._generated_root / base_name
        suffix = 1
        while out_dir.exists():
            suffix += 1
            out_dir = self._generated_root / f"{base_name}_{suffix}"
        out_dir.mkdir(parents=True, exist_ok=False)

        tokens = {
            "__SKETCH_NAME__": out_dir.name,
            "__PROFILE_LABEL__": norm["label"],
            "__FQBN__": norm["board"]["fqbn"],
            "__IMU_TYPE__": norm["hardware"]["imu_type"],
            "__MOTOR_DRIVER__": norm["hardware"]["motor_driver"],
            "__PIN_MOTOR_L_PWM__": str(norm["pins"].get("motor_l_pwm", -1)),
            "__PIN_MOTOR_L_DIR__": str(norm["pins"].get("motor_l_dir", -1)),
            "__PIN_MOTOR_R_PWM__": str(norm["pins"].get("motor_r_pwm", -1)),
            "__PIN_MOTOR_R_DIR__": str(norm["pins"].get("motor_r_dir", -1)),
            "__PIN_IMU_SDA__": str(norm["pins"].get("imu_sda", -1)),
            "__PIN_IMU_SCL__": str(norm["pins"].get("imu_scl", -1)),
            "__PIN_GATE_ENABLE__": str(norm["pins"].get("gate_enable", -1)),
            "__PIN_LED__": str(norm["pins"].get("led", -1)),
            "__PIN_ENC_L_A__": str(norm["pins"].get("enc_l_a", -1)),
            "__PIN_ENC_L_B__": str(norm["pins"].get("enc_l_b", -1)),
            "__PIN_ENC_R_A__": str(norm["pins"].get("enc_r_a", -1)),
            "__PIN_ENC_R_B__": str(norm["pins"].get("enc_r_b", -1)),
        }

        rendered_files: list[str] = []
        for tmpl in sorted(self._unified_templates_dir.glob("*.tmpl")):
            text = tmpl.read_text(encoding="utf-8")
            for key, value in tokens.items():
                text = text.replace(key, value)
            out_name = tmpl.name[:-5]
            if out_name == "main.ino":
                out_name = f"{out_dir.name}.ino"
            target = out_dir / out_name
            target.write_text(text, encoding="utf-8")
            rendered_files.append(str(target))

        profile_path = out_dir / "profile.json"
        profile_path.write_text(json.dumps(norm, indent=2, sort_keys=True), encoding="utf-8")
        rendered_files.append(str(profile_path))
        archive = shutil.make_archive(str(out_dir), "zip", root_dir=str(out_dir.parent), base_dir=out_dir.name)
        return {
            "schema_version": "unified.v1",
            "sketch_folder": str(out_dir),
            "main_file": str(out_dir / f"{out_dir.name}.ino"),
            "archive": archive,
            "files": rendered_files,
            "profile": norm,
        }

    def generate_docs_pack(
        self,
        *,
        profile: Dict[str, Any],
        sketch_name: Optional[str] = None,
        sketch_content: Optional[str] = None,
        sketch_path: Optional[str] = None,
        force_regenerate: bool = False,
    ) -> Dict[str, Any]:
        norm, errors = self._validate_unified_profile(profile)
        if errors:
            raise RuntimeError("invalid_unified_profile: " + "; ".join(errors))

        ts = int(time.time())
        generation_id = f"docs_{int(time.time() * 1000)}_{secrets.token_hex(4)}"
        base_name = self._safe_name(sketch_name or norm["label"], f"upright_docs_{ts}")
        out_dir = self._generated_root / f"{base_name}_docs"
        suffix = 1
        while out_dir.exists():
            suffix += 1
            out_dir = self._generated_root / f"{base_name}_docs_{suffix}"
        out_dir.mkdir(parents=True, exist_ok=False)

        sketch_src = str(sketch_content or "").strip()
        sketch_source_label = "profile_only"
        if not sketch_src and isinstance(sketch_path, str) and sketch_path.strip():
            try:
                sketch_src = pathlib.Path(sketch_path.strip()).read_text(encoding="utf-8")
                sketch_source_label = "profile_plus_sketch_path"
            except Exception:
                sketch_src = ""
        elif sketch_src:
            sketch_source_label = "profile_plus_sketch_inline"

        cmd_keywords = ["GET", "PID", "MOTION", "SETPOINT", "LIMITS", "CAL", "SAVECFG", "ARM", "DISARM", "ESTOP"]
        detected_commands: list[str] = []
        detected_states: list[str] = []
        detected_pin_defs: list[str] = []
        has_setup = False
        has_loop = False
        if sketch_src:
            up = sketch_src.upper()
            has_setup = "VOID SETUP(" in up
            has_loop = "VOID LOOP(" in up
            for cmd in cmd_keywords:
                if re.search(rf"\\b{re.escape(cmd)}\\b", up):
                    detected_commands.append(cmd)
            for state in ["SAFE_IDLE", "IDLE", "ARMED", "BALANCING", "ESTOP", "FAULT"]:
                if re.search(rf"\\b{re.escape(state)}\\b", up):
                    detected_states.append(state)
            pin_rx_a = re.findall(r"#define\\s+([A-Za-z_][A-Za-z0-9_]*)\\s+(-?\\d+)", sketch_src)
            pin_rx_b = re.findall(r"const\\s+(?:uint8_t|int|byte|int16_t|int32_t)\\s+([A-Za-z_][A-Za-z0-9_]*)\\s*=\\s*(-?\\d+)", sketch_src)
            for name, val in (pin_rx_a + pin_rx_b):
                uname = name.upper()
                if "PIN" in uname or uname.startswith("MOTOR_") or uname.startswith("IMU_") or uname.startswith("ENC_"):
                    detected_pin_defs.append(f"{name}={val}")

        pins = norm.get("pins", {})
        pin_rows = [
            ("motor_l_pwm", "MOTOR_L_PWM", "OUT", "Motor Driver", "Left motor PWM output"),
            ("motor_l_dir", "MOTOR_L_DIR", "OUT", "Motor Driver", "Left motor direction"),
            ("motor_r_pwm", "MOTOR_R_PWM", "OUT", "Motor Driver", "Right motor PWM output"),
            ("motor_r_dir", "MOTOR_R_DIR", "OUT", "Motor Driver", "Right motor direction"),
            ("imu_sda", "IMU_SDA", "I/O", "IMU", "I2C data"),
            ("imu_scl", "IMU_SCL", "OUT", "IMU", "I2C clock"),
            ("gate_enable", "GATE_ENABLE", "OUT", "Safety Gate", "Motor driver gate/enable"),
            ("led", "LED", "OUT", "Status", "Status indicator LED"),
            ("enc_l_a", "ENC_L_A", "IN", "Encoder", "Left encoder A (-1 if unused)"),
            ("enc_l_b", "ENC_L_B", "IN", "Encoder", "Left encoder B (-1 if unused)"),
            ("enc_r_a", "ENC_R_A", "IN", "Encoder", "Right encoder A (-1 if unused)"),
            ("enc_r_b", "ENC_R_B", "IN", "Encoder", "Right encoder B (-1 if unused)"),
        ]

        pin_table_lines = [
            "# Pin Assignment Table",
            "",
            "| Pin | Signal | Direction | Component | Notes |",
            "| --- | --- | --- | --- | --- |",
        ]
        for key, signal, direction, component, notes in pin_rows:
            pin_val = pins.get(key, -1)
            pin_table_lines.append(f"| {pin_val} | {signal} | {direction} | {component} | {notes} |")
        pin_table_lines.append("")

        command_map_lines = [
            "# Command/API Map",
            "",
            "| Command | Changes | Notes |",
            "| --- | --- | --- |",
            "| `GET` | Reads status snapshot | No state mutation |",
            "| `PID <kp> <ki> <kd>` | PID gains (`kp`,`ki`,`kd`) | Inner loop tuning |",
            "| `MOTION <kv> <kx>` | Motion gains (`kv`,`kx`) | Outer behavior tuning |",
            "| `SETPOINT <deg>` | Balance target angle (`set`) | Degrees |",
            "| `LIMITS <out_max> <tip_deg> <i_max>` | Safety/output constraints | Device-side clamp |",
            "| `CAL ZERO` | Calibration zero offset | Use while stationary upright |",
            "| `SAVECFG` | Persists config | Writes active config to storage |",
            "| `ARM` | Transition toward armed path | Guarded by safety checks |",
            "| `DISARM` | Transition to safe/idle path | Stops balancing loop |",
            "| `ESTOP LATCH` / `ESTOP RESET` | Emergency stop state | Latch blocks motion commands |",
            "",
            f"Source mode: `{sketch_source_label}`.",
            "",
        ]

        if detected_commands:
            command_map_lines.extend([
                "Detected in sketch:",
                "",
                "| Command Token | Evidence |",
                "| --- | --- |",
            ])
            for token in sorted(set(detected_commands)):
                command_map_lines.append(f"| `{token}` | present in sketch source |")
            command_map_lines.append("")

        command_map_lines.extend([
            "Contract note: STATUS telemetry should include `ang`, `raw`, and `gyro|gyr|gx` for Kalman/compatibility compliance.",
            "",
        ])

        control_flow = """flowchart TB
  S0["Setup"] --> S1["Init serial and sensors"]
  S1 --> S2["Load config"]
  S2 --> S3["Enter SAFE_IDLE"]
  S3 --> L0["Loop tick"]

  L0 --> L1["Read IMU"]
  L1 --> L2["Fuse tilt to ang raw gyro"]
  L2 --> L3["Publish STATUS telemetry"]
  L3 --> L4["Parse serial commands"]
  L4 --> L5["Evaluate mode and guards"]

  L5 --> M0["SAFE_IDLE path motors off"]
  L5 --> M1["BALANCING path compute and drive"]
  L5 --> M2["Fault path latch stop"]

  M0 --> L0
  M1 --> L0
  M2 --> L0
"""
        if sketch_src:
            control_flow += f"\n%% sketch-evidence: setup_found={str(has_setup).lower()} loop_found={str(has_loop).lower()}\n"

        state_machine = """stateDiagram-v2
  [*] --> SAFE_IDLE
  SAFE_IDLE --> ARMED: ARM with prechecks
  ARMED --> BALANCING: balance enabled
  BALANCING --> SAFE_IDLE: DISARM
  ARMED --> SAFE_IDLE: DISARM
  SAFE_IDLE --> ESTOP: ESTOP_LATCH
  ARMED --> ESTOP: ESTOP_LATCH
  BALANCING --> ESTOP: ESTOP_LATCH or fault
  ESTOP --> SAFE_IDLE: ESTOP_RESET with checks
"""
        if detected_states:
            state_machine += "\n%% detected-states: " + ", ".join(sorted(set(detected_states))) + "\n"

        hardware_block = f"""graph TB
  MCU["MCU\\n{norm['board'].get('fqbn', 'unknown')}"]
  IMU["IMU\\n{norm['hardware'].get('imu_type', 'unknown')}"]
  MD["Motor Driver\\n{norm['hardware'].get('motor_driver', 'unknown')}"]
  ENC["Wheel Encoders"]
  USB["USB Serial"]
  GATE["Safety Gate"]
  MOT["Drive Motors"]

  MCU --> IMU
  MCU --> MD
  MCU --> ENC
  MCU --> USB
  MCU --> GATE
  MD --> MOT
"""

        pin_mapping = f"""graph TB
  MCU["MCU pin map"]

  subgraph MTR["Motor group"]
    PM["L_PWM={pins.get('motor_l_pwm', -1)}\\nL_DIR={pins.get('motor_l_dir', -1)}\\nR_PWM={pins.get('motor_r_pwm', -1)}\\nR_DIR={pins.get('motor_r_dir', -1)}"]
    MD["Motor driver pins"]
    PM --> MD
  end

  subgraph IMUG["IMU group"]
    PI["SDA={pins.get('imu_sda', -1)}\\nSCL={pins.get('imu_scl', -1)}"]
    ISIG["IMU bus pins"]
    PI --> ISIG
  end

  subgraph AUX["Aux group"]
    PG["GATE={pins.get('gate_enable', -1)}\\nLED={pins.get('led', -1)}"]
    PE["L_A={pins.get('enc_l_a', -1)}\\nL_B={pins.get('enc_l_b', -1)}\\nR_A={pins.get('enc_r_a', -1)}\\nR_B={pins.get('enc_r_b', -1)}"]
  end

  MCU --> PM
  MCU --> PI
  MCU --> PG
  MCU --> PE
"""

        files_map = {
            "control_flow.mmd": control_flow,
            "state_machine.mmd": state_machine,
            "hardware_block.mmd": hardware_block,
            "pin_mapping.mmd": pin_mapping,
            "pin_assignment.md": "\n".join(pin_table_lines),
            "command_api_map.md": "\n".join(command_map_lines),
            "source_report.md": "\n".join([
                "# Source Report",
                "",
                f"- generation_id: `{generation_id}`",
                f"- force_regenerate: `{str(force_regenerate).lower()}`",
                f"- mode: `{sketch_source_label}`",
                f"- sketch_path: `{sketch_path or ''}`",
                f"- setup_found: `{str(has_setup).lower()}`",
                f"- loop_found: `{str(has_loop).lower()}`",
                f"- detected_states: `{', '.join(sorted(set(detected_states))) if detected_states else 'none'}`",
                f"- detected_commands: `{', '.join(sorted(set(detected_commands))) if detected_commands else 'none'}`",
                f"- detected_pin_defs: `{', '.join(sorted(set(detected_pin_defs))[:20]) if detected_pin_defs else 'none'}`",
                "",
            ]),
        }

        rendered_files: list[str] = []
        for name, content in files_map.items():
            target = out_dir / name
            target.write_text(content, encoding="utf-8")
            rendered_files.append(str(target))

        profile_path = out_dir / "profile.json"
        profile_path.write_text(json.dumps(norm, indent=2, sort_keys=True), encoding="utf-8")
        rendered_files.append(str(profile_path))
        archive = shutil.make_archive(str(out_dir), "zip", root_dir=str(out_dir.parent), base_dir=out_dir.name)

        return {
            "schema_version": "firmware_docs.v1",
            "generation_id": generation_id,
            "generated_at": int(time.time()),
            "docs_folder": str(out_dir),
            "archive": archive,
            "files": rendered_files,
            "artifacts": files_map,
            "profile": norm,
        }


class AIManager:
    def __init__(self, repo_root: pathlib.Path) -> None:
        self.default_api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        self.default_model = os.environ.get("OPENAI_MODEL", "gpt-5-mini")
        self.base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.ssl_context = self._build_ssl_context()
        self.state_path = repo_root / "app" / "bridge" / "ai_threads.json"
        self._lock = threading.Lock()
        self._threads: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._active_thread: Dict[str, str] = {}
        self._load_state()

    def _load_state(self) -> None:
        try:
            if not self.state_path.exists():
                return
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return
            threads = raw.get("threads")
            active = raw.get("active_thread")
            if isinstance(threads, dict):
                clean_threads: Dict[str, Dict[str, Dict[str, Any]]] = {}
                for skey, bucket in threads.items():
                    if not isinstance(skey, str) or not isinstance(bucket, dict):
                        continue
                    clean_bucket: Dict[str, Dict[str, Any]] = {}
                    for tid, entry in bucket.items():
                        if not isinstance(tid, str) or not isinstance(entry, dict):
                            continue
                        msgs = entry.get("messages", [])
                        if not isinstance(msgs, list):
                            msgs = []
                        clean_msgs = []
                        for m in msgs[-120:]:
                            if not isinstance(m, dict):
                                continue
                            role = str(m.get("role", "assistant"))
                            text = str(m.get("text", ""))
                            ts = float(m.get("ts", time.time()) or time.time())
                            clean_msgs.append({"ts": ts, "role": role, "text": text})
                        clean_bucket[tid] = {
                            "id": tid,
                            "title": str(entry.get("title", "New Chat") or "New Chat"),
                            "created_at": float(entry.get("created_at", time.time()) or time.time()),
                            "updated_at": float(entry.get("updated_at", time.time()) or time.time()),
                            "messages": clean_msgs,
                        }
                    if clean_bucket:
                        clean_threads[skey] = clean_bucket
                self._threads = clean_threads
            if isinstance(active, dict):
                self._active_thread = {str(k): str(v) for k, v in active.items() if isinstance(k, str) and isinstance(v, str)}
        except Exception:
            # Keep chat available even if persisted state is malformed.
            return

    def _save_state_locked(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"threads": self._threads, "active_thread": self._active_thread}
        self.state_path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")

    @staticmethod
    def _build_ssl_context() -> ssl.SSLContext:
        # Allow explicit override if the host needs a custom CA bundle.
        ca_bundle = os.environ.get("OPENAI_CA_BUNDLE", "").strip()
        if ca_bundle:
            return ssl.create_default_context(cafile=ca_bundle)
        if certifi is not None:
            return ssl.create_default_context(cafile=certifi.where())
        return ssl.create_default_context()

    def _thread_title(self, user_text: str) -> str:
        t = " ".join(user_text.strip().split())
        if not t:
            return "New Chat"
        return t[:44]

    def _ensure_thread_locked(self, session_key: str, thread_id: Optional[str] = None) -> tuple[str, Dict[str, Any]]:
        bucket = self._threads.setdefault(session_key, {})
        active = self._active_thread.get(session_key)
        chosen = thread_id or active
        if chosen and chosen in bucket:
            self._active_thread[session_key] = chosen
            return chosen, bucket[chosen]
        if thread_id and thread_id not in bucket:
            # Explicit thread selection must never silently fall back; callers
            # rely on this to detect stale/missing thread IDs.
            raise RuntimeError("thread_not_found")

        if not chosen and bucket:
            picked = max(bucket.values(), key=lambda t: float(t.get("updated_at") or 0.0))
            tid = str(picked["id"])
            self._active_thread[session_key] = tid
            return tid, picked

        new_id = secrets.token_urlsafe(8)
        now = time.time()
        entry = {
            "id": new_id,
            "title": "New Chat",
            "created_at": now,
            "updated_at": now,
            "messages": [],
        }
        bucket[new_id] = entry
        self._active_thread[session_key] = new_id
        self._save_state_locked()
        return new_id, entry

    def _append(self, session_key: str, role: str, text: str, *, thread_id: Optional[str] = None) -> str:
        with self._lock:
            tid, thread = self._ensure_thread_locked(session_key, thread_id)
            msgs = thread["messages"]
            msgs.append({"ts": time.time(), "role": role, "text": text})
            if len(msgs) > 120:
                del msgs[: len(msgs) - 120]
            thread["updated_at"] = time.time()
            if role == "user" and thread.get("title", "New Chat") == "New Chat":
                thread["title"] = self._thread_title(text)
            self._active_thread[session_key] = tid
            self._save_state_locked()
            return tid

    def list_threads(self, session_key: str) -> list[Dict[str, Any]]:
        with self._lock:
            bucket = self._threads.get(session_key, {})
            out: list[Dict[str, Any]] = []
            for thread in bucket.values():
                msgs = thread.get("messages", [])
                preview = msgs[-1]["text"][:96] if msgs else ""
                out.append(
                    {
                        "id": thread["id"],
                        "title": thread.get("title", "New Chat"),
                        "created_at": thread.get("created_at"),
                        "updated_at": thread.get("updated_at"),
                        "message_count": len(msgs),
                        "preview": preview,
                    }
                )
            out.sort(key=lambda t: float(t.get("updated_at") or 0.0), reverse=True)
            return out

    def create_thread(self, session_key: str, title: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            tid, thread = self._ensure_thread_locked(session_key, None)
            # Ensure a fresh thread even if one already exists/active.
            if thread.get("messages"):
                tid = secrets.token_urlsafe(8)
                now = time.time()
                thread = {
                    "id": tid,
                    "title": (title or "New Chat").strip() or "New Chat",
                    "created_at": now,
                    "updated_at": now,
                    "messages": [],
                }
                self._threads.setdefault(session_key, {})[tid] = thread
                self._active_thread[session_key] = tid
            else:
                if title:
                    thread["title"] = title.strip() or "New Chat"
            self._save_state_locked()
            return {
                "id": thread["id"],
                "title": thread["title"],
                "created_at": thread["created_at"],
                "updated_at": thread["updated_at"],
            }

    def select_thread(self, session_key: str, thread_id: str) -> Dict[str, Any]:
        with self._lock:
            bucket = self._threads.get(session_key, {})
            if thread_id not in bucket:
                raise RuntimeError("thread_not_found")
            self._active_thread[session_key] = thread_id
            self._save_state_locked()
            t = bucket[thread_id]
            return {
                "id": t["id"],
                "title": t["title"],
                "created_at": t["created_at"],
                "updated_at": t["updated_at"],
            }

    def status(self, *, configured: bool, model: str, session_key: str) -> Dict[str, Any]:
        with self._lock:
            tid, thread = self._ensure_thread_locked(session_key)
            hlen = len(thread.get("messages", []))
            tcount = len(self._threads.get(session_key, {}))
        return {"configured": configured, "model": model, "history_len": hlen, "active_thread_id": tid, "thread_count": tcount}

    def history(self, session_key: str, thread_id: Optional[str] = None) -> list[Dict[str, Any]]:
        with self._lock:
            tid, thread = self._ensure_thread_locked(session_key, thread_id)
            self._active_thread[session_key] = tid
            return list(thread.get("messages", []))

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


    def chat(
        self,
        *,
        message: str,
        context: Dict[str, Any],
        session_key: str,
        api_key: str,
        model: str,
        thread_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not api_key:
            raise RuntimeError("openai_api_key_missing")
        user_msg = message.strip()
        if not user_msg:
            raise RuntimeError("empty_message")

        context_blob = json.dumps(context, separators=(",", ":"), ensure_ascii=True)
        prompt = system_prompt or (
            "You are Codex for UpRight.os, a robotics tuning copilot. "
            "Be concise, practical, and safe. Never claim actions already executed unless tool output confirms it."
        )

        payload = {
            "model": model,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": prompt}]},
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
        tid = self._append(session_key, "user", user_msg, thread_id=thread_id)
        self._append(session_key, "assistant", answer, thread_id=tid)
        return {"answer": answer, "raw_id": parsed.get("id"), "thread_id": tid}

    def chat_stream(
        self,
        *,
        message: str,
        context: Dict[str, Any],
        session_key: str,
        api_key: str,
        model: str,
        on_delta: Callable[[str], None],
        thread_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not api_key:
            raise RuntimeError("openai_api_key_missing")
        user_msg = message.strip()
        if not user_msg:
            raise RuntimeError("empty_message")

        context_blob = json.dumps(context, separators=(",", ":"), ensure_ascii=True)
        prompt = system_prompt or (
            "You are Codex for UpRight.os, a robotics tuning copilot. "
            "Be concise, practical, and safe. Never claim actions already executed unless tool output confirms it."
        )

        payload = {
            "model": model,
            "stream": True,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": prompt}]},
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

        chunks: list[str] = []
        raw_id: Optional[str] = None
        completed_response: Optional[Dict[str, Any]] = None
        try:
            with urlrequest.urlopen(req, timeout=90, context=self.ssl_context) as r:
                for raw in r:
                    if not raw:
                        continue
                    line = raw.decode("utf-8", errors="replace").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    payload_txt = line[5:].strip()
                    if not payload_txt or payload_txt == "[DONE]":
                        continue
                    evt = json.loads(payload_txt)
                    et = str(evt.get("type", ""))
                    if et == "response.output_text.delta":
                        delta = str(evt.get("delta", ""))
                        if delta:
                            chunks.append(delta)
                            on_delta(delta)
                    elif et == "response.completed":
                        resp = evt.get("response")
                        if isinstance(resp, dict):
                            completed_response = resp
                            rid = resp.get("id")
                            if isinstance(rid, str) and rid:
                                raw_id = rid
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

        answer = "".join(chunks).strip()
        if (not answer) and completed_response:
            answer = self._extract_output_text(completed_response)
        answer = answer or "(no output)"
        tid = self._append(session_key, "user", user_msg, thread_id=thread_id)
        self._append(session_key, "assistant", answer, thread_id=tid)
        return {"answer": answer, "raw_id": raw_id, "thread_id": tid}


def _safe_float(v: Any) -> Optional[float]:
    try:
        return float(v)
    except Exception:
        return None


def _first_float(status: Dict[str, Any], *keys: str) -> Optional[float]:
    for k in keys:
        if k in status:
            out = _safe_float(status.get(k))
            if out is not None:
                return out
    return None


def _extract_apply_json(answer: str) -> Optional[Dict[str, Any]]:
    marker = "UPRIGHT_APPLY_JSON:"
    idx = answer.find(marker)
    if idx < 0:
        return None
    tail = answer[idx + len(marker):].lstrip()
    if not tail.startswith("{"):
        return None
    dec = json.JSONDecoder()
    try:
        obj, _ = dec.raw_decode(tail)
    except Exception:
        return None
    if isinstance(obj, dict):
        return obj
    return None


def _sanitize_apply_plan(raw: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    pid = raw.get("pid")
    if isinstance(pid, dict):
        kp = _safe_float(pid.get("kp"))
        ki = _safe_float(pid.get("ki"))
        kd = _safe_float(pid.get("kd"))
        partial: Dict[str, float] = {}
        if kp is not None:
            partial["kp"] = kp
        if ki is not None:
            partial["ki"] = ki
        if kd is not None:
            partial["kd"] = kd
        if partial:
            out["pid"] = partial
    motion = raw.get("motion")
    if isinstance(motion, dict):
        kv = _safe_float(motion.get("kv"))
        kx = _safe_float(motion.get("kx"))
        partial_m: Dict[str, float] = {}
        if kv is not None:
            partial_m["kv"] = kv
        if kx is not None:
            partial_m["kx"] = kx
        if partial_m:
            out["motion"] = partial_m
    setpoint = raw.get("setpoint")
    if isinstance(setpoint, dict):
        deg = _safe_float(setpoint.get("deg"))
        if deg is not None:
            out["setpoint"] = {"deg": deg}
    else:
        deg = _safe_float(setpoint)
        if deg is not None:
            out["setpoint"] = {"deg": deg}
    limits = raw.get("limits")
    if isinstance(limits, dict):
        out_max = _safe_float(limits.get("out_max"))
        tip_deg = _safe_float(limits.get("tip_deg"))
        i_max = _safe_float(limits.get("i_max"))
        partial_l: Dict[str, float] = {}
        if out_max is not None:
            partial_l["out_max"] = out_max
        if tip_deg is not None:
            partial_l["tip_deg"] = tip_deg
        if i_max is not None:
            partial_l["i_max"] = i_max
        if partial_l:
            out["limits"] = partial_l
    unified = raw.get("unified")
    if isinstance(unified, dict):
        profile = unified.get("profile")
        sketch_name = unified.get("sketch_name")
        if isinstance(profile, dict):
            part_u: Dict[str, Any] = {"profile": profile}
            if isinstance(sketch_name, str) and sketch_name.strip():
                part_u["sketch_name"] = sketch_name.strip()
            out["unified"] = part_u
    sketch = raw.get("sketch")
    if isinstance(sketch, dict):
        content = sketch.get("content")
        path = sketch.get("path")
        if isinstance(content, str) and content.strip():
            part_s: Dict[str, Any] = {"content": content}
            if isinstance(path, str) and path.strip():
                part_s["path"] = path.strip()
            out["sketch"] = part_s
    return out


def _strip_apply_json_block(answer: str) -> str:
    marker = "UPRIGHT_APPLY_JSON:"
    idx = answer.find(marker)
    if idx < 0:
        return answer.strip()
    head = answer[:idx].rstrip()
    tail = answer[idx + len(marker):].lstrip()
    if tail.startswith("{"):
        dec = json.JSONDecoder()
        try:
            _, end_idx = dec.raw_decode(tail)
            tail = tail[end_idx:].lstrip()
        except Exception:
            pass
    merged = f"{head}\n{tail}".strip() if head and tail else (head or tail).strip()
    return merged


def _format_apply_note(apply_result: Dict[str, Any]) -> str:
    if not bool(apply_result.get("ok", False)):
        return f"Apply failed: {str(apply_result.get('error', 'unknown_error'))}"
    applied = apply_result.get("applied", [])
    if not isinstance(applied, list):
        applied = []
    sections = ", ".join(str(x) for x in applied) if applied else "none"
    changed = apply_result.get("changed", {})
    kd_note = ""
    if isinstance(changed, dict):
        pid = changed.get("pid")
        if isinstance(pid, dict):
            before = pid.get("before") if isinstance(pid.get("before"), dict) else {}
            target = pid.get("target") if isinstance(pid.get("target"), dict) else {}
            bkd = before.get("kd")
            tkd = target.get("kd")
            if bkd is not None and tkd is not None:
                kd_note = f" KD {float(bkd):.3f} -> {float(tkd):.3f}."
    sid = str(apply_result.get("snapshot_id", "")).strip()
    extras = apply_result.get("artifacts", {})
    extra_note = ""
    if isinstance(extras, dict):
        sketch_path = extras.get("sketch_path")
        unified_folder = extras.get("unified_folder")
        if isinstance(unified_folder, str) and unified_folder:
            extra_note += f" Unified scaffold: {unified_folder}."
        if isinstance(sketch_path, str) and sketch_path:
            extra_note += f" Sketch updated: {sketch_path}."
    if sid:
        return f"Applied now: {sections}.{kd_note}{extra_note} Revert point saved ({sid}).".strip()
    return f"Applied now: {sections}.{kd_note}{extra_note}".strip()


class ConfigHistoryManager:
    def __init__(self, repo_root: pathlib.Path) -> None:
        self.path = repo_root / "app" / "bridge" / "config_history.json"
        self._lock = threading.Lock()
        self._max_entries = 200

    def _read_unlocked(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"snapshots": []}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"snapshots": []}
        if not isinstance(raw, dict):
            return {"snapshots": []}
        snaps = raw.get("snapshots")
        if not isinstance(snaps, list):
            snaps = []
        return {"snapshots": snaps}

    def _write_unlocked(self, data: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def _capture_fields(self, status: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "pid": {
                "kp": _first_float(status, "kp"),
                "ki": _first_float(status, "ki"),
                "kd": _first_float(status, "kd"),
            },
            "motion": {
                "kv": _first_float(status, "kv"),
                "kx": _first_float(status, "kx"),
            },
            "setpoint": {
                "deg": _first_float(status, "set"),
            },
            "limits": {
                "out_max": _first_float(status, "outMax", "out_max"),
                "tip_deg": _first_float(status, "tipDeg", "tip_deg"),
                "i_max": _first_float(status, "iMax", "i_max"),
            },
        }

    def save_snapshot(self, *, source: str, status_before: Dict[str, Any], note: str = "") -> Dict[str, Any]:
        entry = {
            "snapshot_id": secrets.token_urlsafe(8),
            "ts": time.time(),
            "source": source,
            "note": note,
            "values": self._capture_fields(status_before),
            "status_before": dict(status_before),
        }
        with self._lock:
            data = self._read_unlocked()
            snaps = list(data.get("snapshots", []))
            snaps.append(entry)
            if len(snaps) > self._max_entries:
                snaps = snaps[-self._max_entries:]
            data["snapshots"] = snaps
            self._write_unlocked(data)
        return entry

    def list_snapshots(self, *, limit: int = 30) -> list[Dict[str, Any]]:
        n = max(1, min(int(limit), 200))
        with self._lock:
            data = self._read_unlocked()
            snaps = list(data.get("snapshots", []))
        snaps.sort(key=lambda e: float(e.get("ts", 0.0) or 0.0), reverse=True)
        return snaps[:n]

    def get_snapshot(self, snapshot_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        with self._lock:
            data = self._read_unlocked()
            snaps = list(data.get("snapshots", []))
        if not snaps:
            return None
        if snapshot_id:
            for e in snaps:
                if str(e.get("snapshot_id", "")) == snapshot_id:
                    return e
            return None
        snaps.sort(key=lambda e: float(e.get("ts", 0.0) or 0.0), reverse=True)
        return snaps[0]


def _apply_tuning_plan(
    gateway: NanoSerialGateway,
    config_history: ConfigHistoryManager,
    plan: Dict[str, Any],
    *,
    source: str,
) -> Dict[str, Any]:
    status_before = gateway.get_status()
    curr_kp = _first_float(status_before, "kp")
    curr_ki = _first_float(status_before, "ki")
    curr_kd = _first_float(status_before, "kd")
    curr_kv = _first_float(status_before, "kv")
    curr_kx = _first_float(status_before, "kx")
    curr_set = _first_float(status_before, "set")
    curr_out_max = _first_float(status_before, "outMax", "out_max")
    curr_tip_deg = _first_float(status_before, "tipDeg", "tip_deg")
    curr_i_max = _first_float(status_before, "iMax", "i_max")
    snap = config_history.save_snapshot(source=source, status_before=status_before, note="auto-pre-apply")
    actions: list[str] = []
    changed: Dict[str, Any] = {}
    if "pid" in plan:
        p = plan["pid"]
        kp = _safe_float(p.get("kp")) if isinstance(p, dict) else None
        ki = _safe_float(p.get("ki")) if isinstance(p, dict) else None
        kd = _safe_float(p.get("kd")) if isinstance(p, dict) else None
        if kp is None:
            kp = curr_kp
        if ki is None:
            ki = curr_ki
        if kd is None:
            kd = curr_kd
        if kp is None or ki is None or kd is None:
            raise RuntimeError("apply_pid_missing_current_values")
        gateway.command(f"PID {kp} {ki} {kd}", expect_contains="OK PID", timeout=2.0)
        actions.append("pid")
        changed["pid"] = {"before": {"kp": curr_kp, "ki": curr_ki, "kd": curr_kd}, "target": {"kp": kp, "ki": ki, "kd": kd}}
    if "motion" in plan:
        m = plan["motion"]
        kv = _safe_float(m.get("kv")) if isinstance(m, dict) else None
        kx = _safe_float(m.get("kx")) if isinstance(m, dict) else None
        if kv is None:
            kv = curr_kv
        if kx is None:
            kx = curr_kx
        if kv is None or kx is None:
            raise RuntimeError("apply_motion_missing_current_values")
        gateway.command(f"MOTION {kv} {kx}", expect_contains="OK MOTION", timeout=2.0)
        actions.append("motion")
        changed["motion"] = {"before": {"kv": curr_kv, "kx": curr_kx}, "target": {"kv": kv, "kx": kx}}
    if "setpoint" in plan:
        s = plan["setpoint"]
        deg = _safe_float(s.get("deg")) if isinstance(s, dict) else None
        if deg is None:
            deg = curr_set
        if deg is None:
            raise RuntimeError("apply_setpoint_missing_current_value")
        gateway.command(f"SETPOINT {deg}", expect_contains="OK SETPOINT", timeout=2.0)
        actions.append("setpoint")
        changed["setpoint"] = {"before": {"deg": curr_set}, "target": {"deg": deg}}
    if "limits" in plan:
        l = plan["limits"]
        out_max = _safe_float(l.get("out_max")) if isinstance(l, dict) else None
        tip_deg = _safe_float(l.get("tip_deg")) if isinstance(l, dict) else None
        i_max = _safe_float(l.get("i_max")) if isinstance(l, dict) else None
        if out_max is None:
            out_max = curr_out_max
        if tip_deg is None:
            tip_deg = curr_tip_deg
        if i_max is None:
            i_max = curr_i_max
        if out_max is None or tip_deg is None or i_max is None:
            raise RuntimeError("apply_limits_missing_current_values")
        gateway.command(f"LIMITS {out_max} {tip_deg} {i_max}", expect_contains="OK LIMITS", timeout=2.0)
        actions.append("limits")
        changed["limits"] = {"before": {"out_max": curr_out_max, "tip_deg": curr_tip_deg, "i_max": curr_i_max}, "target": {"out_max": out_max, "tip_deg": tip_deg, "i_max": i_max}}
    return {"ok": True, "snapshot_id": snap["snapshot_id"], "applied": actions, "changed": changed, "status": gateway.get_status()}


def _apply_assistant_plan(
    gateway: NanoSerialGateway,
    config_history: ConfigHistoryManager,
    firmware: FirmwareManager,
    plan: Dict[str, Any],
    *,
    source: str,
) -> Dict[str, Any]:
    tuning_keys = {"pid", "motion", "setpoint", "limits"}
    tuning_plan = {k: plan[k] for k in tuning_keys if k in plan}
    applied: list[str] = []
    changed: Dict[str, Any] = {}
    artifacts: Dict[str, Any] = {}
    snapshot_id: Optional[str] = None
    status_after: Optional[Dict[str, Any]] = None

    if tuning_plan:
        t = _apply_tuning_plan(gateway, config_history, tuning_plan, source=source)
        if not bool(t.get("ok", False)):
            return t
        applied.extend(list(t.get("applied", [])) if isinstance(t.get("applied"), list) else [])
        if isinstance(t.get("changed"), dict):
            changed.update(t["changed"])
        sid = t.get("snapshot_id")
        if isinstance(sid, str) and sid:
            snapshot_id = sid
        if isinstance(t.get("status"), dict):
            status_after = t.get("status")

    unified = plan.get("unified")
    if isinstance(unified, dict):
        profile = unified.get("profile")
        if not isinstance(profile, dict):
            raise RuntimeError("apply_unified_profile_missing")
        sketch_name = unified.get("sketch_name")
        out = firmware.generate_unified(profile=profile, sketch_name=str(sketch_name) if isinstance(sketch_name, str) else None)
        applied.append("unified")
        artifacts["unified_folder"] = out.get("sketch_folder")
        artifacts["unified_archive"] = out.get("archive")
        artifacts["unified_main_file"] = out.get("main_file")

    sketch = plan.get("sketch")
    if isinstance(sketch, dict):
        content = sketch.get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("apply_sketch_content_missing")
        path = sketch.get("path")
        out = firmware.write_sketch_with_backup(
            content=content,
            path=str(path) if isinstance(path, str) and path.strip() else None,
            source="assistant",
        )
        applied.append("sketch")
        artifacts["sketch_path"] = out.get("path")
        artifacts["sketch_backup"] = out.get("backup_path")
        artifacts["sketch_bytes"] = out.get("bytes")

    if not status_after:
        try:
            status_after = gateway.get_status()
        except Exception:
            status_after = None
    return {
        "ok": True,
        "snapshot_id": snapshot_id,
        "applied": applied,
        "changed": changed,
        "artifacts": artifacts,
        "status": status_after,
    }


def _revert_snapshot(
    gateway: NanoSerialGateway,
    config_history: ConfigHistoryManager,
    *,
    snapshot_id: Optional[str] = None,
) -> Dict[str, Any]:
    snap = config_history.get_snapshot(snapshot_id=snapshot_id)
    if not snap:
        raise RuntimeError("snapshot_not_found")
    vals = snap.get("values", {})
    pid = vals.get("pid", {}) if isinstance(vals, dict) else {}
    motion = vals.get("motion", {}) if isinstance(vals, dict) else {}
    setpoint = vals.get("setpoint", {}) if isinstance(vals, dict) else {}
    limits = vals.get("limits", {}) if isinstance(vals, dict) else {}
    actions: list[str] = []
    if all(_safe_float(pid.get(k)) is not None for k in ("kp", "ki", "kd")):
        gateway.command(f"PID {float(pid['kp'])} {float(pid['ki'])} {float(pid['kd'])}", expect_contains="OK PID", timeout=2.0)
        actions.append("pid")
    if all(_safe_float(motion.get(k)) is not None for k in ("kv", "kx")):
        gateway.command(f"MOTION {float(motion['kv'])} {float(motion['kx'])}", expect_contains="OK MOTION", timeout=2.0)
        actions.append("motion")
    if _safe_float(setpoint.get("deg")) is not None:
        gateway.command(f"SETPOINT {float(setpoint['deg'])}", expect_contains="OK SETPOINT", timeout=2.0)
        actions.append("setpoint")
    if all(_safe_float(limits.get(k)) is not None for k in ("out_max", "tip_deg", "i_max")):
        gateway.command(
            f"LIMITS {float(limits['out_max'])} {float(limits['tip_deg'])} {float(limits['i_max'])}",
            expect_contains="OK LIMITS",
            timeout=2.0,
        )
        actions.append("limits")
    return {"ok": True, "snapshot_id": snap.get("snapshot_id"), "reverted": actions, "status": gateway.get_status()}


def _read_csv_tail(path: pathlib.Path, max_tail: int = 80) -> Dict[str, Any]:
    total_lines = 0
    header = ""
    tail: "collections.deque[str]" = collections.deque(maxlen=max(1, max_tail))
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for idx, line in enumerate(f):
            txt = line.rstrip("\n")
            if idx == 0:
                header = txt
            else:
                tail.append(txt)
            total_lines += 1
    return {
        "path": str(path),
        "line_count": total_lines,
        "header": header,
        "tail_rows": list(tail),
    }


class HostCaptureManager:
    def __init__(self, repo_root: pathlib.Path) -> None:
        self.out_dir = repo_root / "tests" / "results"
        self._lock = threading.Lock()
        self._state = "idle"
        self._delay_ms = 0
        self._freq_hz = 8.0
        self._target_lines = 0
        self._rows = 0
        self._armed_mono: Optional[float] = None
        self._last_row_mono: Optional[float] = None
        self._started_at: Optional[float] = None
        self._finished_at: Optional[float] = None
        self._last_error: Optional[str] = None
        self._latest_run: Optional[str] = None
        self._current_path: Optional[pathlib.Path] = None
        self._fh: Optional[Any] = None

    @staticmethod
    def _header() -> str:
        return "host_ts,mode,estop,ang,raw,gyro,set,out,pid,mot,wspd,wpos,kp,ki,kd,kv,kx,encL,encR,volRaw"

    def _close_file_unlocked(self) -> None:
        if self._fh is not None:
            try:
                self._fh.flush()
                self._fh.close()
            except Exception:
                pass
        self._fh = None

    def _finish_unlocked(self, next_state: str) -> None:
        self._state = next_state
        self._finished_at = time.time()
        self._armed_mono = None
        self._close_file_unlocked()
        if self._current_path is not None:
            self._latest_run = str(self._current_path)
        self._current_path = None

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "state": self._state,
                "delay_ms": self._delay_ms,
                "freq_hz": self._freq_hz,
                "target_lines": self._target_lines,
                "rows": self._rows,
                "started_at": self._started_at,
                "finished_at": self._finished_at,
                "latest_run": self._latest_run,
                "last_error": self._last_error,
            }

    def arm(self, *, delay_ms: int, lines: int, freq_hz: float = 8.0) -> Dict[str, Any]:
        d = max(0, min(int(delay_ms), 60_000))
        n = max(1, min(int(lines), 3_000))
        hz = max(1.0, min(float(freq_hz), 100.0))
        with self._lock:
            self._close_file_unlocked()
            self._state = "armed"
            self._delay_ms = d
            self._freq_hz = hz
            self._target_lines = n
            self._rows = 0
            # Queue now; delay timer starts only after BALANCING is reached.
            self._armed_mono = None
            self._last_row_mono = None
            self._started_at = None
            self._finished_at = None
            self._last_error = None
            self._current_path = None
            return {
                "state": self._state,
                "delay_ms": self._delay_ms,
                "freq_hz": self._freq_hz,
                "target_lines": self._target_lines,
                "rows": self._rows,
                "started_at": self._started_at,
                "finished_at": self._finished_at,
                "latest_run": self._latest_run,
                "last_error": self._last_error,
            }

    def _start_capture_unlocked(self) -> None:
        ts = int(time.time())
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = self.out_dir / f"host_run_{ts}.csv"
        self._fh = path.open("w", encoding="utf-8")
        self._fh.write(self._header() + "\n")
        self._fh.flush()
        self._current_path = path
        self._started_at = time.time()
        self._last_row_mono = None
        self._state = "capturing"

    def ingest(self, status: Dict[str, Any]) -> None:
        if not status:
            return
        with self._lock:
            if self._state not in {"armed", "capturing"}:
                return
            mode = str(status.get("mode", ""))
            estop = str(status.get("estop", "1"))
            if mode != "BALANCING" or estop == "1":
                # Require continuous BALANCING window for queued-delay logic.
                if self._state == "armed":
                    self._armed_mono = None
                return
            if self._state == "armed":
                if self._armed_mono is None:
                    self._armed_mono = time.monotonic()
                elapsed_ms = (time.monotonic() - self._armed_mono) * 1000.0
                if elapsed_ms < float(self._delay_ms):
                    return
                try:
                    self._start_capture_unlocked()
                except Exception as exc:
                    self._last_error = str(exc)
                    self._finish_unlocked("failed")
                    return
            if self._state != "capturing" or self._fh is None:
                return
            period_s = 1.0 / max(self._freq_hz, 1.0)
            now_mono = time.monotonic()
            if self._last_row_mono is not None and (now_mono - self._last_row_mono) < period_s:
                return

            def g(key: str) -> str:
                v = status.get(key)
                return "" if v is None else str(v)

            row = ",".join(
                [
                    f"{time.time():.6f}",
                    g("mode"),
                    g("estop"),
                    g("ang"),
                    g("raw"),
                    g("gyro"),
                    g("set"),
                    g("out"),
                    g("pid"),
                    g("mot"),
                    g("wspd"),
                    g("wpos"),
                    g("kp"),
                    g("ki"),
                    g("kd"),
                    g("kv"),
                    g("kx"),
                    g("encL"),
                    g("encR"),
                    g("volRaw"),
                ]
            )
            self._fh.write(row + "\n")
            self._rows += 1
            self._last_row_mono = now_mono
            if self._rows >= self._target_lines:
                self._finish_unlocked("done")


def _commissioning_ai_context(commissioning: CommissioningManager) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "status": commissioning.status(),
        "artifacts": commissioning.artifacts(),
    }

    latest_metrics = out["artifacts"].get("latest_metrics")
    if isinstance(latest_metrics, str) and latest_metrics:
        p = pathlib.Path(latest_metrics)
        try:
            out["latest_metrics_json"] = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            out["latest_metrics_error"] = str(exc)

    latest_run = out["artifacts"].get("latest_run")
    if isinstance(latest_run, str) and latest_run:
        p = pathlib.Path(latest_run)
        try:
            out["latest_run_csv"] = _read_csv_tail(p, max_tail=80)
        except Exception as exc:
            out["latest_run_error"] = str(exc)

    return out


def _host_capture_ai_context(host_capture: HostCaptureManager) -> Dict[str, Any]:
    out: Dict[str, Any] = {"status": host_capture.status()}
    latest = out["status"].get("latest_run")
    if isinstance(latest, str) and latest:
        p = pathlib.Path(latest)
        if p.exists():
            try:
                out["latest_run_csv"] = _read_csv_tail(p, max_tail=80)
            except Exception as exc:
                out["latest_run_error"] = str(exc)
    return out


def _assistant_capabilities_context(*, allow_apply: bool) -> Dict[str, Any]:
    return {
        "can_read": [
            "cached_status",
            "control_state",
            "serial_health",
            "burst_status",
            "host_capture_latest_csv_tail",
            "commissioning_artifacts",
            "assistant_knowledge_pack",
            "config_snapshots",
        ],
        "can_apply_now": bool(allow_apply),
        "can_write": [
            "pid",
            "motion",
            "setpoint",
            "limits",
            "generate_unified_firmware_scaffold",
            "write_sketch_with_backup",
        ] if allow_apply else [],
        "confirm_first_for": [
            "arm/disarm",
            "cal_zero",
            "firmware_upload_or_flash",
            "power_state_changes",
        ],
    }


class AIProfileManager:
    def __init__(self, repo_root: pathlib.Path) -> None:
        self.path = repo_root / "app" / "bridge" / "ai_profiles.json"
        self._lock = threading.Lock()

    def _default_profile(self) -> Dict[str, Any]:
        now = time.time()
        return {
            "profile_id": "default",
            "label": "Default Copilot",
            "description": "Balanced safety and concise tuning guidance.",
            "instructions": (
                "Focus on practical next steps and concrete tuning deltas. "
                "Only include safety prechecks when the user asks or the action is high-risk. "
                "For non-high-risk requests, act immediately and avoid repeated confirmation prompts. "
                "If uncertain, ask at most one clarifying question."
            ),
            "policy": {
                "allow_auto_apply": True,
            },
            "created_at": now,
            "updated_at": now,
        }

    def _read_unlocked(self) -> Dict[str, Any]:
        if not self.path.exists():
            d = self._default_profile()
            return {"active_profile_id": d["profile_id"], "profiles": [d]}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            d = self._default_profile()
            return {"active_profile_id": d["profile_id"], "profiles": [d]}
        if not isinstance(raw, dict):
            d = self._default_profile()
            return {"active_profile_id": d["profile_id"], "profiles": [d]}
        profiles = raw.get("profiles")
        if not isinstance(profiles, list) or not profiles:
            d = self._default_profile()
            profiles = [d]
        active_profile_id = raw.get("active_profile_id")
        if not isinstance(active_profile_id, str) or not any(str(p.get("profile_id", "")) == active_profile_id for p in profiles):
            active_profile_id = str(profiles[0].get("profile_id", "default"))
        return {"active_profile_id": active_profile_id, "profiles": profiles}

    def _write_unlocked(self, data: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def list(self) -> Dict[str, Any]:
        with self._lock:
            data = self._read_unlocked()
            profiles = list(data.get("profiles", []))
            profiles.sort(key=lambda p: float(p.get("updated_at", 0.0) or 0.0), reverse=True)
            return {"active_profile_id": data.get("active_profile_id"), "profiles": profiles}

    def get_active(self) -> Dict[str, Any]:
        with self._lock:
            data = self._read_unlocked()
            active = str(data.get("active_profile_id", ""))
            for p in data.get("profiles", []):
                if str(p.get("profile_id", "")) == active:
                    return p
            return data.get("profiles", [self._default_profile()])[0]

    def save(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        label = str(profile.get("label", "")).strip()
        if not label:
            raise RuntimeError("ai_profile_label_required")
        description = str(profile.get("description", "")).strip()
        instructions = str(profile.get("instructions", "")).strip()
        policy_in = profile.get("policy")
        policy = policy_in if isinstance(policy_in, dict) else {}
        allow_auto_apply = bool(policy.get("allow_auto_apply", True))
        with self._lock:
            data = self._read_unlocked()
            profiles = list(data.get("profiles", []))
            now = time.time()
            pid = str(profile.get("profile_id", "")).strip() or secrets.token_urlsafe(8)
            next_profile = {
                "profile_id": pid,
                "label": label,
                "description": description,
                "instructions": instructions,
                "policy": {"allow_auto_apply": allow_auto_apply},
                "created_at": now,
                "updated_at": now,
            }
            replaced = False
            for i, p in enumerate(profiles):
                if str(p.get("profile_id", "")) == pid:
                    next_profile["created_at"] = float(p.get("created_at", now) or now)
                    profiles[i] = next_profile
                    replaced = True
                    break
            if not replaced:
                profiles.append(next_profile)
            active_profile_id = str(data.get("active_profile_id") or pid)
            out = {"active_profile_id": active_profile_id, "profiles": profiles}
            self._write_unlocked(out)
            return {"active_profile_id": active_profile_id, "profile": next_profile}

    def activate(self, profile_id: str) -> Dict[str, Any]:
        pid = str(profile_id).strip()
        if not pid:
            raise RuntimeError("ai_profile_id_required")
        with self._lock:
            data = self._read_unlocked()
            profiles = list(data.get("profiles", []))
            if not any(str(p.get("profile_id", "")) == pid for p in profiles):
                raise RuntimeError("ai_profile_not_found")
            out = {"active_profile_id": pid, "profiles": profiles}
            self._write_unlocked(out)
            return {"active_profile_id": pid}


class AssistantKnowledgeManager:
    def __init__(self, repo_root: pathlib.Path) -> None:
        self.root = repo_root
        self.base_dir = repo_root / "docs" / "assistant_knowledge"
        self.manifest_path = self.base_dir / "manifest.json"
        self._lock = threading.Lock()
        self._cache: Dict[str, Any] = {"ts": 0.0, "payload": None}
        self._cache_ttl_s = 2.0

    def _load_text(self, filename: str, max_chars: int = 7000) -> str:
        p = self.base_dir / filename
        if not p.exists() or not p.is_file():
            return ""
        try:
            txt = p.read_text(encoding="utf-8")
        except Exception:
            return ""
        if len(txt) > max_chars:
            return txt[:max_chars] + "\n\n[truncated]"
        return txt

    def _build_payload_unlocked(self) -> Dict[str, Any]:
        if not self.manifest_path.exists():
            return {"available": False, "error": "knowledge_manifest_missing"}
        try:
            man = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"available": False, "error": f"knowledge_manifest_invalid:{exc}"}
        if not isinstance(man, dict):
            return {"available": False, "error": "knowledge_manifest_not_object"}
        active = str(man.get("active_version", "")).strip()
        versions = man.get("versions", [])
        if not isinstance(versions, list):
            versions = []
        current = None
        for v in versions:
            if isinstance(v, dict) and str(v.get("version", "")) == active:
                current = v
                break
        if current is None and versions and isinstance(versions[0], dict):
            current = versions[0]
            active = str(current.get("version", "")).strip()
        if current is None:
            return {"available": False, "error": "knowledge_version_missing"}
        playbook_file = str(current.get("playbook_file", "")).strip()
        theory_file = str(current.get("theory_file", "")).strip()
        rules_file = str(current.get("rules_file", "")).strip()
        return {
            "available": True,
            "active_version": active,
            "label": str(current.get("label", "")),
            "created_at": str(current.get("created_at", "")),
            "changelog": list(current.get("changelog", [])) if isinstance(current.get("changelog", []), list) else [],
            "playbook_markdown": self._load_text(playbook_file),
            "theory_markdown": self._load_text(theory_file),
            "rules_markdown": self._load_text(rules_file),
        }

    def context(self) -> Dict[str, Any]:
        now = time.monotonic()
        with self._lock:
            ts = float(self._cache.get("ts", 0.0) or 0.0)
            if self._cache.get("payload") is not None and (now - ts) <= self._cache_ttl_s:
                return dict(self._cache["payload"])
            payload = self._build_payload_unlocked()
            self._cache = {"ts": now, "payload": payload}
            return dict(payload)


# Cache for .codexrules content to avoid repeated file reads
_codexrules_cache: Dict[str, Any] = {"content": None, "mtime": 0.0}


def _load_codexrules(repo_root: pathlib.Path) -> str:
    """
    Load .codexrules from repo root if it exists.
    Caches content and reloads only if file modified.
    """
    global _codexrules_cache
    rules_path = repo_root / ".codexrules"
    if not rules_path.exists():
        return ""
    try:
        mtime = rules_path.stat().st_mtime
        if _codexrules_cache["mtime"] == mtime and _codexrules_cache["content"] is not None:
            return str(_codexrules_cache["content"])
        content = rules_path.read_text(encoding="utf-8").strip()
        _codexrules_cache = {"content": content, "mtime": mtime}
        logger.info(f"Loaded .codexrules ({len(content)} chars)")
        return content
    except Exception as e:
        logger.warning(f"Failed to load .codexrules: {e}")
        return ""


def _resolve_system_prompt(profile: Dict[str, Any], *, allow_apply: bool, repo_root: Optional[pathlib.Path] = None) -> str:
    """
    Build system prompt for Codex agent.
    
    Priority (later overrides earlier):
    1. .codexrules file (project-level rules, like .windsurfrules)
    2. Profile instructions (per-robot customization)
    3. Action policy block (apply permissions)
    """
    # Load project-level rules from .codexrules
    codexrules = ""
    if repo_root:
        codexrules = _load_codexrules(repo_root)
    
    # Fallback base prompt if no .codexrules exists
    if not codexrules:
        codexrules = (
            "You are Codex for UpRight.os, a robotics tuning copilot. "
            "Be concise, practical, and decisive. Never claim actions already executed unless tool output confirms it. "
            "Use plain English and short bullet points. Never output raw JSON to the user. "
            "Default behavior: if user asks for a concrete non-high-risk change, execute it now instead of asking repeated confirmations. "
            "Ask for confirmation only for high-risk actions: arm/disarm, cal-zero, firmware upload/flash, or power-state changes. "
            "Do not include routine precheck lists unless user asks for a checklist or action is high-risk. "
        )
    
    # Profile-specific instructions (per-robot customization)
    custom = str(profile.get("instructions", "") or "").strip()
    
    # Action policy block
    policy = profile.get("policy", {})
    policy_allow = bool(policy.get("allow_auto_apply", True)) if isinstance(policy, dict) else True
    can_apply = allow_apply and policy_allow
    if can_apply:
        action_block = (
            "If user asks to apply/modify now, include exactly one machine-readable line: "
            "UPRIGHT_APPLY_JSON:{\"pid\":{\"kp\":..,\"ki\":..,\"kd\":..},\"motion\":{\"kv\":..,\"kx\":..},"
            "\"setpoint\":{\"deg\":..},\"limits\":{\"out_max\":..,\"tip_deg\":..,\"i_max\":..},"
            "\"unified\":{\"profile\":{...},\"sketch_name\":\"...\"},"
            "\"sketch\":{\"path\":\"/optional/path.ino\",\"content\":\"...full file content...\"}} "
            "using only keys you want changed. "
            "Use unified/sketch only when user explicitly asks to generate or edit firmware files. "
            "Then explain the result in plain English."
        )
    else:
        action_block = "Do not request direct hardware actions; provide recommendations only."
    
    return "\n\n".join(x for x in [codexrules, custom, action_block] if x).strip()


class RobotProfilesManager:
    def __init__(self, repo_root: pathlib.Path) -> None:
        self.path = repo_root / "app" / "bridge" / "robot_profiles.json"
        self._lock = threading.Lock()

    def _read(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"active_profile_id": None, "profiles": []}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"active_profile_id": None, "profiles": []}
        if not isinstance(raw, dict):
            return {"active_profile_id": None, "profiles": []}
        profiles = raw.get("profiles")
        if not isinstance(profiles, list):
            profiles = []
        active_profile_id = raw.get("active_profile_id")
        if active_profile_id is not None and not isinstance(active_profile_id, str):
            active_profile_id = None
        return {"active_profile_id": active_profile_id, "profiles": profiles}

    def _write(self, data: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def list(self) -> Dict[str, Any]:
        with self._lock:
            data = self._read()
            profiles = list(data.get("profiles", []))
            profiles.sort(key=lambda p: float(p.get("updated_at", 0) or 0), reverse=True)
            return {"active_profile_id": data.get("active_profile_id"), "profiles": profiles}

    def save(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        label = str(profile.get("label", "")).strip()
        if not label:
            raise RuntimeError("profile_label_required")
        chassis = str(profile.get("chassis", "custom")).strip() or "custom"
        with self._lock:
            data = self._read()
            profiles = list(data.get("profiles", []))
            now = time.time()
            pid = str(profile.get("profile_id", "")).strip() or secrets.token_urlsafe(8)
            next_profile = {
                "profile_id": pid,
                "label": label,
                "chassis": chassis,
                "board": profile.get("board", {}) if isinstance(profile.get("board"), dict) else {},
                "parts": profile.get("parts", {}) if isinstance(profile.get("parts"), dict) else {},
                "pinmap": profile.get("pinmap", {}) if isinstance(profile.get("pinmap"), dict) else {},
                "firmware": profile.get("firmware", {}) if isinstance(profile.get("firmware"), dict) else {},
                "limits": profile.get("limits", {}) if isinstance(profile.get("limits"), dict) else {},
                "calibration": profile.get("calibration", {}) if isinstance(profile.get("calibration"), dict) else {},
                "probe": profile.get("probe", {}) if isinstance(profile.get("probe"), dict) else {},
                "validation": profile.get("validation", {}) if isinstance(profile.get("validation"), dict) else {},
                "created_at": float(profile.get("created_at", now) or now),
                "updated_at": now,
            }
            replaced = False
            for i, p in enumerate(profiles):
                if str(p.get("profile_id", "")) == pid:
                    created_at = float(p.get("created_at", now) or now)
                    next_profile["created_at"] = created_at
                    profiles[i] = next_profile
                    replaced = True
                    break
            if not replaced:
                profiles.append(next_profile)
            active_profile_id = data.get("active_profile_id") or pid
            out = {"active_profile_id": active_profile_id, "profiles": profiles}
            self._write(out)
            return {"active_profile_id": active_profile_id, "profile": next_profile}

    def activate(self, profile_id: str) -> Dict[str, Any]:
        pid = str(profile_id).strip()
        if not pid:
            raise RuntimeError("profile_id_required")
        with self._lock:
            data = self._read()
            profiles = list(data.get("profiles", []))
            if not any(str(p.get("profile_id", "")) == pid for p in profiles):
                raise RuntimeError("profile_not_found")
            out = {"active_profile_id": pid, "profiles": profiles}
            self._write(out)
            return {"active_profile_id": pid}

    def delete(self, profile_id: str) -> Dict[str, Any]:
        pid = str(profile_id).strip()
        if not pid:
            raise RuntimeError("profile_id_required")
        with self._lock:
            data = self._read()
            profiles = [p for p in list(data.get("profiles", [])) if str(p.get("profile_id", "")) != pid]
            active = data.get("active_profile_id")
            if active == pid:
                active = str(profiles[0].get("profile_id")) if profiles else None
            out = {"active_profile_id": active, "profiles": profiles}
            self._write(out)
            return {"active_profile_id": active, "profiles": profiles}

    def validate(self, gateway: NanoSerialGateway, *, duration_s: float = 12.0, sample_interval_s: float = 0.25) -> Dict[str, Any]:
        duration_s = max(2.0, min(duration_s, 90.0))
        sample_interval_s = max(0.1, min(sample_interval_s, 1.0))

        connect = run_connect_probe(gateway)
        serial = gateway.health()
        compat = connect.get("compat", {}) if isinstance(connect, dict) else {}

        missing_fields = list((compat.get("missing_fields") or [])) if isinstance(compat, dict) else []
        has_schema = ("ang" not in missing_fields) and ("raw" not in missing_fields) and (not any("gyro" in str(f) for f in missing_fields))

        required_cmds = ["GET", "ARM", "DISARM", "PID", "MOTION", "SETPOINT", "CAL ZERO"]
        supported_cmds = set(connect.get("commands", []) if isinstance(connect, dict) else [])
        missing_cmds = [c for c in required_cmds if c not in supported_cmds]

        samples = 0
        fresh_hits = 0
        q_ok_hits = 0
        timeout_start = int(((serial.get("serial_metrics") or {}).get("timeouts", 0)) or 0)
        until = time.monotonic() + duration_s
        while time.monotonic() < until:
            h = gateway.health()
            samples += 1
            age_ms = h.get("last_status_age_ms")
            qd = int(h.get("queue_depth", 0) or 0)
            if isinstance(age_ms, (float, int)) and float(age_ms) < 500.0:
                fresh_hits += 1
            if qd <= 2:
                q_ok_hits += 1
            time.sleep(sample_interval_s)
        end = gateway.health()
        timeout_end = int(((end.get("serial_metrics") or {}).get("timeouts", 0)) or 0)
        timeout_delta = max(0, timeout_end - timeout_start)

        freshness_ratio = (fresh_hits / samples) if samples else 0.0
        queue_ratio = (q_ok_hits / samples) if samples else 0.0

        checks = [
            {
                "id": "compat_fields",
                "label": "Compatibility fields present (ang/raw/gyro)",
                "ok": bool(has_schema),
                "detail": "missing=" + (",".join(missing_fields) if missing_fields else "none"),
            },
            {
                "id": "commands_supported",
                "label": "Required commands supported",
                "ok": len(missing_cmds) == 0,
                "detail": "missing=" + (",".join(missing_cmds) if missing_cmds else "none"),
            },
            {
                "id": "telemetry_freshness",
                "label": "Telemetry freshness (<500ms for >=95% samples)",
                "ok": freshness_ratio >= 0.95,
                "detail": f"fresh_ratio={freshness_ratio:.3f} samples={samples}",
            },
            {
                "id": "queue_depth",
                "label": "Serial queue depth healthy (<=2 for >=95% samples)",
                "ok": queue_ratio >= 0.95,
                "detail": f"queue_ratio={queue_ratio:.3f} samples={samples}",
            },
            {
                "id": "timeouts",
                "label": "Serial timeouts <= 1 during validation window",
                "ok": timeout_delta <= 1,
                "detail": f"timeout_delta={timeout_delta}",
            },
        ]
        ok = all(bool(c["ok"]) for c in checks)
        score_pct = int(round(100.0 * (sum(1 for c in checks if c["ok"]) / max(1, len(checks)))))

        return {
            "ok": ok,
            "score_pct": score_pct,
            "checks": checks,
            "generated_at": time.time(),
            "duration_s": duration_s,
            "sample_interval_s": sample_interval_s,
            "connect": connect,
            "compat": compat,
            "serial": end,
        }


class TelemetryHub:
    def __init__(self, gateway: NanoSerialGateway, control: BridgeControlState, host_capture: HostCaptureManager, host: str, port: int) -> None:
        self.gateway = gateway
        self.control = control
        self.host_capture = host_capture
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
                cached_status: Dict[str, Any] = {}
                queue_depth = 0
                try:
                    h = self.gateway.health()
                    cached_status = dict(h.get("last_status", {}))
                    queue_depth = int(h.get("queue_depth", 0) or 0)
                except Exception:
                    cached_status = {}
                    queue_depth = 0
                payload = {
                    "ts": time.time(),
                    "status": cached_status,
                    "control": self.control.snapshot(),
                }
                try:
                    self.host_capture.ingest(cached_status)
                except Exception:
                    pass
                if queue_depth > 6:
                    payload["warn"] = "serial_queue_backpressure"

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
                # 8-10 Hz telemetry is sufficient for HUD responsiveness without monopolizing serial lock time.
                await asyncio.sleep(0.12)


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
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS password_resets (
                  token_hash TEXT PRIMARY KEY,
                  user_id INTEGER NOT NULL,
                  created_at REAL NOT NULL,
                  expires_at REAL NOT NULL,
                  used_at REAL,
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

    def request_password_reset(self, email: str) -> Dict[str, Any]:
        em = self._normalize_email(email)
        now = time.time()
        with self._lock, self._connect() as con:
            user = con.execute("SELECT id FROM users WHERE email=?", (em,)).fetchone()
            # Do not reveal account existence.
            if not user:
                return {"accepted": True, "delivery": "local_token", "reset_token": None, "expires_in_s": 900}

            token = secrets.token_urlsafe(24)
            tokh = self._hash_token(token)
            exp = now + 900
            con.execute("DELETE FROM password_resets WHERE user_id=?", (int(user["id"]),))
            con.execute(
                "INSERT OR REPLACE INTO password_resets(token_hash,user_id,created_at,expires_at,used_at) VALUES(?,?,?,?,NULL)",
                (tokh, int(user["id"]), now, exp),
            )
            con.commit()
            return {"accepted": True, "delivery": "local_token", "reset_token": token, "expires_in_s": 900}

    def reset_password(self, email: str, token: str, new_password: str) -> Dict[str, Any]:
        em = self._normalize_email(email)
        tok = token.strip()
        if len(new_password) < 8:
            raise RuntimeError("weak_password")
        if not tok:
            raise RuntimeError("invalid_reset_token")

        tokh = self._hash_token(tok)
        now = time.time()
        salt = secrets.token_bytes(16)
        pwh = self._hash_password(new_password, salt)

        with self._lock, self._connect() as con:
            user = con.execute("SELECT id FROM users WHERE email=?", (em,)).fetchone()
            if not user:
                raise RuntimeError("invalid_reset_token")
            uid = int(user["id"])

            row = con.execute(
                """
                SELECT token_hash FROM password_resets
                WHERE token_hash=? AND user_id=? AND used_at IS NULL AND expires_at>=?
                """,
                (tokh, uid, now),
            ).fetchone()
            if not row:
                raise RuntimeError("invalid_reset_token")

            con.execute("UPDATE users SET pw_salt=?, pw_hash=? WHERE id=?", (salt, pwh, uid))
            con.execute("UPDATE password_resets SET used_at=? WHERE token_hash=?", (now, tokh))
            con.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
            con.commit()
        return {"ok": True}


def _normalize_cmd(cmd: str) -> str:
    return " ".join(cmd.strip().split()).upper()


def _blocked_while_latched(cmd: str) -> bool:
    c = _normalize_cmd(cmd)
    safe_prefixes = ("GET", "DISARM", "HELP", "LOGCSV", "LOGT")
    return not c.startswith(safe_prefixes)


# ============================================================================
# Telemetry Contract v2 Readiness
# ============================================================================

# v1 required fields (unchanged)
V1_REQUIRED_FIELDS = ("mode", "ang", "raw", "out", "kp", "ki", "kd", "set")
V1_GYRO_ALIASES = ("gyro", "gyr", "gx")

# v2 readiness fields (backward-compatible gate)
V2_READINESS_FIELDS = ("gyro_bias", "vel_meas", "outer_loop_enabled")

# v2 factory telemetry fields (strict factory standard)
V2_FACTORY_FIELDS = (
    "gyro_bias", "accel_level_offset", "upright_trim",
    "vel_meas", "vel_target", "outer_loop_enabled",
    "target_angle_from_velocity",
    "motor_l_trim", "motor_r_trim", "drift_diag_state",
)
# Backward-compatible alias used by tests/docs from earlier revision.
V2_OPTIONAL_FIELDS = V2_FACTORY_FIELDS


def detect_contract_readiness(status: Dict[str, Any]) -> Dict[str, Any]:
    """
    Detect telemetry contract version and v2 readiness.
    
    Returns dict with:
        - contract_version_detected: "v1" or "v2"
        - v1_ok: bool
        - v2_ready: bool
        - v2_missing_fields: list of missing v2 readiness fields
        - v2_present_fields: list of v2 optional fields that are present
        - readiness_checks: list of {check, status, detail}
    """
    if not status:
        return {
            "contract_version_detected": "unknown",
            "v1_ok": False,
            "v2_ready": False,
            "v2_missing_fields": list(V2_READINESS_FIELDS),
            "v2_factory_ready": False,
            "v2_factory_missing_fields": list(V2_FACTORY_FIELDS),
            "v2_present_fields": [],
            "readiness_checks": [
                {"check": "telemetry_available", "status": "fail", "detail": "No telemetry data"}
            ],
        }

    checks: list[Dict[str, Any]] = []

    # v1 check
    v1_missing = [f for f in V1_REQUIRED_FIELDS if f not in status]
    has_gyro = any(alias in status for alias in V1_GYRO_ALIASES)
    if not has_gyro:
        v1_missing.append("gyro|gyr|gx")
    v1_ok = len(v1_missing) == 0

    checks.append({
        "check": "v1_required_fields",
        "status": "pass" if v1_ok else "fail",
        "detail": f"Missing: {v1_missing}" if v1_missing else "All v1 fields present",
    })

    # v2 readiness check
    v2_missing = [f for f in V2_READINESS_FIELDS if f not in status]
    if not has_gyro and "gyro|gyr|gx" not in v2_missing:
        # Keep backward-compatible diagnostics: missing gyro alias should surface
        # in readiness output even though it is part of v1 base contract.
        v2_missing.append("gyro|gyr|gx")
    v2_ready = len(v2_missing) == 0
    v2_factory_missing = [f for f in V2_FACTORY_FIELDS if f not in status]
    v2_factory_ready = len(v2_factory_missing) == 0

    checks.append({
        "check": "v2_readiness_fields",
        "status": "pass" if v2_ready else "warn",
        "detail": f"Missing: {v2_missing}" if v2_missing else "All v2 readiness fields present",
    })

    # v2 optional fields present
    v2_present = [f for f in V2_FACTORY_FIELDS if f in status]

    checks.append({
        "check": "v2_optional_fields",
        "status": "pass" if v2_present else "warn",
        "detail": f"Present: {v2_present}" if v2_present else "No v2 optional fields present",
    })

    checks.append({
        "check": "v2_factory_fields",
        "status": "pass" if v2_factory_ready else "warn",
        "detail": f"Missing: {v2_factory_missing}" if v2_factory_missing else "All factory v2 fields present",
    })

    # Calibration readiness
    has_gyro_bias = "gyro_bias" in status
    has_accel_offset = "accel_level_offset" in status
    has_upright_trim = "upright_trim" in status
    calibration_ready = has_gyro_bias and has_accel_offset

    checks.append({
        "check": "calibration_data",
        "status": "pass" if calibration_ready else "warn",
        "detail": "Gyro bias and accel offset calibrated" if calibration_ready else "Calibration not complete",
    })

    # Outer loop readiness
    has_velocity = "vel_meas" in status
    outer_enabled = status.get("outer_loop_enabled", False)

    checks.append({
        "check": "outer_loop_ready",
        "status": "pass" if (has_velocity and outer_enabled) else "warn",
        "detail": "Velocity feedback and outer loop active" if (has_velocity and outer_enabled) else "Outer loop not active or no velocity data",
    })

    return {
        "contract_version_detected": "v2" if v2_ready else "v1",
        "v1_ok": v1_ok,
        "v2_ready": v2_ready,
        "v2_missing_fields": v2_missing,
        "v2_factory_ready": v2_factory_ready,
        "v2_factory_missing_fields": v2_factory_missing,
        "v2_present_fields": v2_present,
        "readiness_checks": checks,
    }


def run_compat_probe(gateway: NanoSerialGateway) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "ok": False,
        "profile": "unknown",
        "firmware_id": None,
        "required_fields": ["mode", "ang", "raw", "gyro|gyr|gx", "out", "kp", "ki", "kd", "set"],
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
    required_base = ("mode", "ang", "raw", "out", "kp", "ki", "kd", "set")
    has_gyro = any(k in status for k in ("gyro", "gyr", "gx"))
    missing_fields = [f for f in required_base if f not in status]
    if not has_gyro:
        missing_fields.append("gyro|gyr|gx")
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

    # If HELP output is unusable (e.g., generic "OK"), do not fail compat on
    # command discovery; fall back to schema-based validation.
    if len(supported) == 0:
        report["warnings"].append("help_probe_unusable_command_catalog")
        missing = []

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

    # v2 readiness (additive, non-breaking)
    v2_readiness = detect_contract_readiness(status)
    report["contract_version_detected"] = v2_readiness["contract_version_detected"]
    report["v1_ok"] = v2_readiness["v1_ok"]
    report["v2_ready"] = v2_readiness["v2_ready"]
    report["v2_missing_fields"] = v2_readiness["v2_missing_fields"]
    report["v2_factory_ready"] = v2_readiness["v2_factory_ready"]
    report["v2_factory_missing_fields"] = v2_readiness["v2_factory_missing_fields"]
    report["v2_present_fields"] = v2_readiness["v2_present_fields"]
    report["readiness_checks"] = v2_readiness["readiness_checks"]

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
    has_gyro = any(k in status for k in ("gyro", "gyr", "gx"))
    report["status_schema_ok"] = all(f in status for f in required_fields) and has_gyro
    report["components"]["imu"] = "ang" in status and "raw" in status and has_gyro
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
    if not has_gyro:
        report["warnings"].append("kalman telemetry missing gyro rate field (expected one of: gyro/gyr/gx)")
    if report["missing_commands"]:
        report["warnings"].append("some expected commands were not found in HELP output")

    # v2 readiness (additive, non-breaking)
    v2_readiness = detect_contract_readiness(status)
    report["contract_version_detected"] = v2_readiness["contract_version_detected"]
    report["v1_ok"] = v2_readiness["v1_ok"]
    report["v2_ready"] = v2_readiness["v2_ready"]
    report["v2_missing_fields"] = v2_readiness["v2_missing_fields"]
    report["v2_factory_ready"] = v2_readiness["v2_factory_ready"]
    report["v2_factory_missing_fields"] = v2_readiness["v2_factory_missing_fields"]
    report["v2_present_fields"] = v2_readiness["v2_present_fields"]
    report["readiness_checks"] = v2_readiness["readiness_checks"]

    # Recommended next action for v2 readiness
    if not v2_readiness["v2_ready"]:
        missing = v2_readiness["v2_missing_fields"]
        if "gyro_bias" in missing:
            report["v2_recommended_action"] = "Run gyro calibration to establish sensor bias"
        elif "vel_meas" in missing:
            report["v2_recommended_action"] = "Firmware update needed for velocity feedback"
        elif "outer_loop_enabled" in missing:
            report["v2_recommended_action"] = "Enable outer velocity loop for anti-drift"
        else:
            report["v2_recommended_action"] = "Complete v2 setup for anti-drift capabilities"
    else:
        report["v2_recommended_action"] = None

    return report


def _latest_docs_folder(generated_root: pathlib.Path) -> Optional[pathlib.Path]:
    try:
        candidates = [p for p in generated_root.glob("*_docs*") if p.is_dir()]
    except Exception:
        return None
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _validate_docs_artifacts(docs_dir: pathlib.Path) -> Dict[str, Any]:
    required = [
        "control_flow.mmd",
        "state_machine.mmd",
        "hardware_block.mmd",
        "pin_mapping.mmd",
        "pin_assignment.md",
        "command_api_map.md",
        "source_report.md",
    ]
    missing: list[str] = []
    invalid: list[str] = []
    for name in required:
        path = docs_dir / name
        if not path.exists() or not path.is_file():
            missing.append(name)
            continue
        try:
            txt = path.read_text(encoding="utf-8").strip()
        except Exception:
            invalid.append(name)
            continue
        if not txt:
            invalid.append(name)
            continue
        if name.endswith(".mmd"):
            first = txt.splitlines()[0].strip().lower()
            if not (
                first.startswith("flowchart")
                or first.startswith("graph")
                or first.startswith("statediagram-v2")
                or first.startswith("classdiagram")
            ):
                invalid.append(name)
    ok = not missing and not invalid
    return {"ok": ok, "missing": missing, "invalid": invalid, "required": required}


def build_overwatch_report(
    *,
    gateway: NanoSerialGateway,
    firmware: FirmwareManager,
    compat: Optional[Dict[str, Any]] = None,
    connect: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    checks: list[Dict[str, Any]] = []
    actions: list[str] = []

    def add_check(check_id: str, label: str, status: str, detail: str, evidence: str = "") -> None:
        checks.append({"id": check_id, "label": label, "status": status, "detail": detail, "evidence": evidence})
        if status != "pass":
            actions.append(f"{label}: {detail}")

    health = gateway.health()
    connected = bool(health.get("connected", False))
    add_check(
        "serial_connected",
        "Serial Link",
        "pass" if connected else "fail",
        "Bridge has active serial session" if connected else "Bridge is not connected to serial device",
        f"port={health.get('port', '')}",
    )

    status = dict(health.get("last_status", {}))
    readiness = detect_contract_readiness(status)
    v1_ok = bool(readiness.get("v1_ok", False))
    v2_ready = bool(readiness.get("v2_ready", False))
    add_check(
        "telemetry_contract_v1",
        "Telemetry Contract",
        "pass" if v1_ok else "fail",
        "Required telemetry fields present" if v1_ok else "Required telemetry fields missing",
        f"version={readiness.get('contract_version_detected', 'unknown')}",
    )
    add_check(
        "antidrift_v2_ready",
        "Anti-Drift Readiness",
        "pass" if v2_ready else ("warn" if v1_ok else "fail"),
        "v2 anti-drift fields present" if v2_ready else "v2 anti-drift fields incomplete",
        f"missing={','.join(readiness.get('v2_missing_fields', [])) or 'none'}",
    )

    compat_report = compat if isinstance(compat, dict) else {}
    missing_commands = (
        list(compat_report.get("missing_commands", []))
        if isinstance(compat_report.get("missing_commands", []), list)
        else []
    )
    add_check(
        "command_contract",
        "Command Contract",
        "pass" if not missing_commands else "fail",
        "Required command set detected" if not missing_commands else "Missing required commands",
        ",".join(missing_commands) if missing_commands else "none",
    )

    fw_status = firmware.status()
    sketch_path = pathlib.Path(str(fw_status.get("defaults", {}).get("sketch", "")))
    sketch_exists = sketch_path.exists() and sketch_path.is_file()
    sketch_mtime = sketch_path.stat().st_mtime if sketch_exists else None
    add_check(
        "sketch_present",
        "Sketch Presence",
        "pass" if sketch_exists else "fail",
        "Active sketch file found" if sketch_exists else "No active sketch file found",
        str(sketch_path),
    )

    docs_dir = _latest_docs_folder(firmware._generated_root)
    docs_exists = docs_dir is not None and docs_dir.exists()
    docs_check = _validate_docs_artifacts(docs_dir) if docs_exists and docs_dir is not None else {"ok": False, "missing": [], "invalid": [], "required": []}
    docs_mtime = docs_dir.stat().st_mtime if docs_exists and docs_dir is not None else None
    docs_fresh = bool(sketch_mtime is not None and docs_mtime is not None and docs_mtime >= sketch_mtime)
    docs_ok = bool(docs_exists and docs_check.get("ok", False) and docs_fresh)
    docs_detail = "Docs pack is synced to sketch" if docs_ok else "Docs pack missing, invalid, or stale vs sketch"
    docs_evidence = f"docs={str(docs_dir) if docs_dir else 'none'}; fresh={str(docs_fresh).lower()}; missing={','.join(docs_check.get('missing', [])) or 'none'}; invalid={','.join(docs_check.get('invalid', [])) or 'none'}"
    add_check("docs_sync", "Docs Integrity", "pass" if docs_ok else "fail", docs_detail, docs_evidence)

    gyro_present = any(k in status for k in ("gyro", "gyr", "gx"))
    hud_ok = ("ang" in status) and ("raw" in status) and gyro_present
    add_check(
        "hud_sensor_contract",
        "HUD Sensor Contract",
        "pass" if hud_ok else "fail",
        "HUD sensor fields available" if hud_ok else "HUD fields missing (need ang/raw/gyro alias)",
        f"fields={','.join(sorted(status.keys())[:12])}",
    )

    loop_hz = _first_float(status, "loop_hz", "loopHz", "hz")
    loop_status = "pass" if (loop_hz is not None and loop_hz >= 45.0) else ("warn" if (loop_hz is not None and loop_hz >= 20.0) else "fail")
    add_check(
        "loop_rate",
        "Loop Feed Quality",
        loop_status,
        "Loop rate optimal" if loop_status == "pass" else ("Loop rate sufficient but not optimal" if loop_status == "warn" else "Loop rate too low"),
        f"loop_hz={loop_hz if loop_hz is not None else 'n/a'}",
    )

    pass_count = sum(1 for c in checks if c["status"] == "pass")
    warn_count = sum(1 for c in checks if c["status"] == "warn")
    fail_count = sum(1 for c in checks if c["status"] == "fail")
    denom = max(1, len(checks))
    score_pct = int(round(((pass_count + 0.5 * warn_count) / denom) * 100))
    all_green = fail_count == 0 and warn_count == 0
    overall = "pass" if all_green else ("warn" if fail_count == 0 else "fail")

    connect_report = connect if isinstance(connect, dict) else {}
    return {
        "ok": all_green,
        "overall": overall,
        "score_pct": score_pct,
        "generated_at": time.time(),
        "checks": checks,
        "counts": {"pass": pass_count, "warn": warn_count, "fail": fail_count, "total": len(checks)},
        "actions": actions[:8],
        "contract_version_detected": readiness.get("contract_version_detected", "unknown"),
        "connect_confidence_pct": int(connect_report.get("confidence_pct", 0) or 0) if connect_report else 0,
        "docs": {
            "latest_folder": str(docs_dir) if docs_dir else None,
            "exists": docs_exists,
            "fresh": docs_fresh,
            "check": docs_check,
            "sketch_path": str(sketch_path),
        },
    }


def build_handler(
    gateway: NanoSerialGateway,
    control: BridgeControlState,
    commissioning: CommissioningManager,
    host_capture: HostCaptureManager,
    firmware: FirmwareManager,
    ai: AIManager,
    ai_profiles: AIProfileManager,
    knowledge: AssistantKnowledgeManager,
    auth: AuthManager,
    profiles: RobotProfilesManager,
    config_history: ConfigHistoryManager,
    telemetry_port: int,
    codex_agent: Optional[Any] = None,
):
    probe_cache_lock = threading.Lock()
    probe_cache: Dict[str, Dict[str, Any]] = {
        "compat": {"ts": 0.0, "report": None},
        "connect": {"ts": 0.0, "report": None},
        "overwatch": {"ts": 0.0, "report": None},
    }

    def cached_probe(kind: str) -> Optional[Dict[str, Any]]:
        with probe_cache_lock:
            node = probe_cache.get(kind, {})
            ts = float(node.get("ts", 0.0) or 0.0)
            report = node.get("report")
        ttl_s = 4.0 if kind == "compat" else 2.0
        if report is not None and (time.monotonic() - ts) <= ttl_s:
            return report
        return None

    def store_probe(kind: str, report: Dict[str, Any]) -> None:
        with probe_cache_lock:
            probe_cache[kind] = {"ts": time.monotonic(), "report": report}

    def burst_status() -> Dict[str, Any]:
        lines = gateway.recent_lines(800)
        burst_events = [ln for ln in lines if ln.startswith("BURSTCSV")]
        csv_recent = sum(1 for ln in lines if ln.startswith("CSV,"))
        host = host_capture.status()
        state = "idle"
        if burst_events:
            last = burst_events[-1]
            if "DONE" in last:
                state = "done"
            elif "CANCELED" in last:
                state = "canceled"
            elif "STABLE" in last:
                state = "stable"
            elif "ARMED" in last:
                state = "armed"
        else:
            hs = str(host.get("state", "idle"))
            if hs in {"armed", "capturing", "done", "failed"}:
                state = hs
        return {
            "state": state,
            "last_event": burst_events[-1] if burst_events else None,
            "events_recent": burst_events[-12:],
            "csv_recent": csv_recent,
            "host_capture": host,
        }

    def history_with_reply(history: list[Dict[str, Any]], reply: str) -> list[Dict[str, Any]]:
        out = list(history)
        for i in range(len(out) - 1, -1, -1):
            node = out[i]
            if str(node.get("role", "")) == "assistant":
                repl = dict(node)
                repl["text"] = reply
                out[i] = repl
                break
        return out

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
                    # Keep /status non-blocking: return cached status only.
                    # Serial worker drains spontaneous STATUS lines in background.
                    st = dict(gateway.health().get("last_status", {}))
                    return _json(self, 200, {"ok": True, "status": st, "control": control.snapshot()})
                if u.path == "/diag/serial":
                    return _json(
                        self,
                        200,
                        {
                            "ok": True,
                            "serial": gateway.health(),
                            "control": control.snapshot(),
                        },
                    )
                if u.path == "/lines":
                    q = parse_qs(u.query)
                    n = int(q.get("n", ["100"])[0])
                    return _json(self, 200, {"ok": True, "lines": gateway.recent_lines(n)})
                if u.path == "/burst/status":
                    return _json(self, 200, {"ok": True, "burst": burst_status()})
                if u.path == "/commissioning/status":
                    return _json(self, 200, {"ok": True, "commissioning": commissioning.status()})
                if u.path == "/commissioning/artifacts":
                    return _json(self, 200, {"ok": True, "artifacts": commissioning.artifacts()})
                if u.path == "/firmware/status":
                    return _json(self, 200, {"ok": True, "firmware": firmware.status()})
                if u.path == "/firmware/unified-schema":
                    return _json(self, 200, {"ok": True, "schema": firmware.unified_schema()})
                if u.path == "/ai/status":
                    tok = _extract_auth_token(self)
                    me = auth.me(tok)
                    if not me:
                        return _json(self, 200, {"ok": True, "ai": ai.status(configured=False, model="gpt-5-mini", session_key="anon"), "history": [], "threads": []})
                    model = str(me.get("openai_model") or "gpt-5-mini")
                    configured = bool(me.get("openai_configured"))
                    skey = f"user:{me['id']}"
                    st = ai.status(configured=configured, model=model, session_key=skey)
                    tid = st.get("active_thread_id")
                    return _json(self, 200, {"ok": True, "ai": st, "history": ai.history(skey, tid)[-80:], "threads": ai.list_threads(skey)})
                if u.path == "/ai/threads":
                    tok = _extract_auth_token(self)
                    me = auth.me(tok)
                    if not me:
                        return _json(self, 401, {"ok": False, "error": "unauthenticated"})
                    skey = f"user:{me['id']}"
                    return _json(
                        self,
                        200,
                        {
                            "ok": True,
                            "threads": ai.list_threads(skey),
                            "ai": ai.status(
                                configured=bool(me.get("openai_configured")),
                                model=str(me.get("openai_model") or "gpt-5-mini"),
                                session_key=skey,
                            ),
                        },
                    )
                if u.path == "/ai/profiles":
                    tok = _extract_auth_token(self)
                    me = auth.me(tok)
                    if not me:
                        return _json(self, 401, {"ok": False, "error": "unauthenticated"})
                    return _json(self, 200, {"ok": True, "profiles": ai_profiles.list()})
                if u.path == "/ai/knowledge":
                    tok = _extract_auth_token(self)
                    me = auth.me(tok)
                    if not me:
                        return _json(self, 401, {"ok": False, "error": "unauthenticated"})
                    return _json(self, 200, {"ok": True, "knowledge": knowledge.context()})
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
                    cached = cached_probe("compat")
                    if cached is not None:
                        return _json(self, 200, {"ok": True, "compat": cached})
                    # Throttle probe pressure when queue is already busy.
                    if int(gateway.health().get("queue_depth", 0) or 0) > 2:
                        fallback = {
                            "ok": False,
                            "profile": "unknown",
                            "firmware_id": None,
                            "required_fields": [],
                            "missing_fields": [],
                            "supported_commands": [],
                            "missing_commands": [],
                            "warnings": ["compat_probe_throttled_queue_busy"],
                        }
                        return _json(self, 200, {"ok": True, "compat": fallback})
                    out = run_compat_probe(gateway)
                    store_probe("compat", out)
                    return _json(self, 200, {"ok": True, "compat": out})
                if u.path == "/probe/connect":
                    cached = cached_probe("connect")
                    if cached is not None:
                        return _json(self, 200, {"ok": True, "probe": cached})
                    if int(gateway.health().get("queue_depth", 0) or 0) > 2:
                        fallback = {
                            "ok": False,
                            "connected": bool(gateway.health().get("connected", False)),
                            "port": str(gateway.health().get("port", "")),
                            "baud": int(gateway.health().get("baud", 0) or 0),
                            "port_meta": _get_port_meta(str(gateway.health().get("port", ""))),
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
                            "warnings": ["connect_probe_throttled_queue_busy"],
                            "next_questions": [],
                            "compat": None,
                        }
                        return _json(self, 200, {"ok": True, "probe": fallback})
                    out = run_connect_probe(gateway)
                    store_probe("connect", out)
                    return _json(self, 200, {"ok": True, "probe": out})
                if u.path == "/overwatch/status":
                    q = parse_qs(u.query)
                    force_refresh = str((q.get("refresh", ["0"]) or ["0"])[0]).strip().lower() in {"1", "true", "yes"}
                    if not force_refresh:
                        cached = cached_probe("overwatch")
                        if cached is not None:
                            return _json(self, 200, {"ok": True, "overwatch": cached})

                    compat = cached_probe("compat")
                    if compat is None:
                        if int(gateway.health().get("queue_depth", 0) or 0) <= 2:
                            try:
                                compat = run_compat_probe(gateway)
                                store_probe("compat", compat)
                            except Exception:
                                compat = {"ok": False, "missing_commands": [], "missing_fields": []}
                        else:
                            compat = {"ok": False, "missing_commands": [], "missing_fields": []}

                    connect = cached_probe("connect")
                    if connect is None:
                        if int(gateway.health().get("queue_depth", 0) or 0) <= 2:
                            try:
                                connect = run_connect_probe(gateway)
                                store_probe("connect", connect)
                            except Exception:
                                connect = {"ok": False, "confidence_pct": 0}
                        else:
                            connect = {"ok": False, "confidence_pct": 0}

                    report = build_overwatch_report(
                        gateway=gateway,
                        firmware=firmware,
                        compat=compat if isinstance(compat, dict) else None,
                        connect=connect if isinstance(connect, dict) else None,
                    )
                    store_probe("overwatch", report)
                    return _json(self, 200, {"ok": True, "overwatch": report})
                if u.path == "/profiles":
                    return _json(self, 200, {"ok": True, "profiles": profiles.list()})
                if u.path == "/ai/metrics":
                    tok = _extract_auth_token(self)
                    me = auth.me(tok)
                    if not me:
                        return _json(self, 401, {"ok": False, "error": "unauthenticated"})
                    q = parse_qs(u.query)
                    since_hours = float((q.get("since_hours", ["24"]) or ["24"])[0] or 24)
                    since_ts = time.time() - (since_hours * 3600) if since_hours > 0 else None
                    tool_filter = str((q.get("tool", [""]) or [""])[0]).strip() or None
                    from codex_db import get_codex_db
                    db = get_codex_db()
                    try:
                        tool_metrics = db.get_tool_metrics(since_ts=since_ts, tool_filter=tool_filter)
                        db_stats = db.get_stats()
                        return _json(self, 200, {
                            "ok": True,
                            "since_hours": since_hours,
                            "tool_metrics": tool_metrics,
                            "db_stats": db_stats,
                            "ts": time.time(),
                        })
                    except Exception as exc:
                        logger.warning(f"Metrics fetch error: {exc}")
                        return _json(self, 500, {"ok": False, "error": f"metrics_error: {exc}"})
                if u.path == "/ai/rag/stats":
                    tok = _extract_auth_token(self)
                    me = auth.me(tok)
                    if not me:
                        return _json(self, 401, {"ok": False, "error": "unauthenticated"})
                    try:
                        if not get_codex_rag:
                            return _json(self, 503, {"ok": False, "error": "rag_not_available"})
                        openai_key = me.get("openai_key") or os.environ.get("OPENAI_API_KEY")
                        rag = get_codex_rag(openai_key)
                        stats = rag.get_index_stats()
                        return _json(self, 200, {
                            "ok": True,
                            "stats": stats,
                            "ts": time.time(),
                        })
                    except Exception as exc:
                        logger.warning(f"RAG stats error: {exc}")
                        return _json(self, 500, {"ok": False, "error": f"rag_stats_error: {exc}"})
                if u.path == "/config/snapshots":
                    q = parse_qs(u.query)
                    limit = int((q.get("limit", ["30"]) or ["30"])[0] or 30)
                    return _json(self, 200, {"ok": True, "snapshots": config_history.list_snapshots(limit=limit)})
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

                if u.path == "/auth/password-reset/request":
                    email = str(body.get("email", ""))
                    out = auth.request_password_reset(email)
                    return _json(self, 200, {"ok": True, "reset": out})

                if u.path == "/auth/password-reset/confirm":
                    email = str(body.get("email", ""))
                    token = str(body.get("token", ""))
                    new_password = str(body.get("new_password", ""))
                    auth.reset_password(email, token, new_password)
                    return _json(self, 200, {"ok": True, "result": "password_reset"})

                if u.path == "/auth/logout":
                    tok = _extract_auth_token(self, body)
                    auth.logout(tok)
                    return _json(self, 200, {"ok": True})

                if u.path == "/ai/thread/new":
                    tok = _extract_auth_token(self, body)
                    me = auth.me(tok)
                    if not me:
                        return _json(self, 401, {"ok": False, "error": "unauthenticated"})
                    skey = f"user:{me['id']}"
                    created = ai.create_thread(skey, title=body.get("title"))
                    st = ai.status(configured=bool(me.get("openai_configured")), model=str(me.get("openai_model") or "gpt-5-mini"), session_key=skey)
                    return _json(self, 200, {"ok": True, "thread": created, "threads": ai.list_threads(skey), "ai": st, "history": ai.history(skey, st.get("active_thread_id"))[-80:]})

                if u.path == "/ai/thread/select":
                    tok = _extract_auth_token(self, body)
                    me = auth.me(tok)
                    if not me:
                        return _json(self, 401, {"ok": False, "error": "unauthenticated"})
                    thread_id = str(body.get("thread_id", "")).strip()
                    if not thread_id:
                        return _json(self, 400, {"ok": False, "error": "thread_id_required"})
                    skey = f"user:{me['id']}"
                    selected = ai.select_thread(skey, thread_id)
                    st = ai.status(configured=bool(me.get("openai_configured")), model=str(me.get("openai_model") or "gpt-5-mini"), session_key=skey)
                    return _json(self, 200, {"ok": True, "thread": selected, "threads": ai.list_threads(skey), "ai": st, "history": ai.history(skey, thread_id)[-80:]})

                if u.path == "/ai/profile/save":
                    tok = _extract_auth_token(self, body)
                    me = auth.me(tok)
                    if not me:
                        return _json(self, 401, {"ok": False, "error": "unauthenticated"})
                    return _json(
                        self,
                        403,
                        {
                            "ok": False,
                            "error": "ai_profile_edit_locked",
                            "hint": "Assistant profiles are managed via local repository edits only.",
                        },
                    )

                if u.path == "/ai/profile/activate":
                    tok = _extract_auth_token(self, body)
                    me = auth.me(tok)
                    if not me:
                        return _json(self, 401, {"ok": False, "error": "unauthenticated"})
                    return _json(
                        self,
                        403,
                        {
                            "ok": False,
                            "error": "ai_profile_edit_locked",
                            "hint": "Assistant profiles are managed via local repository edits only.",
                        },
                    )

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

                if u.path == "/firmware/generate-unified":
                    profile = body.get("profile")
                    if not isinstance(profile, dict):
                        return _json(self, 400, {"ok": False, "error": "profile_object_required"})
                    sketch_name = body.get("sketch_name")
                    out = firmware.generate_unified(profile=profile, sketch_name=str(sketch_name) if sketch_name else None)
                    return _json(self, 200, {"ok": True, "unified": out})

                if u.path == "/firmware/generate-docs-pack":
                    profile = body.get("profile")
                    if not isinstance(profile, dict):
                        return _json(self, 400, {"ok": False, "error": "profile_object_required"})
                    sketch_name = body.get("sketch_name")
                    sketch_content = body.get("sketch_content")
                    sketch_path = body.get("sketch_path")
                    force_regenerate = bool(body.get("force_regenerate", False))
                    out = firmware.generate_docs_pack(
                        profile=profile,
                        sketch_name=str(sketch_name) if sketch_name else None,
                        sketch_content=str(sketch_content) if isinstance(sketch_content, str) else None,
                        sketch_path=str(sketch_path) if isinstance(sketch_path, str) else None,
                        force_regenerate=force_regenerate,
                    )
                    return _json(self, 200, {"ok": True, "docs_pack": out})

                if u.path == "/profiles/validate":
                    duration_s = float(body.get("duration_s", 12.0))
                    sample_interval_s = float(body.get("sample_interval_s", 0.25))
                    report = profiles.validate(gateway, duration_s=duration_s, sample_interval_s=sample_interval_s)
                    return _json(self, 200, {"ok": True, "validation": report})

                if u.path == "/profiles/save":
                    prof = body.get("profile")
                    if not isinstance(prof, dict):
                        return _json(self, 400, {"ok": False, "error": "profile_object_required"})
                    saved = profiles.save(prof)
                    return _json(self, 200, {"ok": True, "saved": saved, "profiles": profiles.list()})

                if u.path == "/profiles/activate":
                    profile_id = str(body.get("profile_id", "")).strip()
                    if not profile_id:
                        return _json(self, 400, {"ok": False, "error": "profile_id_required"})
                    validation = body.get("validation")
                    if not isinstance(validation, dict) or not bool(validation.get("ok", False)):
                        return _json(self, 409, {"ok": False, "error": "validation_required_before_activation"})
                    out = profiles.activate(profile_id)
                    return _json(self, 200, {"ok": True, "active": out, "profiles": profiles.list()})

                if u.path == "/profiles/delete":
                    profile_id = str(body.get("profile_id", "")).strip()
                    if not profile_id:
                        return _json(self, 400, {"ok": False, "error": "profile_id_required"})
                    out = profiles.delete(profile_id)
                    return _json(self, 200, {"ok": True, "profiles": out})

                if u.path == "/config/revert":
                    snapshot_id = str(body.get("snapshot_id", "")).strip() or None
                    out = _revert_snapshot(gateway, config_history, snapshot_id=snapshot_id)
                    return _json(self, 200, {"ok": True, "revert": out, "control": control.snapshot()})

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
                    active_profile = ai_profiles.get_active()
                    policy = active_profile.get("policy", {}) if isinstance(active_profile, dict) else {}
                    profile_allow_apply = bool(policy.get("allow_auto_apply", True)) if isinstance(policy, dict) else True
                    requested_allow_apply = bool(body.get("allow_apply", True))
                    allow_apply = bool(requested_allow_apply and profile_allow_apply)
                    prompt = _resolve_system_prompt(active_profile, allow_apply=allow_apply, repo_root=firmware.repo_root)
                    serial_h = gateway.health()
                    cached_status = dict(serial_h.get("last_status", {}))
                    ctx = {
                        "status": cached_status,
                        "status_source": "gateway.health.last_status_cached",
                        "serial_health": serial_h,
                        "control": control.snapshot(),
                        "firmware": firmware.status(),
                        "commissioning": _commissioning_ai_context(commissioning),
                        "host_capture": _host_capture_ai_context(host_capture),
                        "burst": burst_status(),
                        "config_snapshots": config_history.list_snapshots(limit=8),
                        "assistant_capabilities": _assistant_capabilities_context(allow_apply=allow_apply),
                        "assistant_profile": active_profile,
                        "assistant_knowledge": knowledge.context(),
                    }
                    skey = f"user:{me['id']}"
                    thread_id = str(body.get("thread_id", "")).strip() or None
                    if thread_id:
                        try:
                            ai.history(skey, thread_id)
                        except RuntimeError as exc:
                            if str(exc) == "thread_not_found":
                                return _json(self, 404, {"ok": False, "error": "thread_not_found"})
                            raise
                    out = ai.chat(
                        message=msg,
                        context=ctx,
                        session_key=skey,
                        api_key=creds["api_key"],
                        model=str(creds["model"] or "gpt-5-mini"),
                        thread_id=thread_id,
                        system_prompt=prompt,
                    )
                    reply = _strip_apply_json_block(out["answer"])
                    apply_result: Optional[Dict[str, Any]] = None
                    apply_src = _extract_apply_json(out["answer"])
                    plan = _sanitize_apply_plan(apply_src) if isinstance(apply_src, dict) else {}
                    if allow_apply and plan:
                        try:
                            apply_result = _apply_assistant_plan(gateway, config_history, firmware, plan, source="ai/chat")
                        except Exception as exc:
                            apply_result = {"ok": False, "error": str(exc)}
                    if apply_result:
                        note = _format_apply_note(apply_result)
                        reply = f"{reply}\n\n{note}".strip()
                    hist = ai.history(skey, out.get("thread_id"))[-80:]
                    if reply != out["answer"]:
                        hist = history_with_reply(hist, reply)
                    return _json(
                        self,
                        200,
                        {
                            "ok": True,
                            "reply": reply,
                            "ai": ai.status(configured=True, model=str(creds["model"] or "gpt-5-mini"), session_key=skey),
                            "history": hist,
                            "threads": ai.list_threads(skey),
                            "thread_id": out.get("thread_id"),
                            "apply": apply_result,
                        },
                    )

                if u.path == "/ai/chat/tools":
                    # Tool-enabled chat endpoint using CodexAgent
                    if codex_agent is None:
                        return _json(self, 501, {"ok": False, "error": "tool_support_not_available"})
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
                    active_profile = ai_profiles.get_active()
                    policy = active_profile.get("policy", {}) if isinstance(active_profile, dict) else {}
                    enable_tools = bool(body.get("enable_tools", True))
                    prompt = _resolve_system_prompt(active_profile, allow_apply=True, repo_root=firmware.repo_root)
                    serial_h = gateway.health()
                    cached_status = dict(serial_h.get("last_status", {}))
                    ctx = {
                        "status": cached_status,
                        "status_source": "gateway.health.last_status_cached",
                        "serial_health": serial_h,
                        "control": control.snapshot(),
                        "firmware": firmware.status(),
                        "commissioning": _commissioning_ai_context(commissioning),
                        "host_capture": _host_capture_ai_context(host_capture),
                        "burst": burst_status(),
                        "config_snapshots": config_history.list_snapshots(limit=8),
                        "assistant_profile": active_profile,
                        "assistant_knowledge": knowledge.context(),
                    }
                    # Extract sketch/robot context from request or firmware status
                    fw_status = firmware.status()
                    active_sketch = str(body.get("sketch_path", fw_status.get("sketch_path", "")))
                    robot_id = str(body.get("robot_id", "default"))
                    board_fqbn = str(body.get("board", fw_status.get("board", "arduino:avr:nano")))
                    port = str(body.get("port", fw_status.get("port", "")))
                    try:
                        skey = f"user:{me['id']}"
                        thread_id = str(body.get("thread_id", "")).strip() or None
                        if thread_id:
                            try:
                                ai.history(skey, thread_id)
                            except RuntimeError as exc:
                                if str(exc) == "thread_not_found":
                                    return _json(self, 404, {"ok": False, "error": "thread_not_found"})
                                raise
                        result = codex_agent.chat_with_tools(
                            message=msg,
                            context=ctx,
                            api_key=creds["api_key"],
                            model=str(creds["model"] or "gpt-4"),
                            system_prompt=prompt,
                            enable_tools=enable_tools,
                            active_sketch_path=active_sketch,
                            active_robot_id=robot_id,
                            board_fqbn=board_fqbn,
                            port=port,
                        )
                        tid = ai._append(skey, "user", msg, thread_id=thread_id)
                        ai._append(skey, "assistant", result["answer"], thread_id=tid)
                        return _json(
                            self,
                            200,
                            {
                                "ok": True,
                                "reply": result["answer"],
                                "tool_calls": result.get("tool_calls", []),
                                "iterations": result.get("iterations", 1),
                                "ai": ai.status(configured=True, model=str(creds["model"] or "gpt-4"), session_key=skey),
                                "history": ai.history(skey, tid)[-80:],
                                "threads": ai.list_threads(skey),
                                "thread_id": tid,
                            },
                        )
                    except Exception as exc:
                        return _json(self, 500, {"ok": False, "error": str(exc)})

                if u.path == "/ai/upload/confirm":
                    # Upload confirmation endpoint - validates token and executes upload
                    tok = _extract_auth_token(self, body)
                    me = auth.me(tok)
                    if not me:
                        return _json(self, 401, {"ok": False, "error": "unauthenticated"})
                    confirm_token = str(body.get("token", "")).strip()
                    action = str(body.get("action", "")).strip()
                    if not confirm_token:
                        return _json(self, 400, {"ok": False, "error": "missing token"})
                    if action not in ("approve", "reject"):
                        return _json(self, 400, {"ok": False, "error": "invalid action, must be 'approve' or 'reject'"})
                    if action == "reject":
                        # Clear pending upload if codex_agent available
                        if codex_agent and hasattr(codex_agent, 'tool_executor'):
                            codex_agent.tool_executor._pending_uploads.pop(confirm_token, None)
                        return _json(self, 200, {"ok": True, "action": "rejected"})
                    # Approve action - execute the upload
                    if codex_agent is None:
                        return _json(self, 501, {"ok": False, "error": "tool_support_not_available", "action": "invalid"})
                    if not hasattr(codex_agent, 'tool_executor'):
                        return _json(self, 501, {"ok": False, "error": "tool_executor_not_available", "action": "invalid"})
                    executor = codex_agent.tool_executor
                    # Check if token exists
                    if confirm_token not in executor._pending_uploads:
                        return _json(self, 400, {"ok": False, "error": "Invalid or expired confirmation token", "action": "invalid"})
                    # Execute upload with token
                    result = executor._tool_upload_firmware({"confirmation_token": confirm_token})
                    if result.ok:
                        return _json(self, 200, {
                            "ok": True,
                            "action": "approved",
                            "upload_result": {
                                "ok": True,
                                "sketch": result.data.get("sketch"),
                                "board": result.data.get("board"),
                                "port": result.data.get("port"),
                                "output": result.data.get("output", ""),
                            },
                        })
                    else:
                        # Check for specific error types
                        error_msg = result.error or "Upload failed"
                        action_type = "invalid" if "expired" in error_msg.lower() else "approved"
                        if "expired" in error_msg.lower():
                            action_type = "expired"
                        return _json(self, 200, {
                            "ok": False,
                            "action": action_type,
                            "error": error_msg,
                            "upload_result": {"ok": False, "error": error_msg, "output": result.data.get("output", "")},
                        })

                if u.path == "/ai/metrics":
                    # Metrics endpoint - returns safe aggregate counters for observability
                    tok = _extract_auth_token(self, body)
                    me = auth.me(tok)
                    if not me:
                        return _json(self, 401, {"ok": False, "error": "unauthenticated"})
                    
                    # Parse optional filters
                    since_hours = float(body.get("since_hours", 24))
                    since_ts = time.time() - (since_hours * 3600) if since_hours > 0 else None
                    tool_filter = str(body.get("tool", "")).strip() or None
                    
                    # Get metrics from codex_db
                    from codex_db import get_codex_db
                    db = get_codex_db()
                    
                    try:
                        tool_metrics = db.get_tool_metrics(since_ts=since_ts, tool_filter=tool_filter)
                        db_stats = db.get_stats()
                        
                        return _json(self, 200, {
                            "ok": True,
                            "since_hours": since_hours,
                            "tool_metrics": tool_metrics,
                            "db_stats": db_stats,
                            "ts": time.time(),
                        })
                    except Exception as exc:
                        logger.warning(f"Metrics fetch error: {exc}")
                        return _json(self, 500, {"ok": False, "error": f"metrics_error: {exc}"})

                if u.path == "/ai/rag/index":
                    tok = _extract_auth_token(self, body)
                    me = auth.me(tok)
                    if not me:
                        return _json(self, 401, {"ok": False, "error": "unauthenticated"})
                    try:
                        if not get_codex_rag:
                            return _json(self, 503, {"ok": False, "error": "rag_not_available"})
                        openai_key = me.get("openai_key") or os.environ.get("OPENAI_API_KEY")
                        if not openai_key:
                            return _json(self, 400, {"ok": False, "error": "no_openai_key", "hint": "Set OpenAI API key to enable RAG indexing"})
                        rag = get_codex_rag(openai_key)
                        paths = body.get("paths")  # Optional: list of paths to index
                        force_reindex = bool(body.get("force_reindex", False))
                        start_ts = time.time()
                        doc_stats = rag.index_docs(doc_paths=paths, force_reindex=force_reindex)
                        sketch_stats = rag.index_sketches(force_reindex=force_reindex)
                        elapsed_ms = (time.time() - start_ts) * 1000
                        return _json(self, 200, {
                            "ok": True,
                            "docs": doc_stats,
                            "sketches": sketch_stats,
                            "elapsed_ms": round(elapsed_ms, 2),
                            "ts": time.time(),
                        })
                    except Exception as exc:
                        logger.warning(f"RAG index error: {exc}")
                        return _json(self, 500, {"ok": False, "error": f"rag_index_error: {exc}"})

                if u.path == "/ai/chat/stream":
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
                    active_profile = ai_profiles.get_active()
                    policy = active_profile.get("policy", {}) if isinstance(active_profile, dict) else {}
                    profile_allow_apply = bool(policy.get("allow_auto_apply", True)) if isinstance(policy, dict) else True
                    requested_allow_apply = bool(body.get("allow_apply", True))
                    allow_apply = bool(requested_allow_apply and profile_allow_apply)
                    prompt = _resolve_system_prompt(active_profile, allow_apply=allow_apply, repo_root=firmware.repo_root)
                    serial_h = gateway.health()
                    cached_status = dict(serial_h.get("last_status", {}))

                    ctx = {
                        "status": cached_status,
                        "status_source": "gateway.health.last_status_cached",
                        "serial_health": serial_h,
                        "control": control.snapshot(),
                        "firmware": firmware.status(),
                        "commissioning": _commissioning_ai_context(commissioning),
                        "host_capture": _host_capture_ai_context(host_capture),
                        "burst": burst_status(),
                        "config_snapshots": config_history.list_snapshots(limit=8),
                        "assistant_capabilities": _assistant_capabilities_context(allow_apply=allow_apply),
                        "assistant_profile": active_profile,
                        "assistant_knowledge": knowledge.context(),
                    }
                    skey = f"user:{me['id']}"
                    thread_id = str(body.get("thread_id", "")).strip() or None
                    if thread_id:
                        try:
                            ai.history(skey, thread_id)
                        except RuntimeError as exc:
                            if str(exc) == "thread_not_found":
                                return _json(self, 404, {"ok": False, "error": "thread_not_found"})
                            raise

                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "keep-alive")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Session-Token")
                    self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
                    self.end_headers()

                    def send_evt(name: str, payload_obj: Dict[str, Any]) -> None:
                        blob = f"event: {name}\ndata: {json.dumps(payload_obj, ensure_ascii=True)}\n\n".encode("utf-8")
                        self.wfile.write(blob)
                        self.wfile.flush()

                    send_evt("start", {"ok": True})
                    try:
                        delta_marker = "UPRIGHT_APPLY_JSON:"
                        delta_state: Dict[str, Any] = {
                            "carry": "",
                            "suppress": False,
                        }

                        def on_stream_delta(txt: str) -> None:
                            if not txt:
                                return
                            if bool(delta_state["suppress"]):
                                return
                            combined = str(delta_state["carry"]) + txt
                            idx = combined.find(delta_marker)
                            if idx >= 0:
                                emit = combined[:idx]
                                delta_state["carry"] = ""
                                delta_state["suppress"] = True
                                if emit:
                                    send_evt("delta", {"text": emit})
                                return
                            keep = max(0, len(delta_marker) - 1)
                            safe_len = max(0, len(combined) - keep)
                            if safe_len > 0:
                                emit = combined[:safe_len]
                                delta_state["carry"] = combined[safe_len:]
                                send_evt("delta", {"text": emit})
                            else:
                                delta_state["carry"] = combined

                        out = ai.chat_stream(
                            message=msg,
                            context=ctx,
                            session_key=skey,
                            api_key=creds["api_key"],
                            model=str(creds["model"] or "gpt-5-mini"),
                            on_delta=on_stream_delta,
                            thread_id=thread_id,
                            system_prompt=prompt,
                        )
                        if (not bool(delta_state["suppress"])) and str(delta_state["carry"]):
                            send_evt("delta", {"text": str(delta_state["carry"])})
                        reply = _strip_apply_json_block(out["answer"])
                        apply_result: Optional[Dict[str, Any]] = None
                        apply_src = _extract_apply_json(out["answer"])
                        plan = _sanitize_apply_plan(apply_src) if isinstance(apply_src, dict) else {}
                        if allow_apply and plan:
                            try:
                                apply_result = _apply_assistant_plan(gateway, config_history, firmware, plan, source="ai/chat/stream")
                            except Exception as exc:
                                apply_result = {"ok": False, "error": str(exc)}
                        if apply_result:
                            note = _format_apply_note(apply_result)
                            reply = f"{reply}\n\n{note}".strip()
                        hist = ai.history(skey, out.get("thread_id"))[-80:]
                        if reply != out["answer"]:
                            hist = history_with_reply(hist, reply)
                        send_evt(
                            "done",
                            {
                                "ok": True,
                                "reply": reply,
                                "ai": ai.status(configured=True, model=str(creds["model"] or "gpt-5-mini"), session_key=skey),
                                "history": hist,
                                "threads": ai.list_threads(skey),
                                "thread_id": out.get("thread_id"),
                                "apply": apply_result,
                            },
                        )
                    except Exception as exc:
                        send_evt("error", {"ok": False, "error": str(exc)})
                    return

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

                if u.path == "/burst/arm":
                    delay_ms = int(body.get("delay_ms", 3000) or 3000)
                    lines = int(body.get("lines", 80) or 80)
                    freq_hz = float(body.get("freq_hz", 8.0) or 8.0)
                    h = gateway.health()
                    st = dict(h.get("last_status", {}))
                    if not bool(h.get("connected", False)):
                        return _json(self, 409, {"ok": False, "error": "serial_disconnected"})
                    cmd = f"BURSTCSV {max(0, min(delay_ms, 60000))} {max(1, min(lines, 3000))}"
                    host = host_capture.arm(delay_ms=delay_ms, lines=lines, freq_hz=freq_hz)
                    fw: Dict[str, Any] = {"ok": True, "cmd": cmd, "queued": True}
                    try:
                        # Keep endpoint responsive when serial is momentarily busy.
                        fw["result"] = gateway.command(cmd, timeout=1.0)
                    except Exception as exc:
                        fw["ok"] = False
                        fw["error"] = str(exc)
                    return _json(
                        self,
                        200,
                        {
                            "ok": True,
                            "queued": True,
                            "status": st,
                            "firmware": fw,
                            "burst": burst_status(),
                            "host_capture": host,
                        },
                    )

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
                    snap = config_history.save_snapshot(source="/pid", status_before=gateway.get_status())
                    res = gateway.command(f"PID {kp} {ki} {kd}", expect_contains="OK PID", timeout=2.0)
                    return _json(self, 200, {"ok": True, "result": res, "snapshot": snap, "status": gateway.get_status(), "control": control.snapshot()})

                if u.path == "/motion":
                    kv = float(body["kv"])
                    kx = float(body["kx"])
                    snap = config_history.save_snapshot(source="/motion", status_before=gateway.get_status())
                    res = gateway.command(f"MOTION {kv} {kx}", expect_contains="OK MOTION", timeout=2.0)
                    return _json(self, 200, {"ok": True, "result": res, "snapshot": snap, "status": gateway.get_status(), "control": control.snapshot()})

                if u.path == "/setpoint":
                    deg = float(body["deg"])
                    snap = config_history.save_snapshot(source="/setpoint", status_before=gateway.get_status())
                    res = gateway.command(f"SETPOINT {deg}", expect_contains="OK SETPOINT", timeout=2.0)
                    return _json(self, 200, {"ok": True, "result": res, "snapshot": snap, "status": gateway.get_status(), "control": control.snapshot()})

                if u.path == "/limits":
                    out_max = float(body["out_max"])
                    tip_deg = float(body["tip_deg"])
                    i_max = float(body["i_max"])
                    snap = config_history.save_snapshot(source="/limits", status_before=gateway.get_status())
                    res = gateway.command(f"LIMITS {out_max} {tip_deg} {i_max}", expect_contains="OK LIMITS", timeout=2.0)
                    return _json(self, 200, {"ok": True, "result": res, "snapshot": snap, "status": gateway.get_status(), "control": control.snapshot()})

                return _json(self, 404, {"ok": False, "error": "not_found"})
            except KeyError as exc:
                return _json(self, 400, {"ok": False, "error": f"missing field: {exc}"})
            except RuntimeError as exc:
                msg = str(exc)
                if msg in {"invalid_email", "weak_password", "email_exists", "invalid_credentials", "invalid_openai_key", "empty_message"}:
                    return _json(self, 400, {"ok": False, "error": msg})
                if msg in {"profile_label_required", "profile_id_required"}:
                    return _json(self, 400, {"ok": False, "error": msg})
                if msg.startswith("invalid_unified_profile:"):
                    return _json(self, 400, {"ok": False, "error": msg})
                if msg in {"ai_profile_label_required", "ai_profile_id_required"}:
                    return _json(self, 400, {"ok": False, "error": msg})
                if msg in {"profile_not_found"}:
                    return _json(self, 404, {"ok": False, "error": msg})
                if msg in {"ai_profile_not_found"}:
                    return _json(self, 404, {"ok": False, "error": msg})
                if msg in {"snapshot_not_found"}:
                    return _json(self, 404, {"ok": False, "error": msg})
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


def serial_reconnect_loop(gateway: NanoSerialGateway, stop_evt: threading.Event) -> None:
    while not stop_evt.wait(2.0):
        try:
            if gateway.health().get("connected", False):
                continue
            gateway.connect()
            ready = gateway.wait_ready(timeout=5.0)
            print(f"serial reconnected: mode={ready.get('mode', 'UNKNOWN')}")
        except Exception:
            try:
                gateway.close()
            except Exception:
                pass
            continue


def _startup_rag_indexing(openai_key: Optional[str]) -> None:
    """
    Background RAG indexing on server startup.
    Non-blocking - runs in daemon thread. Fails gracefully if RAG unavailable.
    """
    if not openai_key:
        logger.info("Startup RAG indexing skipped: no OpenAI key available")
        return
    if not get_codex_rag:
        logger.info("Startup RAG indexing skipped: RAG module not available")
        return
    try:
        rag = get_codex_rag(openai_key)
        logger.info("Starting background RAG indexing...")
        start_ts = time.time()
        doc_stats = rag.index_docs(force_reindex=False)
        sketch_stats = rag.index_sketches(force_reindex=False)
        elapsed_s = time.time() - start_ts
        logger.info(
            f"Background RAG indexing complete in {elapsed_s:.1f}s: "
            f"docs={doc_stats['files_processed']} processed/{doc_stats['files_skipped']} skipped, "
            f"sketches={sketch_stats['files_processed']} processed/{sketch_stats['files_skipped']} skipped"
        )
    except Exception as exc:
        logger.warning(f"Background RAG indexing failed (non-fatal): {exc}")


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
    startup_serial_error: Optional[str] = None
    try:
        gw.connect()
    except Exception as exc:
        startup_serial_error = str(exc)
        try:
            gw.close()
        except Exception:
            pass
    control = BridgeControlState(watchdog_timeout_s=max(0.5, args.watchdog_timeout))
    commissioning = CommissioningManager(repo_root, args.port, args.baud)
    host_capture = HostCaptureManager(repo_root)
    firmware = FirmwareManager(repo_root, args.port)
    ai = AIManager(repo_root)
    ai_profiles = AIProfileManager(repo_root)
    knowledge = AssistantKnowledgeManager(repo_root)

    # Initialize CodexAgent for tool-enabled chat (optional - gracefully degrades if unavailable)
    codex_agent: Optional[Any] = None
    if create_codex_agent is not None:
        try:
            codex_agent = create_codex_agent(
                gateway=gw,
                firmware_module=firmware,
                probe_funcs={
                    "run_compat_probe": run_compat_probe,
                    "run_connect_probe": run_connect_probe,
                },
                repo_root=str(repo_root),
                host_capture=host_capture,
            )
            print("codex agent initialized with tool support")
            # Kick off background RAG indexing (non-blocking)
            startup_openai_key = os.environ.get("OPENAI_API_KEY")
            if startup_openai_key:
                rag_thread = threading.Thread(
                    target=_startup_rag_indexing,
                    args=(startup_openai_key,),
                    daemon=True,
                    name="startup-rag-indexing",
                )
                rag_thread.start()
                print("background RAG indexing started")
        except Exception as exc:
            print(f"codex agent init failed (tool support disabled): {exc}")
    auth = AuthManager(repo_root)
    profiles = RobotProfilesManager(repo_root)
    config_history = ConfigHistoryManager(repo_root)
    telemetry = TelemetryHub(gw, control, host_capture, args.host, args.telemetry_port)
    telemetry.start()

    if startup_serial_error:
        print(f"bridge started without serial target: {args.port} @ {args.baud} ({startup_serial_error})")
    else:
        print(f"bridge serial opened: {args.port} @ {args.baud}")
    print(f"telemetry websocket: ws://{args.host}:{args.telemetry_port}/telemetry enabled={websockets is not None}")

    stop_evt = threading.Event()
    wd = threading.Thread(target=watchdog_loop, args=(gw, control, stop_evt), daemon=True)
    wd.start()
    reconn = threading.Thread(target=serial_reconnect_loop, args=(gw, stop_evt), daemon=True)
    reconn.start()

    server = ThreadingHTTPServer(
        (args.host, args.http_port),
        build_handler(gw, control, commissioning, host_capture, firmware, ai, ai_profiles, knowledge, auth, profiles, config_history, args.telemetry_port, codex_agent),
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

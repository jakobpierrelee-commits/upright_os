#!/usr/bin/env python3
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any, Dict, List, Optional

import serial


def parse_status_line(line: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not line.startswith("STATUS "):
        return out
    for tok in line.split()[1:]:
        if "=" in tok:
            k, v = tok.split("=", 1)
            out[k] = v
    return out


class NanoSerialGateway:
    def __init__(self, port: str, baud: int = 115200, timeout: float = 0.1):
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self._lock = threading.Lock()
        self._ser: Optional[serial.Serial] = None
        self._last_status: Dict[str, str] = {}
        self._recent_lines: deque[str] = deque(maxlen=600)

    def connect(self) -> None:
        with self._lock:
            if self._ser and self._ser.is_open:
                return
            self._ser = serial.Serial(
                port=self.port,
                baudrate=self.baud,
                timeout=self.timeout,
            )
            self._ser.reset_input_buffer()
            self._ser.reset_output_buffer()
            self._drain_locked(1.2)

    def close(self) -> None:
        with self._lock:
            if self._ser and self._ser.is_open:
                self._ser.close()
            self._ser = None

    def wait_ready(self, timeout: float = 20.0) -> Dict[str, str]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                s = self.get_status()
                if s:
                    return s
            except Exception:
                time.sleep(0.2)
        raise TimeoutError("Firmware did not become ready (no STATUS response)")

    def health(self) -> Dict[str, Any]:
        with self._lock:
            connected = bool(self._ser and self._ser.is_open)
            return {
                "connected": connected,
                "port": self.port,
                "baud": self.baud,
                "last_status": self._last_status,
                "recent_line_count": len(self._recent_lines),
            }

    def recent_lines(self, n: int = 100) -> List[str]:
        with self._lock:
            if n <= 0:
                return []
            return list(self._recent_lines)[-n:]

    def get_status(self) -> Dict[str, str]:
        res = self.command("GET", expect_prefix="STATUS ", timeout=2.5)
        line = res["matched"]
        status = parse_status_line(line)
        if not status:
            raise RuntimeError(f"Failed to parse status from: {line}")
        return status

    def command(
        self,
        cmd: str,
        *,
        expect_contains: Optional[str] = None,
        expect_prefix: Optional[str] = None,
        timeout: float = 2.0,
    ) -> Dict[str, Any]:
        with self._lock:
            self._ensure_open_locked()
            assert self._ser is not None
            self._ser.write((cmd + "\n").encode("utf-8"))
            self._ser.flush()

            lines: List[str] = []
            deadline = time.time() + timeout
            matched: Optional[str] = None
            got_any = False
            quiet_deadline: Optional[float] = None

            while time.time() < deadline:
                line = self._readline_locked()
                if line is None:
                    if quiet_deadline and time.time() >= quiet_deadline:
                        break
                    continue
                got_any = True
                lines.append(line)
                if expect_contains and expect_contains in line:
                    matched = line
                    break
                if expect_prefix and line.startswith(expect_prefix):
                    matched = line
                    break
                if not expect_contains and not expect_prefix:
                    quiet_deadline = time.time() + 0.2

            if expect_contains or expect_prefix:
                if not matched:
                    raise TimeoutError(
                        f"Timeout waiting for expected response to '{cmd}'. "
                        f"Last lines: {lines[-5:] if lines else []}"
                    )
                return {"ok": True, "cmd": cmd, "matched": matched, "lines": lines}

            if not got_any:
                return {"ok": True, "cmd": cmd, "matched": "", "lines": []}
            return {"ok": True, "cmd": cmd, "matched": lines[-1], "lines": lines}

    def _ensure_open_locked(self) -> None:
        if not self._ser or not self._ser.is_open:
            raise RuntimeError("Serial port is not connected")

    def _drain_locked(self, seconds: float) -> None:
        end = time.time() + seconds
        while time.time() < end:
            self._readline_locked()

    def _readline_locked(self) -> Optional[str]:
        assert self._ser is not None
        raw = self._ser.readline()
        if not raw:
            return None
        try:
            line = raw.decode("utf-8", errors="replace").strip()
        except Exception:
            return None
        if not line:
            return None
        self._recent_lines.append(line)
        if line.startswith("STATUS "):
            self._last_status = parse_status_line(line)
        return line

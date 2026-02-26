#!/usr/bin/env python3
from __future__ import annotations

import itertools
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import serial


def parse_status_line(line: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    payload = ""
    if line.startswith("STATUS "):
        payload = line[len("STATUS ") :]
    elif line.startswith("S "):
        payload = line[len("S ") :]
    else:
        return out
    for tok in payload.split():
        if "=" in tok:
            k, v = tok.split("=", 1)
            out[k] = v
    return out


@dataclass
class _GatewayRequest:
    req_id: int
    cmd: str
    expect_contains: Optional[str]
    expect_prefix: Optional[str]
    timeout: float
    created_at: float = field(default_factory=time.monotonic)
    response_q: "queue.Queue[tuple[bool, Any]]" = field(default_factory=queue.Queue)


class NanoSerialGateway:
    def __init__(self, port: str, baud: int = 115200, timeout: float = 0.1):
        self.port = port
        self.baud = baud
        self.timeout = timeout

        self._state_lock = threading.Lock()
        self._ser: Optional[serial.Serial] = None
        self._last_status: Dict[str, str] = {}
        self._last_status_ts: Optional[float] = None
        self._recent_lines: deque[str] = deque(maxlen=600)

        self._req_q: "queue.PriorityQueue[tuple[int, int, _GatewayRequest]]" = queue.PriorityQueue()
        self._seq = itertools.count(1)
        self._req_ids = itertools.count(1)
        self._worker_stop = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._inflight = 0

        self._metrics_lock = threading.Lock()
        self._commands_ok = 0
        self._commands_err = 0
        self._timeouts = 0
        self._latencies_ms: deque[float] = deque(maxlen=300)
        self._last_error: Optional[str] = None

    @staticmethod
    def _is_transport_gone_error(exc: Exception) -> bool:
        msg = str(exc).lower()
        return any(
            needle in msg
            for needle in (
                "device not configured",
                "bad file descriptor",
                "input/output error",
                "i/o error",
                "broken pipe",
                "permission denied",
                "resource unavailable",
            )
        )

    def _mark_disconnected(self, reason: str) -> None:
        with self._state_lock:
            if self._ser and self._ser.is_open:
                try:
                    self._ser.close()
                except Exception:
                    pass
            self._ser = None
            self._last_status = {}
            self._last_status_ts = None
        with self._metrics_lock:
            self._last_error = reason

    def connect(self) -> None:
        with self._state_lock:
            if self._ser and self._ser.is_open:
                self._ensure_worker_locked()
                return
            self._ser = serial.Serial(
                port=self.port,
                baudrate=self.baud,
                timeout=self.timeout,
            )
            self._ser.reset_input_buffer()
            self._ser.reset_output_buffer()

        self._drain(1.2)

        with self._state_lock:
            self._ensure_worker_locked()

    def close(self) -> None:
        worker: Optional[threading.Thread] = None
        with self._state_lock:
            self._worker_stop.set()
            worker = self._worker
            self._worker = None
        if worker and worker.is_alive():
            worker.join(timeout=1.0)

        with self._state_lock:
            if self._ser and self._ser.is_open:
                self._ser.close()
            self._ser = None

    def wait_ready(self, timeout: float = 20.0) -> Dict[str, str]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                remain = max(0.2, deadline - time.time())
                s = self.get_status(timeout=min(1.0, remain), priority=4)
                if s:
                    return s
            except Exception:
                time.sleep(0.2)
        raise TimeoutError("Firmware did not become ready (no STATUS response)")

    def health(self) -> Dict[str, Any]:
        with self._state_lock:
            connected = bool(self._ser and self._ser.is_open)
            last_status = dict(self._last_status)
            last_status_age_ms = None
            if self._last_status_ts is not None:
                last_status_age_ms = max(0.0, (time.monotonic() - self._last_status_ts) * 1000.0)
            worker_alive = bool(self._worker and self._worker.is_alive())
            queue_depth = self._req_q.qsize()
            recent_line_count = len(self._recent_lines)
            inflight = self._inflight

        with self._metrics_lock:
            lat = list(self._latencies_ms)
            p50 = lat[len(lat) // 2] if lat else None
            p95 = lat[int(len(lat) * 0.95)] if lat else None
            stats = {
                "commands_ok": self._commands_ok,
                "commands_err": self._commands_err,
                "timeouts": self._timeouts,
                "latency_p50_ms": p50,
                "latency_p95_ms": p95,
                "last_error": self._last_error,
            }

        return {
            "connected": connected,
            "port": self.port,
            "baud": self.baud,
            "last_status": last_status,
            "last_status_age_ms": last_status_age_ms,
            "recent_line_count": recent_line_count,
            "queue_depth": queue_depth,
            "inflight": inflight,
            "busy": bool(inflight > 0 or queue_depth > 0),
            "worker_alive": worker_alive,
            "serial_metrics": stats,
        }

    def is_busy(self) -> bool:
        with self._state_lock:
            return bool(self._inflight > 0 or self._req_q.qsize() > 0)

    def recent_lines(self, n: int = 100) -> List[str]:
        with self._state_lock:
            if n <= 0:
                return []
            return list(self._recent_lines)[-n:]

    def get_status(self, timeout: float = 2.5, priority: int = 3) -> Dict[str, str]:
        try:
            res = self.command("GET", timeout=timeout, priority=priority)
            lines = list(res.get("lines", []))
            status: Dict[str, str] = {}
            for line in reversed(lines):
                status = parse_status_line(str(line))
                if status:
                    break
            if not status:
                status = parse_status_line(str(res.get("matched", "")))
            if not status:
                raise RuntimeError(f"Failed to parse status from: {lines[-5:] if lines else []}")
            return status
        except Exception:
            with self._state_lock:
                cached = dict(self._last_status)
                ts = self._last_status_ts
            if cached and ts is not None:
                age_s = time.monotonic() - ts
                if age_s <= 1.5:
                    return cached
            raise

    def command(
        self,
        cmd: str,
        *,
        expect_contains: Optional[str] = None,
        expect_prefix: Optional[str] = None,
        timeout: float = 2.0,
        priority: int = 0,
    ) -> Dict[str, Any]:
        req = _GatewayRequest(
            req_id=next(self._req_ids),
            cmd=cmd,
            expect_contains=expect_contains,
            expect_prefix=expect_prefix,
            timeout=timeout,
        )
        self._enqueue(priority, req)

        wait_timeout = max(0.3, timeout + 0.8)
        try:
            ok, payload = req.response_q.get(timeout=wait_timeout)
        except queue.Empty:
            raise TimeoutError(f"gateway_queue_timeout req_id={req.req_id} cmd={cmd}")

        if ok:
            return payload
        if isinstance(payload, Exception):
            raise payload
        raise RuntimeError(str(payload))

    def _enqueue(self, priority: int, req: _GatewayRequest) -> None:
        with self._state_lock:
            self._ensure_open_locked()
            self._ensure_worker_locked()
            # Backpressure: shed low-priority probes if queue is already backed up.
            if priority >= 8 and self._req_q.qsize() > 2:
                raise RuntimeError("serial_queue_busy_for_probe")
            seq = next(self._seq)
            self._req_q.put((priority, seq, req))

    def _ensure_open_locked(self) -> None:
        if not self._ser or not self._ser.is_open:
            raise RuntimeError("Serial port is not connected")

    def _ensure_worker_locked(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._worker_stop.clear()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    def _worker_loop(self) -> None:
        while not self._worker_stop.is_set():
            try:
                _, _, req = self._req_q.get(timeout=0.1)
            except queue.Empty:
                # Keep draining spontaneous serial output (e.g., STATUS heartbeats)
                # even when no commands are queued.
                try:
                    ser = self._get_open_serial()
                    self._readline(ser)
                except Exception:
                    pass
                continue

            start = time.monotonic()
            try:
                with self._state_lock:
                    self._inflight += 1
                out = self._execute_request(req)
                latency_ms = (time.monotonic() - start) * 1000.0
                out["latency_ms"] = latency_ms
                self._record_ok(latency_ms)
                req.response_q.put((True, out))
            except Exception as exc:
                self._record_err(exc)
                req.response_q.put((False, exc))
            finally:
                with self._state_lock:
                    self._inflight = max(0, self._inflight - 1)
                self._req_q.task_done()

    def _execute_request(self, req: _GatewayRequest) -> Dict[str, Any]:
        ser = self._get_open_serial()

        try:
            ser.write((req.cmd + "\n").encode("utf-8"))
            ser.flush()
        except Exception as exc:
            if self._is_transport_gone_error(exc):
                self._mark_disconnected(f"write failed: {exc}")
            raise RuntimeError(f"write failed: {exc}")

        lines: List[str] = []
        deadline = time.time() + req.timeout
        matched: Optional[str] = None
        got_any = False
        quiet_deadline: Optional[float] = None

        while time.time() < deadline:
            line = self._readline(ser)
            if line is None:
                if quiet_deadline and time.time() >= quiet_deadline:
                    break
                continue
            got_any = True
            lines.append(line)

            if req.expect_contains and req.expect_contains in line:
                matched = line
                break
            if req.expect_prefix and line.startswith(req.expect_prefix):
                matched = line
                break
            if not req.expect_contains and not req.expect_prefix:
                quiet_deadline = time.time() + 0.18

        if req.expect_contains or req.expect_prefix:
            if not matched:
                self._record_timeout()
                raise TimeoutError(
                    f"Timeout waiting for expected response req_id={req.req_id} cmd='{req.cmd}'. "
                    f"Last lines: {lines[-5:] if lines else []}"
                )
            return {"ok": True, "cmd": req.cmd, "cmd_id": req.req_id, "matched": matched, "lines": lines}

        if not got_any:
            return {"ok": True, "cmd": req.cmd, "cmd_id": req.req_id, "matched": "", "lines": []}
        return {"ok": True, "cmd": req.cmd, "cmd_id": req.req_id, "matched": lines[-1], "lines": lines}

    def _get_open_serial(self) -> serial.Serial:
        with self._state_lock:
            self._ensure_open_locked()
            assert self._ser is not None
            return self._ser

    def _drain(self, seconds: float) -> None:
        ser = self._get_open_serial()
        end = time.time() + seconds
        while time.time() < end:
            self._readline(ser)

    def _readline(self, ser: serial.Serial) -> Optional[str]:
        try:
            raw = ser.readline()
        except Exception as exc:
            if self._is_transport_gone_error(exc):
                self._mark_disconnected(f"read failed: {exc}")
            raise RuntimeError(f"read failed: {exc}")
        if not raw:
            return None
        try:
            line = raw.decode("utf-8", errors="replace").strip()
        except Exception:
            return None
        if not line:
            return None

        with self._state_lock:
            self._recent_lines.append(line)
            parsed = parse_status_line(line)
            if parsed:
                self._last_status = parsed
                self._last_status_ts = time.monotonic()
        return line

    def _record_ok(self, latency_ms: float) -> None:
        with self._metrics_lock:
            self._commands_ok += 1
            self._latencies_ms.append(latency_ms)

    def _record_timeout(self) -> None:
        with self._metrics_lock:
            self._timeouts += 1

    def _record_err(self, exc: Exception) -> None:
        with self._metrics_lock:
            self._commands_err += 1
            self._last_error = str(exc)

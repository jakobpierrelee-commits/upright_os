"""
Bridge Control State - Runtime control state management.

Extracted from server.py to domains/control_runtime/
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional


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

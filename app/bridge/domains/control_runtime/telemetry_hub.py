"""
Telemetry Hub - Real-time telemetry distribution.

Manages telemetry streaming via WebSocket and provides
subscription-based access to live robot data.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set


@dataclass
class TelemetrySnapshot:
    """A single telemetry sample."""
    ts: float
    robot_id: str = ""
    mode: str = ""
    ang: float = 0.0
    raw: float = 0.0
    out: float = 0.0
    kp: float = 0.0
    ki: float = 0.0
    kd: float = 0.0
    setpoint: float = 0.0
    gyro: float = 0.0
    voltage: float = 0.0
    enc_l: int = 0
    enc_r: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "ts": self.ts,
            "robot_id": self.robot_id,
            "mode": self.mode,
            "ang": self.ang,
            "raw": self.raw,
            "out": self.out,
            "kp": self.kp,
            "ki": self.ki,
            "kd": self.kd,
            "setpoint": self.setpoint,
            "gyro": self.gyro,
            "voltage": self.voltage,
            "enc_l": self.enc_l,
            "enc_r": self.enc_r,
            **self.extra,
        }


class TelemetryHub:
    """
    Central hub for telemetry distribution.
    
    Receives telemetry from serial gateway and distributes
    to all subscribed clients (WebSocket connections, DB logger, etc.)
    """

    def __init__(self, max_history: int = 600):
        self._subscribers: Set[Callable[[TelemetrySnapshot], None]] = set()
        self._lock = threading.Lock()
        self._history: List[TelemetrySnapshot] = []
        self._max_history = max_history
        self._latest: Optional[TelemetrySnapshot] = None

    def subscribe(self, callback: Callable[[TelemetrySnapshot], None]) -> Callable[[], None]:
        """
        Subscribe to telemetry updates.
        
        Returns an unsubscribe function.
        """
        with self._lock:
            self._subscribers.add(callback)
        
        def unsubscribe() -> None:
            with self._lock:
                self._subscribers.discard(callback)
        
        return unsubscribe

    def publish(self, snapshot: TelemetrySnapshot) -> None:
        """Publish a telemetry snapshot to all subscribers."""
        with self._lock:
            self._latest = snapshot
            self._history.append(snapshot)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]
            subscribers = list(self._subscribers)
        
        for callback in subscribers:
            try:
                callback(snapshot)
            except Exception:
                pass  # Don't let subscriber errors affect hub

    def get_latest(self) -> Optional[TelemetrySnapshot]:
        """Get the most recent telemetry snapshot."""
        with self._lock:
            return self._latest

    def get_history(self, count: int = 100) -> List[TelemetrySnapshot]:
        """Get recent telemetry history."""
        with self._lock:
            return self._history[-count:] if count else list(self._history)

    def get_stats(self) -> Dict[str, Any]:
        """Get telemetry hub statistics."""
        with self._lock:
            return {
                "subscriber_count": len(self._subscribers),
                "history_count": len(self._history),
                "latest_ts": self._latest.ts if self._latest else None,
            }


# Factory function for creating hub instances
def create_telemetry_hub(max_history: int = 600) -> TelemetryHub:
    """Create a new TelemetryHub instance."""
    return TelemetryHub(max_history=max_history)

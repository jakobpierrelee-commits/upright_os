"""
Watchdog - Connection monitoring and timeout handling.

Monitors serial connection health and manages reconnection logic.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


@dataclass
class WatchdogConfig:
    """Watchdog configuration."""
    heartbeat_interval_s: float = 1.0
    timeout_s: float = 5.0
    max_reconnect_attempts: int = 3
    reconnect_delay_s: float = 1.0


@dataclass
class WatchdogState:
    """Current watchdog state."""
    is_healthy: bool = False
    last_heartbeat_ts: Optional[float] = None
    consecutive_failures: int = 0
    last_error: Optional[str] = None


class Watchdog:
    """
    Monitors connection health and triggers recovery actions.
    
    Thread-safe watchdog that periodically checks connection status
    and invokes callbacks on state changes.
    """

    def __init__(
        self,
        config: Optional[WatchdogConfig] = None,
        on_healthy: Optional[Callable[[], None]] = None,
        on_unhealthy: Optional[Callable[[str], None]] = None,
        on_reconnect: Optional[Callable[[], bool]] = None,
    ):
        self.config = config or WatchdogConfig()
        self._on_healthy = on_healthy
        self._on_unhealthy = on_unhealthy
        self._on_reconnect = on_reconnect
        
        self._state = WatchdogState()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start watchdog monitoring."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop watchdog monitoring."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def heartbeat(self) -> None:
        """Record a successful heartbeat."""
        with self._lock:
            self._state.last_heartbeat_ts = time.time()
            self._state.consecutive_failures = 0
            if not self._state.is_healthy:
                self._state.is_healthy = True
                self._state.last_error = None
                if self._on_healthy:
                    self._on_healthy()

    def mark_failure(self, error: str) -> None:
        """Record a connection failure."""
        with self._lock:
            self._state.consecutive_failures += 1
            self._state.last_error = error
            if self._state.is_healthy:
                self._state.is_healthy = False
                if self._on_unhealthy:
                    self._on_unhealthy(error)

    def get_state(self) -> Dict[str, Any]:
        """Get current watchdog state."""
        with self._lock:
            return {
                "is_healthy": self._state.is_healthy,
                "last_heartbeat_ts": self._state.last_heartbeat_ts,
                "consecutive_failures": self._state.consecutive_failures,
                "last_error": self._state.last_error,
            }

    def _run(self) -> None:
        """Watchdog monitoring loop."""
        while not self._stop_event.wait(self.config.heartbeat_interval_s):
            with self._lock:
                if self._state.last_heartbeat_ts is None:
                    continue
                    
                elapsed = time.time() - self._state.last_heartbeat_ts
                if elapsed > self.config.timeout_s and self._state.is_healthy:
                    self._state.is_healthy = False
                    self._state.last_error = f"heartbeat_timeout_{elapsed:.1f}s"
                    if self._on_unhealthy:
                        self._on_unhealthy(self._state.last_error)
                    
                    # Attempt reconnection
                    if self._on_reconnect and self._state.consecutive_failures < self.config.max_reconnect_attempts:
                        time.sleep(self.config.reconnect_delay_s)
                        if self._on_reconnect():
                            self._state.is_healthy = True
                            self._state.consecutive_failures = 0
                            self._state.last_error = None
                            if self._on_healthy:
                                self._on_healthy()


# Re-export for backwards compatibility
SerialGateway = None  # Placeholder - actual import from serial_gateway.py

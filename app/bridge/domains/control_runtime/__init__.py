"""
Control Runtime Domain

Handles serial communication, watchdog monitoring, and telemetry streaming.
This is the lowest-level domain for robot interaction.

Components:
- serial_gateway: Serial port abstraction and command execution
- watchdog: Connection monitoring and timeout handling
- telemetry_hub: Real-time telemetry distribution
"""

from .serial_gateway import NanoSerialGateway
from .watchdog import Watchdog, WatchdogConfig, WatchdogState
from .telemetry_hub import TelemetryHub, TelemetrySnapshot, create_telemetry_hub

# Alias for backwards compatibility
SerialGateway = NanoSerialGateway

__all__ = [
    "NanoSerialGateway",
    "SerialGateway",
    "Watchdog",
    "WatchdogConfig",
    "WatchdogState",
    "TelemetryHub",
    "TelemetrySnapshot",
    "create_telemetry_hub",
]

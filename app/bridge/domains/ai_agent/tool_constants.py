"""
Tool Constants - Shared constants for AI agent tools.

Canonical limits, error codes, and field mappings used across tool modules.
Extracted from codex_tools.py for domain organization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


class ObservationLimits:
    """Canonical limits for T1/T2 tools. Do not hardcode elsewhere."""

    MAX_OBSERVE_DURATION_S = 30
    MAX_BASELINE_DURATION_S = 15
    MAX_EXPERIMENT_DURATION_S = 60
    MAX_WRITES_PER_CALL = 3
    EXPERIMENT_COOLDOWN_S = 5
    DEFAULT_SAMPLE_RATE_HZ = 8
    MAX_BURST_ROWS = 3000
    BURST_ROW_CHAR_LIMIT = 500
    SERIAL_TIMEOUT_S = 2
    WEBSOCKET_TIMEOUT_S = 5
    TRIGGER_TIMEOUT_S = 30


# Valid robot modes for safety checks
SAFE_MODES = frozenset({"SAFE_IDLE", "IDLE", "ARMED", "BALANCING"})

# Telemetry field mapping (runtime key -> logical name)
TELEMETRY_FIELDS = {
    "ang": "angle",
    "raw": "raw_angle",
    "gyro": "gyro",
    "gyr": "gyro",
    "gx": "gyro",
    "out": "output",
    "mode": "mode",
    "estop": "estop",
    "set": "setpoint",
    "kp": "kp",
    "ki": "ki",
    "kd": "kd",
}

# Safe serial commands (allowlist)
SAFE_COMMANDS = frozenset(
    [
        "PID",
        "SETPOINT",
        "MOTION",
        "LIMITS",
        "CAL ZERO",
        "ZERO",
        "ENCMODE",
        "SAVECFG",
        "LOADCFG",
        "GET",
        "HELP",
        "LOGT",
        "LOGCSV",
    ]
)

# Blocked serial commands (require UI action)
BLOCKED_COMMANDS = frozenset(
    [
        "ARM",
        "DISARM",
        "STATE",
        "MOTOR",
        "MOTOROFF",
        "DEFAULTCFG",
        "BURSTCSV",
    ]
)

# Safe sketch variables (allowlist)
SAFE_SKETCH_VARIABLES = frozenset(
    [
        "qAngle",
        "qBias",
        "rMeasure",
        "LOOP_US",
        "TEL_MS",
        "STATUS_MS",
        "ARM_HOLD_MS",
        "burstTarget",
        "burstDelayMs",
        "BURST_BAL_ERR_DEG",
        "BURST_STABLE_HOLD_MS",
        "deadbandPwm",
    ]
)

# Blocked sketch variables (pin/mode constants)
BLOCKED_SKETCH_VARIABLES = frozenset(
    [
        "PIN_",
        "MOTOR_L_PWM",
        "MOTOR_R_PWM",
        "IMU_SDA",
        "IMU_SCL",
        "MODE_",
        "STATE_",
        "CONFIG_MAGIC",
        "CONFIG_VERSION",
    ]
)

# Factory default PID values
FACTORY_DEFAULTS = {
    "kp": 18.0,
    "ki": 0.1,
    "kd": 0.6,
    "setpoint": 0.0,
    "max_output": 255,
    "deadband": 0,
}

# Rating hierarchy for checkpoint selection
RATING_HIERARCHY = ["great", "good", "ok", "bad"]

# Default robot physical parameters for simulation
ROBOT_DEFAULTS = {
    "mass_kg": 0.2,
    "height_m": 0.15,
    "wheel_radius_m": 0.033,
    "loop_period_ms": 10,
    "gravity": 9.81,
}

# PID tuning heuristics thresholds
TUNING_THRESHOLDS = {
    "oscillation_freq_high_hz": 3.0,
    "oscillation_freq_low_hz": 1.0,
    "saturation_warning_pct": 60,
    "saturation_critical_pct": 85,
    "angle_variance_good": 2.0,
    "angle_variance_acceptable": 5.0,
}


class T1Errors:
    """T1 (observation) error codes."""

    E_WS_CONNECT_FAILED = "E_WS_CONNECT_FAILED"
    E_WS_NO_DATA = "E_WS_NO_DATA"
    E_WS_DISCONNECT = "E_WS_DISCONNECT"
    E_WS_NO_SAMPLES = "E_WS_NO_SAMPLES"
    E_SERIAL_DISCONNECTED = "E_SERIAL_DISCONNECTED"
    E_TRIGGER_TIMEOUT = "E_TRIGGER_TIMEOUT"
    E_NO_BURST_DATA = "E_NO_BURST_DATA"
    E_BURST_IN_PROGRESS = "E_BURST_IN_PROGRESS"
    E_CSV_NOT_FOUND = "E_CSV_NOT_FOUND"
    E_NO_BURST_SAMPLES = "E_NO_BURST_SAMPLES"


class T2Errors:
    """T2 (mutation) error codes."""

    E_NO_CHECKPOINT = "E_NO_CHECKPOINT"
    E_CHECKPOINT_NOT_FOUND = "E_CHECKPOINT_NOT_FOUND"
    E_NO_DB = "E_NO_DB"
    E_SERIAL_BUSY = "E_SERIAL_BUSY"
    E_COMMAND_FAILED = "E_COMMAND_FAILED"
    E_INVALID_CHANGE = "E_INVALID_CHANGE"
    E_BLOCKED_COMMAND = "E_BLOCKED_COMMAND"
    E_EDIT_PARSE_ERROR = "E_EDIT_PARSE_ERROR"
    E_EDIT_OUT_OF_RANGE = "E_EDIT_OUT_OF_RANGE"
    E_EDIT_VALIDATION_FAILED = "E_EDIT_VALIDATION_FAILED"
    E_SKETCH_NOT_FOUND = "E_SKETCH_NOT_FOUND"
    E_SKETCH_READ_ERROR = "E_SKETCH_READ_ERROR"
    E_SKETCH_WRITE_ERROR = "E_SKETCH_WRITE_ERROR"
    E_SKETCH_NO_MATCH = "E_SKETCH_NO_MATCH"
    E_COMPILE_FAILED = "E_COMPILE_FAILED"
    E_UPLOAD_NOT_CONFIRMED = "E_UPLOAD_NOT_CONFIRMED"
    E_UPLOAD_FAILED = "E_UPLOAD_FAILED"
    E_BASELINE_FAILED = "E_BASELINE_FAILED"
    E_REVERT_FAILED = "E_REVERT_FAILED"


class T3Errors:
    """T3 (experiment) error codes."""

    E_EXPERIMENT_ALREADY_RUNNING = "E_EXPERIMENT_ALREADY_RUNNING"
    E_EXPERIMENT_COOLDOWN = "E_EXPERIMENT_COOLDOWN"
    E_EXPERIMENT_BASELINE_FAILED = "E_EXPERIMENT_BASELINE_FAILED"
    E_EXPERIMENT_INVALID_PARAM = "E_EXPERIMENT_INVALID_PARAM"
    E_EXPERIMENT_UNSAFE_STATE = "E_EXPERIMENT_UNSAFE_STATE"
    E_EXPERIMENT_TIMEOUT = "E_EXPERIMENT_TIMEOUT"
    E_EXPERIMENT_ABORTED = "E_EXPERIMENT_ABORTED"
    E_SIMULATION_FAILED = "E_SIMULATION_FAILED"
    E_SIMULATION_INVALID_PARAMS = "E_SIMULATION_INVALID_PARAMS"
    E_SUGGESTION_NO_DATA = "E_SUGGESTION_NO_DATA"
    E_ANNOTATION_FAILED = "E_ANNOTATION_FAILED"


@dataclass
class ToolResult:
    """Standard result from tool execution."""

    ok: bool
    tool: str
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    execution_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "tool": self.tool,
            "data": self.data,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
        }

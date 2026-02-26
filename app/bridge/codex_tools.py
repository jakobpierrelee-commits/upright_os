"""
Codex Tools Module - Tool implementations for AI agent.

Provides:
- get_probe_results: Read hardware state
- query_telemetry: Query historical telemetry
- query_checkpoints: Query saved checkpoints
- search_docs: RAG search
- execute_command: Safe serial command execution (allowlist enforced)
- edit_sketch_value: Edit compile-time params (allowlist enforced)
- generate_sketch: Template-based sketch generation
- compile_firmware: Compile sketch
- upload_firmware: Upload with confirmation gate

All tools return structured results with ok/error fields.
Tool invocations are logged for auditability.
"""

from __future__ import annotations

import csv
import json
import logging
import math
import os
import re
import subprocess
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# Canonical Observation Limits (from PRD)
# ============================================================================


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
    "gyr": "gyro",  # fallback
    "gx": "gyro",  # fallback
    "out": "output",
    "mode": "mode",
    "estop": "estop",
    "set": "setpoint",
    "kp": "kp",
    "ki": "ki",
    "kd": "kd",
}


# T1 Error Codes
class T1Errors:
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


# T2 Error Codes
class T2Errors:
    E_NO_CHECKPOINT = "E_NO_CHECKPOINT"
    E_CHECKPOINT_NOT_FOUND = "E_CHECKPOINT_NOT_FOUND"
    E_NO_DB = "E_NO_DB"
    E_SERIAL_BUSY = "E_SERIAL_BUSY"
    E_COMMAND_FAILED = "E_COMMAND_FAILED"
    E_INVALID_CHANGE = "E_INVALID_CHANGE"
    E_BLOCKED_COMMAND = "E_BLOCKED_COMMAND"
    E_EXPERIMENT_FAILED = "E_EXPERIMENT_FAILED"
    E_BASELINE_FAILED = "E_BASELINE_FAILED"
    E_REVERT_FAILED = "E_REVERT_FAILED"


# Factory default PID values (from firmware constants)
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


# T3 Error Codes
class T3Errors:
    E_INVALID_PID = "E_INVALID_PID"
    E_SIMULATION_FAILED = "E_SIMULATION_FAILED"
    E_NO_TELEMETRY = "E_NO_TELEMETRY"
    E_SUGGESTION_FAILED = "E_SUGGESTION_FAILED"


# Default robot physical parameters for simulation
ROBOT_DEFAULTS = {
    "mass_kg": 0.2,  # 200g typical balance bot
    "height_m": 0.15,  # 15cm pendulum height
    "wheel_radius_m": 0.033,  # 33mm wheel radius
    "loop_period_ms": 10,  # 10ms control loop
    "gravity": 9.81,
}

# PID tuning heuristics thresholds
TUNING_THRESHOLDS = {
    "oscillation_freq_high_hz": 3.0,  # >3Hz suggests derivative issues
    "oscillation_freq_low_hz": 1.0,  # <1Hz suggests integral issues
    "saturation_warning_pct": 60,  # Output saturation warning
    "saturation_critical_pct": 85,  # Output saturation critical
    "angle_variance_good": 2.0,  # Good variance threshold
    "angle_variance_acceptable": 5.0,  # Acceptable variance threshold
}

# ============================================================================
# Command Safety Configuration
# ============================================================================

# Commands that are SAFE for the agent to execute without confirmation
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

SHELL_MAX_TIMEOUT_S = int(os.environ.get("CODEX_SHELL_MAX_TIMEOUT_S", "120"))

# Commands that are BLOCKED - require human action through UI
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

# Sketch variables that are SAFE to edit
SAFE_SKETCH_VARIABLES = frozenset(
    [
        # Kalman filter params
        "qAngle",
        "qBias",
        "rMeasure",
        # Timing constants
        "LOOP_US",
        "TEL_MS",
        "STATUS_MS",
        "ARM_HOLD_MS",
        # Burst logger
        "burstTarget",
        "burstDelayMs",
        "BURST_BAL_ERR_DEG",
        "BURST_STABLE_HOLD_MS",
        # Limits
        "deadbandPwm",
    ]
)

# Sketch variables that are BLOCKED
BLOCKED_SKETCH_VARIABLES = frozenset(
    [
        # Pin assignments
        "PIN_",
        "MOTOR_L_PWM",
        "MOTOR_R_PWM",
        "IMU_SDA",
        "IMU_SCL",
        # Mode enums
        "MODE_",
        "STATE_",
        # Magic constants
        "CONFIG_MAGIC",
        "CONFIG_VERSION",
    ]
)


# ============================================================================
# Tool Result Types
# ============================================================================


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


# ============================================================================
# Tool Definitions (OpenAI Function Calling Format)
# ============================================================================

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_probe_results",
            "description": "Get current compatibility test, connect probe, and validation results for the connected robot. Use this to understand what hardware is connected before making changes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "probe_type": {
                        "type": "string",
                        "enum": ["compat", "connect", "all"],
                        "description": "Type of probe results to fetch. Default 'all'.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_telemetry",
            "description": "Query historical telemetry data for this robot. Returns angle, output, PID values over time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "minutes": {
                        "type": "integer",
                        "description": "How many minutes of history to fetch. Default 5.",
                    },
                    "robot_id": {
                        "type": "string",
                        "description": "Robot ID to query. If omitted, uses current robot.",
                    },
                    "aggregation": {
                        "type": "string",
                        "enum": ["raw", "stats", "trend"],
                        "description": "How to aggregate results. 'raw' returns samples, 'stats' returns summary statistics, 'trend' returns change direction.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_checkpoints",
            "description": "Query saved tuning checkpoints. Checkpoints are user-rated snapshots of tuning state.",
            "parameters": {
                "type": "object",
                "properties": {
                    "rating": {
                        "type": "string",
                        "enum": ["poor", "ok", "good", "great"],
                        "description": "Filter by rating.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max checkpoints to return. Default 10.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_docs",
            "description": "Search documentation and knowledge base for relevant information about tuning, troubleshooting, or robot building.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query.",
                    },
                    "k": {
                        "type": "integer",
                        "description": "Number of results to return. Default 5.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_shell",
            "description": "Execute a terminal command in the project workspace and return stdout/stderr. Use for build/test/lint/git/file-inspection workflows.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cmd": {
                        "type": "string",
                        "description": "Shell command to run, e.g. 'npm run -s build' or 'rg -n \"TODO\" app/'.",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Optional working directory relative to repo root.",
                    },
                    "timeout_s": {
                        "type": "integer",
                        "description": "Optional timeout in seconds (max 120 by default).",
                    },
                },
                "required": ["cmd"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_command",
            "description": "Execute a safe tuning command on the robot via serial. Only allowed commands: PID, SETPOINT, MOTION, LIMITS, CAL ZERO, ENCMODE, SAVECFG. Blocked: ARM, DISARM, STATE, MOTOR.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cmd": {
                        "type": "string",
                        "description": "The command to execute, e.g. 'PID 18 0.1 0.6' or 'SETPOINT 0'.",
                    },
                },
                "required": ["cmd"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_sketch_value",
            "description": "Edit a compile-time constant in the firmware sketch. Requires recompile to take effect. Allowed: Kalman params (qAngle, qBias, rMeasure), timing (LOOP_US, TEL_MS). Blocked: pin assignments, mode enums.",
            "parameters": {
                "type": "object",
                "properties": {
                    "variable": {
                        "type": "string",
                        "description": "Variable name to edit, e.g. 'qAngle' or 'LOOP_US'.",
                    },
                    "value": {
                        "type": "string",
                        "description": "New value as string, e.g. '0.001' or '4000'.",
                    },
                    "sketch_path": {
                        "type": "string",
                        "description": "Path to sketch file. If omitted, uses active sketch.",
                    },
                },
                "required": ["variable", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_sketch",
            "description": "Read the current Arduino sketch source (.ino). Use this before proposing code edits when user asks to inspect current firmware.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sketch_path": {
                        "type": "string",
                        "description": "Path to sketch folder or .ino file. If omitted, uses active sketch.",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "Maximum characters to return (default 12000, max 50000).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_sketch",
            "description": "Generate a new firmware sketch from requirements for the detected hardware. Existing/example sketches are references only; do not preserve template logic unless explicitly requested. Creates a new sketch directory and does not overwrite existing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name for the new sketch, e.g. 'my_balancer_v1'.",
                    },
                    "base_template": {
                        "type": "string",
                        "enum": ["balance_v2", "minimal"],
                        "description": "Base template to use. Default 'balance_v2'.",
                    },
                    "features": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Features to include, e.g. ['kalman_filter', 'motion_control', 'burst_logger'].",
                    },
                    "custom_instructions": {
                        "type": "string",
                        "description": "Additional requirements in natural language.",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compile_firmware",
            "description": "Compile the firmware sketch. Does NOT upload. Use this to verify changes before uploading.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sketch_path": {
                        "type": "string",
                        "description": "Path to sketch folder. If omitted, uses active sketch.",
                    },
                    "board": {
                        "type": "string",
                        "description": "Board FQBN, e.g. 'arduino:avr:nano'. If omitted, uses configured board.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "upload_firmware",
            "description": "Upload compiled firmware to the robot. REQUIRES user confirmation - will return a confirmation_token that must be approved in UI before upload proceeds.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sketch_path": {
                        "type": "string",
                        "description": "Path to sketch folder.",
                    },
                    "confirmation_token": {
                        "type": "string",
                        "description": "Confirmation token from previous upload request. Required for actual upload.",
                    },
                },
                "required": [],
            },
        },
    },
    # ========================================================================
    # T1: Feedback Loop Tools
    # ========================================================================
    {
        "type": "function",
        "function": {
            "name": "observe_telemetry",
            "description": "Watch live telemetry for N seconds and analyze stability, oscillation, output saturation, and settling behavior. Returns real-time metrics for tuning feedback. Read-only, does not send commands.",
            "parameters": {
                "type": "object",
                "properties": {
                    "duration_s": {
                        "type": "number",
                        "description": "Observation duration in seconds. Default 5, max 30.",
                        "default": 5,
                    },
                    "sample_rate_hz": {
                        "type": "number",
                        "description": "Target sample rate. Default matches telemetry feed (~8Hz).",
                        "default": 8,
                    },
                    "metrics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Metrics to compute: angle_variance, angle_mean, angle_peak, output_mean, output_saturation_pct, oscillation_detected, settling_time_ms",
                        "default": [
                            "angle_variance",
                            "output_saturation_pct",
                            "oscillation_detected",
                        ],
                    },
                    "trigger": {
                        "type": "string",
                        "enum": ["immediate", "on_arm", "on_balance"],
                        "description": "When to start observation. Default immediate.",
                        "default": "immediate",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_burst_capture",
            "description": "Read and analyze burst CSV capture data. Returns frequency spectrum, peak oscillation amplitude, phase lag between angle and output. Read-only.",
            "parameters": {
                "type": "object",
                "properties": {
                    "capture_id": {
                        "type": "string",
                        "description": "Burst capture ID or 'latest' for most recent.",
                        "default": "latest",
                    },
                    "analysis": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "fft",
                                "peak_detect",
                                "phase_lag",
                                "envelope",
                                "stats",
                                "raw",
                            ],
                        },
                        "description": "Analysis types to perform.",
                        "default": ["stats", "peak_detect"],
                    },
                    "freq_range_hz": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Frequency range for FFT analysis [min, max]. Default [0.5, 25].",
                        "default": [0.5, 25],
                    },
                },
                "required": [],
            },
        },
    },
    # ========================================================================
    # T2: Experimentation Tools
    # ========================================================================
    {
        "type": "function",
        "function": {
            "name": "diff_config",
            "description": "Compare current runtime configuration to a checkpoint or baseline. Shows what parameters differ with delta percentages. Read-only.",
            "parameters": {
                "type": "object",
                "properties": {
                    "compare_to": {
                        "type": "string",
                        "enum": [
                            "checkpoint",
                            "factory",
                            "session_start",
                            "snapshot_id",
                        ],
                        "description": "What to compare against. Default 'checkpoint' uses best-rated checkpoint.",
                        "default": "checkpoint",
                    },
                    "checkpoint_id": {
                        "type": "string",
                        "description": "Checkpoint ID if compare_to='checkpoint'. Omit for best-rated.",
                    },
                    "snapshot_id": {
                        "type": "string",
                        "description": "Config snapshot ID if compare_to='snapshot_id'.",
                    },
                    "include_sketch": {
                        "type": "boolean",
                        "description": "Include sketch compile-time values in diff.",
                        "default": False,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "safe_rollback",
            "description": "Revert to the most recent checkpoint with specified minimum rating. Faster than manual UI rollback.",
            "parameters": {
                "type": "object",
                "properties": {
                    "min_rating": {
                        "type": "string",
                        "enum": ["ok", "good", "great"],
                        "description": "Minimum checkpoint rating to consider. Default 'good'.",
                        "default": "good",
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["pid", "all_runtime", "motion", "limits"],
                        "description": "What to revert. 'pid' = PID params only, 'all_runtime' = all serial-settable params.",
                        "default": "pid",
                    },
                    "checkpoint_id": {
                        "type": "string",
                        "description": "Specific checkpoint ID. If omitted, uses most recent matching min_rating.",
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, show what would change without applying.",
                        "default": False,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_experiment",
            "description": "Run controlled experiment: capture baseline, apply change, observe effect, compare, optionally auto-revert if criteria not met.",
            "parameters": {
                "type": "object",
                "properties": {
                    "change": {
                        "type": "object",
                        "description": "Change to apply. Either {cmd: 'PID 18 0.1 0.6'} or {variable: 'qAngle', value: '0.001'}",
                        "properties": {
                            "cmd": {"type": "string"},
                            "variable": {"type": "string"},
                            "value": {"type": "string"},
                        },
                    },
                    "baseline_s": {
                        "type": "number",
                        "description": "Seconds to observe baseline before change. Default 5.",
                        "default": 5,
                    },
                    "observe_s": {
                        "type": "number",
                        "description": "Seconds to observe after change. Default 10.",
                        "default": 10,
                    },
                    "auto_revert": {
                        "type": "boolean",
                        "description": "Automatically revert if success_criteria not met. Default true.",
                        "default": True,
                    },
                    "success_criteria": {
                        "type": "object",
                        "description": "Thresholds for success. If any exceeded and auto_revert=true, reverts.",
                        "properties": {
                            "max_angle_variance": {"type": "number"},
                            "max_output_saturation_pct": {"type": "number"},
                            "no_oscillation": {"type": "boolean"},
                        },
                        "default": {
                            "max_angle_variance": 5.0,
                            "max_output_saturation_pct": 80,
                            "no_oscillation": True,
                        },
                    },
                    "description": {
                        "type": "string",
                        "description": "Human-readable description for logging.",
                    },
                },
                "required": ["change"],
            },
        },
    },
    # ========================================================================
    # T3: Intelligence Tools
    # ========================================================================
    {
        "type": "function",
        "function": {
            "name": "simulate_pid_response",
            "description": "Simulate PID step response offline using inverted pendulum model. Predicts settling time, overshoot, stability without affecting the robot.",
            "parameters": {
                "type": "object",
                "properties": {
                    "proposed_pid": {
                        "type": "object",
                        "description": "PID values to simulate: {Kp, Ki, Kd}",
                        "properties": {
                            "Kp": {"type": "number"},
                            "Ki": {"type": "number"},
                            "Kd": {"type": "number"},
                        },
                        "required": ["Kp", "Ki", "Kd"],
                    },
                    "step_size_deg": {
                        "type": "number",
                        "description": "Step disturbance size in degrees. Default 5.",
                        "default": 5,
                    },
                    "duration_s": {
                        "type": "number",
                        "description": "Simulation duration. Default 3.",
                        "default": 3,
                    },
                    "compare_to_current": {
                        "type": "boolean",
                        "description": "Also simulate current PID for comparison.",
                        "default": True,
                    },
                },
                "required": ["proposed_pid"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_next_step",
            "description": "Analyze current tuning state and suggest the most promising next action based on telemetry patterns and successful historical sessions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "context": {
                        "type": "string",
                        "description": "User's goal or problem description.",
                        "default": "",
                    },
                    "include_rationale": {
                        "type": "boolean",
                        "description": "Include detailed reasoning for suggestion.",
                        "default": True,
                    },
                    "max_suggestions": {
                        "type": "integer",
                        "description": "Number of suggestions to return. Default 3.",
                        "default": 3,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "annotate_session",
            "description": "Add annotation to current session timeline. Useful for marking experiments, observations, and learnings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note": {
                        "type": "string",
                        "description": "Annotation text. What happened, what was learned.",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags for categorization: 'oscillation', 'breakthrough', 'failed_experiment', etc.",
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["info", "success", "warning", "failure"],
                        "description": "Annotation severity/type.",
                        "default": "info",
                    },
                    "related_config": {
                        "type": "object",
                        "description": "Config snapshot to associate with this annotation.",
                    },
                    "ts": {
                        "type": "number",
                        "description": "Timestamp to annotate. Default is now.",
                    },
                },
                "required": ["note"],
            },
        },
    },
]


# ============================================================================
# Tool Executor Class
# ============================================================================


class CodexToolExecutor:
    """
    Executes tools with safety enforcement and logging.

    Requires injection of dependencies:
    - gateway: Serial gateway for commands
    - db: CodexDB for telemetry/checkpoints
    - rag: CodexRAG for doc search
    - firmware_module: For compile/upload
    - probe_funcs: Dict of probe functions
    - host_capture: HostCaptureManager for burst captures
    """

    def __init__(
        self,
        gateway: Any = None,
        db: Any = None,
        rag: Any = None,
        firmware_module: Any = None,
        probe_funcs: Optional[Dict[str, Callable]] = None,
        repo_root: Optional[Path] = None,
        active_sketch_path: Optional[str] = None,
        active_robot_id: Optional[str] = None,
        board_fqbn: Optional[str] = None,
        port: Optional[str] = None,
        host_capture: Any = None,
    ):
        self.gateway = gateway
        self.db = db
        self.rag = rag
        self.firmware = firmware_module
        self.probe_funcs = probe_funcs or {}
        self.repo_root = (
            Path(repo_root)
            if repo_root is not None
            else Path(__file__).parent.parent.parent
        )
        self.active_sketch_path = active_sketch_path
        self.active_robot_id = active_robot_id or "default"
        self.board_fqbn = board_fqbn or "arduino:avr:nano"
        self.port = port
        self.host_capture = host_capture

        # Pending upload confirmations: token -> request_data
        self._pending_uploads: Dict[str, Dict[str, Any]] = {}
        # Trusted upload window: one explicit approval can authorize repeated
        # uploads for the same sketch/board/port for a short period.
        self._upload_trust_window_s = int(
            os.environ.get("CODEX_UPLOAD_TRUST_WINDOW_S", "900")
        )
        self._upload_trust: Optional[Dict[str, Any]] = None

    def _build_upload_signature(
        self, sketch_path: str, board: str, port: Optional[str]
    ) -> str:
        sketch_norm = str(Path(sketch_path).resolve()) if sketch_path else ""
        board_norm = (board or "").strip()
        port_norm = (port or "").strip()
        return f"{sketch_norm}|{board_norm}|{port_norm}"

    def _is_upload_trusted(self, signature: str) -> bool:
        if not self._upload_trust:
            return False
        if self._upload_trust.get("signature") != signature:
            return False
        return time.time() < float(self._upload_trust.get("expires_at", 0))

    def _grant_upload_trust(
        self, sketch_path: str, board: str, port: Optional[str]
    ) -> None:
        now = time.time()
        self._upload_trust = {
            "signature": self._build_upload_signature(sketch_path, board, port),
            "granted_at": now,
            "expires_at": now + max(0, self._upload_trust_window_s),
        }

    def execute(self, tool_name: str, arguments: Dict[str, Any]) -> ToolResult:
        """
        Execute a tool by name with given arguments.
        Returns ToolResult with ok/error status.
        """
        start_time = time.time()

        logger.info(f"Tool call: {tool_name} with args: {json.dumps(arguments)}")

        try:
            handler = getattr(self, f"_tool_{tool_name}", None)
            if handler is None:
                return ToolResult(
                    ok=False,
                    tool=tool_name,
                    error=f"Unknown tool: {tool_name}",
                )

            result = handler(arguments)
            result.execution_time_ms = (time.time() - start_time) * 1000

            logger.info(
                f"Tool result: {tool_name} ok={result.ok} time={result.execution_time_ms:.1f}ms"
            )
            return result

        except Exception as e:
            logger.error(f"Tool error: {tool_name} - {e}", exc_info=True)
            return ToolResult(
                ok=False,
                tool=tool_name,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )

    # ========================================================================
    # Tool Implementations
    # ========================================================================

    def _tool_get_probe_results(self, args: Dict[str, Any]) -> ToolResult:
        """Get probe/validation results."""
        probe_type = args.get("probe_type", "all")

        data: Dict[str, Any] = {}

        if probe_type in ("compat", "all"):
            if "run_compat_probe" in self.probe_funcs:
                try:
                    data["compat"] = self.probe_funcs["run_compat_probe"](self.gateway)
                except Exception as e:
                    data["compat_error"] = str(e)

        if probe_type in ("connect", "all"):
            if "run_connect_probe" in self.probe_funcs:
                try:
                    data["connect"] = self.probe_funcs["run_connect_probe"](
                        self.gateway
                    )
                except Exception as e:
                    data["connect_error"] = str(e)

        # Also include current status if gateway available
        if self.gateway:
            try:
                data["status"] = self.gateway.get_status()
                data["health"] = self.gateway.health()
            except Exception as e:
                data["status_error"] = str(e)

        return ToolResult(ok=True, tool="get_probe_results", data=data)

    def _tool_query_telemetry(self, args: Dict[str, Any]) -> ToolResult:
        """Query telemetry from database."""
        if not self.db:
            return ToolResult(
                ok=False, tool="query_telemetry", error="Database not configured"
            )

        minutes = args.get("minutes", 5)
        robot_id = args.get("robot_id", self.active_robot_id)
        aggregation = args.get("aggregation", "stats")

        end_ts = time.time()
        start_ts = end_ts - (minutes * 60)

        snapshots = self.db.query_telemetry(
            robot_id=robot_id,
            start_ts=start_ts,
            end_ts=end_ts,
            limit=500,
        )

        if aggregation == "raw":
            data = {
                "count": len(snapshots),
                "samples": [
                    {
                        "ts": s.ts,
                        "ang": s.ang,
                        "raw": s.raw,
                        "out": s.out,
                        "mode": s.mode,
                    }
                    for s in snapshots[:100]  # Limit raw output
                ],
            }
        elif aggregation == "trend":
            # Calculate trends
            if len(snapshots) >= 2:
                first_half = snapshots[len(snapshots) // 2 :]
                second_half = snapshots[: len(snapshots) // 2]
                avg_ang_first = (
                    sum(s.ang for s in first_half) / len(first_half)
                    if first_half
                    else 0
                )
                avg_ang_second = (
                    sum(s.ang for s in second_half) / len(second_half)
                    if second_half
                    else 0
                )
                data = {
                    "count": len(snapshots),
                    "angle_trend": "increasing"
                    if avg_ang_second > avg_ang_first + 0.1
                    else "decreasing"
                    if avg_ang_second < avg_ang_first - 0.1
                    else "stable",
                    "avg_angle_early": round(avg_ang_first, 3),
                    "avg_angle_recent": round(avg_ang_second, 3),
                }
            else:
                data = {"count": len(snapshots), "angle_trend": "insufficient_data"}
        else:  # stats
            if snapshots:
                angles = [s.ang for s in snapshots]
                outputs = [s.out for s in snapshots]
                data = {
                    "count": len(snapshots),
                    "time_range_minutes": minutes,
                    "angle": {
                        "min": round(min(angles), 3),
                        "max": round(max(angles), 3),
                        "avg": round(sum(angles) / len(angles), 3),
                    },
                    "output": {
                        "min": round(min(outputs), 1),
                        "max": round(max(outputs), 1),
                        "avg": round(sum(outputs) / len(outputs), 1),
                    },
                    "latest_mode": snapshots[0].mode if snapshots else None,
                }
            else:
                data = {"count": 0, "message": "No telemetry data in time range"}

        return ToolResult(ok=True, tool="query_telemetry", data=data)

    def _tool_query_checkpoints(self, args: Dict[str, Any]) -> ToolResult:
        """Query checkpoints from database."""
        if not self.db:
            return ToolResult(
                ok=False, tool="query_checkpoints", error="Database not configured"
            )

        rating = args.get("rating")
        limit = args.get("limit", 10)

        checkpoints = self.db.query_checkpoints(
            robot_id=self.active_robot_id,
            rating=rating,
            limit=limit,
        )

        data = {
            "count": len(checkpoints),
            "checkpoints": [
                {
                    "id": c.id,
                    "ts": c.ts,
                    "rating": c.rating,
                    "mode": c.mode,
                    "pid": {"kp": c.kp, "ki": c.ki, "kd": c.kd},
                    "motion": {"kv": c.kv, "kx": c.kx},
                    "setpoint": c.setpoint,
                    "notes": c.notes,
                }
                for c in checkpoints
            ],
        }

        return ToolResult(ok=True, tool="query_checkpoints", data=data)

    def _tool_search_docs(self, args: Dict[str, Any]) -> ToolResult:
        """Search documentation via RAG."""
        if not self.rag:
            return ToolResult(ok=False, tool="search_docs", error="RAG not configured")

        query = args.get("query", "")
        k = args.get("k", 5)

        if not query:
            return ToolResult(ok=False, tool="search_docs", error="Query is required")

        results = self.rag.search_docs(query, k=k, min_score=0.4)

        data = {
            "count": len(results),
            "results": [
                {
                    "source": r.source_path,
                    "score": round(r.score, 3),
                    "content": r.content[:500] + "..."
                    if len(r.content) > 500
                    else r.content,
                }
                for r in results
            ],
        }

        return ToolResult(ok=True, tool="search_docs", data=data)

    def _tool_execute_shell(self, args: Dict[str, Any]) -> ToolResult:
        """Execute terminal command inside repository workspace."""
        cmd = str(args.get("cmd", "")).strip()
        if not cmd:
            return ToolResult(ok=False, tool="execute_shell", error="cmd is required")

        cwd_raw = str(args.get("cwd", "")).strip()
        repo_root = self.repo_root.resolve()
        if cwd_raw:
            target = (repo_root / cwd_raw).resolve()
            try:
                target.relative_to(repo_root)
            except Exception:
                return ToolResult(
                    ok=False,
                    tool="execute_shell",
                    error="cwd must be inside repository root",
                )
        else:
            target = repo_root

        timeout_s = int(args.get("timeout_s", 60) or 60)
        timeout_s = max(1, min(timeout_s, SHELL_MAX_TIMEOUT_S))
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                cwd=str(target),
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            partial_out = str((exc.stdout or "") + "\n" + (exc.stderr or "")).strip()
            return ToolResult(
                ok=False,
                tool="execute_shell",
                error=f"timeout_after_{timeout_s}s",
                data={
                    "cmd": cmd,
                    "cwd": str(target),
                    "partial_output": partial_out[-4000:],
                },
            )
        except Exception as exc:
            return ToolResult(
                ok=False,
                tool="execute_shell",
                error=f"shell_exec_failed:{exc}",
                data={"cmd": cmd, "cwd": str(target)},
            )

        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        merged = "\n".join([x for x in [out, err] if x]).strip()
        return ToolResult(
            ok=(proc.returncode == 0),
            tool="execute_shell",
            data={
                "cmd": cmd,
                "cwd": str(target),
                "exit_code": int(proc.returncode),
                "output": merged[-12000:],
            },
            error=None if proc.returncode == 0 else f"exit_code:{proc.returncode}",
        )

    def _tool_execute_command(self, args: Dict[str, Any]) -> ToolResult:
        """Execute a serial command with safety enforcement."""
        if not self.gateway:
            return ToolResult(
                ok=False, tool="execute_command", error="Serial gateway not connected"
            )

        # Serial busy guard - check if gateway is currently busy
        if hasattr(self.gateway, "is_busy") and self.gateway.is_busy():
            return ToolResult(
                ok=False,
                tool="execute_command",
                error="SERIAL_BUSY: Serial port is currently in use. Please wait and try again.",
                data={"retry_after_ms": 500},
            )

        cmd = args.get("cmd", "").strip()
        if not cmd:
            return ToolResult(
                ok=False, tool="execute_command", error="Command is required"
            )

        # Extract command prefix for allowlist check
        cmd_prefix = cmd.split()[0].upper() if cmd.split() else ""

        # Check if command is blocked
        if cmd_prefix in BLOCKED_COMMANDS:
            return ToolResult(
                ok=False,
                tool="execute_command",
                error=f"Command '{cmd_prefix}' is blocked for safety. Use the UI to execute ARM/DISARM/MOTOR commands.",
            )

        # Check if command is in allowlist
        # Handle compound commands like "CAL ZERO"
        is_safe = False
        for safe_cmd in SAFE_COMMANDS:
            if cmd.upper().startswith(safe_cmd):
                is_safe = True
                break

        if not is_safe:
            return ToolResult(
                ok=False,
                tool="execute_command",
                error=f"Command '{cmd_prefix}' is not in the safe command allowlist: {', '.join(sorted(SAFE_COMMANDS))}",
            )

        # Execute the command
        try:
            result = self.gateway.command(cmd, timeout=3.0)
            status = self.gateway.get_status()

            return ToolResult(
                ok=True,
                tool="execute_command",
                data={
                    "command": cmd,
                    "result": result,
                    "status_after": status,
                },
            )
        except Exception as e:
            return ToolResult(
                ok=False, tool="execute_command", error=f"Command failed: {e}"
            )

    def _tool_edit_sketch_value(self, args: Dict[str, Any]) -> ToolResult:
        """Edit a compile-time constant in sketch with allowlist enforcement."""
        variable = args.get("variable", "")
        value = args.get("value", "")
        sketch_path = args.get("sketch_path", self.active_sketch_path)

        if not variable or not value:
            return ToolResult(
                ok=False,
                tool="edit_sketch_value",
                error="variable and value are required",
            )

        # Check allowlist
        if variable not in SAFE_SKETCH_VARIABLES:
            # Check if it matches any blocked pattern
            for blocked in BLOCKED_SKETCH_VARIABLES:
                if variable.upper().startswith(blocked):
                    return ToolResult(
                        ok=False,
                        tool="edit_sketch_value",
                        error=f"Variable '{variable}' is blocked (matches pattern '{blocked}'). Cannot edit pin assignments or mode constants.",
                    )

            return ToolResult(
                ok=False,
                tool="edit_sketch_value",
                error=f"Variable '{variable}' is not in allowlist: {', '.join(sorted(SAFE_SKETCH_VARIABLES))}",
            )

        if not sketch_path:
            return ToolResult(
                ok=False, tool="edit_sketch_value", error="No sketch path configured"
            )

        # Find the .ino file
        sketch_dir = Path(sketch_path)
        if not sketch_dir.exists():
            sketch_dir = self.repo_root / sketch_path

        ino_files = list(sketch_dir.glob("*.ino"))
        if not ino_files:
            return ToolResult(
                ok=False,
                tool="edit_sketch_value",
                error=f"No .ino file found in {sketch_path}",
            )

        ino_path = ino_files[0]

        try:
            content = ino_path.read_text(encoding="utf-8")
            if not content.strip():
                return ToolResult(
                    ok=False,
                    tool="edit_sketch_value",
                    error=f"Sketch file is empty: {ino_path}",
                )
            original_content = content

            # Pattern for struct member assignment: .variable = value
            # e.g., .qAngle = 0.001f,
            struct_pattern = rf"(\.{re.escape(variable)}\s*=\s*)([^,;]+)([,;])"
            struct_match = re.search(struct_pattern, content)

            # Pattern for #define: #define VARIABLE value
            define_pattern = rf"(#define\s+{re.escape(variable)}\s+)(\S+)"
            define_match = re.search(define_pattern, content)

            # Pattern for const assignment: const ... variable = value;
            const_pattern = rf"((?:const\s+)?(?:float|int|uint\d+_t|int\d+_t)\s+{re.escape(variable)}\s*=\s*)([^;]+)(;)"
            const_match = re.search(const_pattern, content)

            old_value = None
            if struct_match:
                old_value = struct_match.group(2).strip()
                content = re.sub(struct_pattern, rf"\g<1>{value}\g<3>", content)
            elif define_match:
                old_value = define_match.group(2).strip()
                content = re.sub(define_pattern, rf"\g<1>{value}", content)
            elif const_match:
                old_value = const_match.group(2).strip()
                content = re.sub(const_pattern, rf"\g<1>{value}\g<3>", content)
            else:
                return ToolResult(
                    ok=False,
                    tool="edit_sketch_value",
                    error=f"Variable '{variable}' not found in sketch. Searched patterns: struct member, #define, const.",
                )

            if content == original_content:
                return ToolResult(
                    ok=False,
                    tool="edit_sketch_value",
                    error=f"No changes made. Value may already be '{value}'.",
                )

            # Write changes
            ino_path.write_text(content, encoding="utf-8")

            return ToolResult(
                ok=True,
                tool="edit_sketch_value",
                data={
                    "variable": variable,
                    "old_value": old_value,
                    "new_value": value,
                    "file": str(ino_path),
                    "requires_recompile": True,
                },
            )

        except Exception as e:
            return ToolResult(
                ok=False, tool="edit_sketch_value", error=f"Edit failed: {e}"
            )

    def _tool_read_sketch(self, args: Dict[str, Any]) -> ToolResult:
        """Read current sketch source for inspection/debugging."""
        sketch_path = args.get("sketch_path", self.active_sketch_path)
        max_chars = int(args.get("max_chars", 12000) or 12000)
        max_chars = max(500, min(max_chars, 50000))

        if not sketch_path:
            return ToolResult(
                ok=False, tool="read_sketch", error="No sketch path configured"
            )

        try:
            path = Path(sketch_path)
            if not path.exists():
                path = self.repo_root / str(sketch_path)
            if not path.exists():
                return ToolResult(
                    ok=False,
                    tool="read_sketch",
                    error=f"Sketch path not found: {sketch_path}",
                )

            ino_path: Optional[Path] = None
            if path.is_file():
                if path.suffix.lower() != ".ino":
                    return ToolResult(
                        ok=False,
                        tool="read_sketch",
                        error=f"Expected .ino file, got: {path.name}",
                    )
                ino_path = path
            else:
                ino_files = sorted(path.glob("*.ino"))
                if not ino_files:
                    return ToolResult(
                        ok=False,
                        tool="read_sketch",
                        error=f"No .ino file found in {path}",
                    )
                ino_path = ino_files[0]

            content = ino_path.read_text(encoding="utf-8")
            if not content.strip():
                return ToolResult(
                    ok=False,
                    tool="read_sketch",
                    error=f"Sketch file is empty: {ino_path}",
                )
            truncated = False
            if len(content) > max_chars:
                content = content[:max_chars]
                truncated = True

            return ToolResult(
                ok=True,
                tool="read_sketch",
                data={
                    "path": str(ino_path),
                    "content": content,
                    "chars": len(content),
                    "truncated": truncated,
                },
            )
        except Exception as e:
            return ToolResult(ok=False, tool="read_sketch", error=f"Read failed: {e}")

    def _tool_generate_sketch(self, args: Dict[str, Any]) -> ToolResult:
        """Generate a new sketch from template."""
        name = args.get("name", "")
        base_template = args.get("base_template", "balance_v2")
        features = args.get("features", [])
        custom_instructions = args.get("custom_instructions", "")
        unified_error: Optional[str] = None

        if not name:
            return ToolResult(
                ok=False, tool="generate_sketch", error="Sketch name is required"
            )

        # Sanitize name
        safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
        if safe_name != name:
            logger.info(f"Sanitized sketch name: {name} -> {safe_name}")

        # Check if directory already exists
        output_dir = self.repo_root / "generated_firmware" / safe_name
        if output_dir.exists():
            existing_main = output_dir / f"{safe_name}.ino"
            if existing_main.exists() and existing_main.is_file():
                try:
                    if existing_main.stat().st_size <= 0:
                        return ToolResult(
                            ok=False,
                            tool="generate_sketch",
                            error=f"Directory already exists and main sketch is empty: {existing_main}. Delete the folder, then regenerate.",
                        )
                except OSError:
                    pass
            return ToolResult(
                ok=False,
                tool="generate_sketch",
                error=f"Directory already exists: {output_dir}. Choose a different name or delete existing.",
            )

        # For now, delegate to existing firmware generation if available
        if self.firmware and hasattr(self.firmware, "generate_unified"):
            try:
                # Build a complete default profile so unified generation can succeed
                # even when probe metadata is sparse.
                profile: Dict[str, Any] = {
                    "label": name,
                    "board": {
                        "fqbn": self.board_fqbn or "arduino:avr:nano",
                        "port": self.port or "",
                        "mcu_family": "avr",
                    },
                    "hardware": {
                        "imu_type": "mpu6050",
                        "motor_driver": "tb6612",
                    },
                    "pins": {
                        "motor_l_pwm": 5,
                        "motor_l_dir": 4,
                        "motor_r_pwm": 6,
                        "motor_r_dir": 7,
                        "imu_sda": 18,
                        "imu_scl": 19,
                        "gate_enable": 8,
                        "led": 13,
                        "enc_l_a": -1,
                        "enc_l_b": -1,
                        "enc_r_a": -1,
                        "enc_r_b": -1,
                    },
                }

                result = self.firmware.generate_unified(
                    profile=profile, sketch_name=safe_name
                )
                main_file = result.get("main_file")
                main_path = Path(str(main_file)) if isinstance(main_file, str) else None
                main_bytes: Optional[int] = None
                if main_path and main_path.exists() and main_path.is_file():
                    main_bytes = int(main_path.stat().st_size)
                    if main_bytes <= 0:
                        return ToolResult(
                            ok=False,
                            tool="generate_sketch",
                            error=f"Generated sketch is empty: {main_path}",
                        )

                return ToolResult(
                    ok=True,
                    tool="generate_sketch",
                    data={
                        "name": safe_name,
                        "sketch_folder": result.get("sketch_folder"),
                        "main_file": str(main_path) if main_path else "",
                        "main_file_bytes": main_bytes,
                        "features": features,
                        "message": "Sketch generated. Use compile_firmware to verify, then upload_firmware to flash.",
                    },
                )
            except Exception as e:
                # If unified generation fails (often due missing full hardware profile),
                # fall back to deterministic template copy rather than hard-failing.
                unified_error = str(e)
                logger.warning(
                    f"Unified sketch generation failed; falling back to template copy: {unified_error}"
                )

        # Fallback: copy template manually
        template_dir = self.repo_root / "tumbller_v06_nano_balance_v2"
        if not template_dir.exists():
            return ToolResult(
                ok=False, tool="generate_sketch", error="Template directory not found"
            )

        try:
            import shutil

            output_dir.mkdir(parents=True, exist_ok=True)

            # Copy template files
            source_ino_nonempty = False
            for src_file in template_dir.glob("*"):
                if src_file.is_file():
                    dst_file = output_dir / src_file.name
                    # Rename .ino file to match directory
                    if src_file.suffix == ".ino":
                        try:
                            if src_file.stat().st_size > 0:
                                source_ino_nonempty = True
                        except OSError:
                            pass
                        dst_file = output_dir / f"{safe_name}.ino"
                    shutil.copy2(src_file, dst_file)

            main_file = output_dir / f"{safe_name}.ino"
            if not main_file.exists() or not main_file.is_file():
                return ToolResult(
                    ok=False,
                    tool="generate_sketch",
                    error=f"Generated sketch missing main file: {main_file}",
                )
            main_bytes = main_file.stat().st_size
            if main_bytes <= 0:
                if not source_ino_nonempty:
                    return ToolResult(
                        ok=False,
                        tool="generate_sketch",
                        error=(
                            "Fallback template .ino is empty. Regenerate with unified template "
                            "or restore tumbller_v06_nano_balance_v2/tumbller_v06_nano_balance_v2.ino."
                        ),
                    )
                return ToolResult(
                    ok=False,
                    tool="generate_sketch",
                    error=f"Generated sketch is empty: {main_file}",
                )

            return ToolResult(
                ok=True,
                tool="generate_sketch",
                data={
                    "name": safe_name,
                    "sketch_folder": str(output_dir),
                    "main_file": str(main_file),
                    "main_file_bytes": int(main_bytes),
                    "template_used": str(base_template or "balance_v2"),
                    "features": features,
                    "custom_instructions_used": bool(str(custom_instructions).strip()),
                    "unified_generation_error": unified_error,
                    "message": "Sketch created from template. Edit as needed, then compile and upload.",
                },
            )
        except Exception as e:
            return ToolResult(
                ok=False, tool="generate_sketch", error=f"Copy failed: {e}"
            )

    def _tool_compile_firmware(self, args: Dict[str, Any]) -> ToolResult:
        """Compile firmware sketch."""
        sketch_path = args.get("sketch_path", self.active_sketch_path)
        board = args.get("board", self.board_fqbn)

        if not sketch_path:
            return ToolResult(
                ok=False, tool="compile_firmware", error="No sketch path specified"
            )

        if not self.firmware:
            return ToolResult(
                ok=False,
                tool="compile_firmware",
                error="Firmware module not configured",
            )

        try:
            result = self.firmware.compile(sketch=sketch_path, fqbn=board)

            if result.get("ok"):
                return ToolResult(
                    ok=True,
                    tool="compile_firmware",
                    data={
                        "sketch": sketch_path,
                        "board": board,
                        "output": result.get("output", ""),
                        "binary_path": result.get("binary_path"),
                        "message": "Compilation successful. Use upload_firmware to flash to robot.",
                    },
                )
            else:
                return ToolResult(
                    ok=False,
                    tool="compile_firmware",
                    error=f"Compilation failed: {result.get('error', 'Unknown error')}",
                    data={"output": result.get("output", "")},
                )
        except Exception as e:
            return ToolResult(
                ok=False, tool="compile_firmware", error=f"Compile error: {e}"
            )

    def _tool_upload_firmware(self, args: Dict[str, Any]) -> ToolResult:
        """Upload firmware with confirmation gate."""
        sketch_path = args.get("sketch_path", self.active_sketch_path)
        confirmation_token = args.get("confirmation_token")
        board = args.get("board", self.board_fqbn)
        port = args.get("port", self.port)

        if not sketch_path:
            return ToolResult(
                ok=False, tool="upload_firmware", error="No sketch path specified"
            )

        signature = self._build_upload_signature(sketch_path, board, port)

        # If no confirmation token, generate one and request confirmation
        if not confirmation_token:
            if self._is_upload_trusted(signature):
                if not self.firmware:
                    return ToolResult(
                        ok=False,
                        tool="upload_firmware",
                        error="Firmware module not configured",
                    )
                try:
                    result = self.firmware.upload(
                        sketch=sketch_path,
                        fqbn=board,
                        port=port,
                    )

                    if result.get("ok"):
                        return ToolResult(
                            ok=True,
                            tool="upload_firmware",
                            data={
                                "sketch": sketch_path,
                                "board": board,
                                "port": port,
                                "output": result.get("output", ""),
                                "message": "Upload successful (trusted explicit approval window).",
                            },
                        )
                    else:
                        return ToolResult(
                            ok=False,
                            tool="upload_firmware",
                            error=f"Upload failed: {result.get('error', 'Unknown error')}",
                            data={"output": result.get("output", "")},
                        )
                except Exception as e:
                    return ToolResult(
                        ok=False, tool="upload_firmware", error=f"Upload error: {e}"
                    )

            import secrets

            token = secrets.token_hex(16)
            self._pending_uploads[token] = {
                "sketch_path": sketch_path,
                "board": board,
                "port": port,
                "signature": signature,
                "created_at": time.time(),
            }

            return ToolResult(
                ok=False,
                tool="upload_firmware",
                error="CONFIRMATION_REQUIRED",
                data={
                    "confirmation_token": token,
                    "sketch_path": sketch_path,
                    "board": board,
                    "port": port,
                    "message": "Upload requires user confirmation. Approve in UI to proceed.",
                    "action_required": "User must click 'Confirm Upload' in the UI.",
                    "expires_in_s": 300,
                },
            )

        # Validate confirmation token
        if confirmation_token not in self._pending_uploads:
            return ToolResult(
                ok=False,
                tool="upload_firmware",
                error="Invalid or expired confirmation token. Request a new upload.",
            )

        pending = self._pending_uploads.pop(confirmation_token)

        # Check token age (expire after 5 minutes)
        if time.time() - pending["created_at"] > 300:
            return ToolResult(
                ok=False,
                tool="upload_firmware",
                error="Confirmation token expired. Request a new upload.",
            )

        if not self.firmware:
            return ToolResult(
                ok=False, tool="upload_firmware", error="Firmware module not configured"
            )

        try:
            # A validated confirmation token is explicit operator permission.
            # Grant a brief trust window for this exact upload context.
            self._grant_upload_trust(
                pending["sketch_path"], pending["board"], pending["port"]
            )
            result = self.firmware.upload(
                sketch=pending["sketch_path"],
                fqbn=pending["board"],
                port=pending["port"],
            )

            if result.get("ok"):
                return ToolResult(
                    ok=True,
                    tool="upload_firmware",
                    data={
                        "sketch": pending["sketch_path"],
                        "board": pending["board"],
                        "port": pending["port"],
                        "output": result.get("output", ""),
                        "message": "Upload successful! Robot is now running new firmware.",
                    },
                )
            else:
                return ToolResult(
                    ok=False,
                    tool="upload_firmware",
                    error=f"Upload failed: {result.get('error', 'Unknown error')}",
                    data={"output": result.get("output", "")},
                )
        except Exception as e:
            return ToolResult(
                ok=False, tool="upload_firmware", error=f"Upload error: {e}"
            )

    # ========================================================================
    # T1: Feedback Loop Tool Implementations
    # ========================================================================

    def _tool_observe_telemetry(self, args: Dict[str, Any]) -> ToolResult:
        """
        Watch live telemetry for N seconds and compute stability metrics.
        Read-only - does not acquire serial write lock.
        """
        # Check gateway health first (fail fast)
        if not self.gateway:
            return ToolResult(
                ok=False,
                tool="observe_telemetry",
                error=T1Errors.E_SERIAL_DISCONNECTED,
                data={"message": "Serial gateway not configured", "retry_after_s": 5},
            )

        try:
            health = self.gateway.health()
            if not health.get("connected"):
                return ToolResult(
                    ok=False,
                    tool="observe_telemetry",
                    error=T1Errors.E_SERIAL_DISCONNECTED,
                    data={"message": "Serial not connected", "retry_after_s": 5},
                )
        except Exception as e:
            return ToolResult(
                ok=False,
                tool="observe_telemetry",
                error=T1Errors.E_SERIAL_DISCONNECTED,
                data={"message": str(e), "retry_after_s": 5},
            )

        # Parse and validate arguments
        duration_s = min(
            float(args.get("duration_s", 5)), ObservationLimits.MAX_OBSERVE_DURATION_S
        )
        sample_rate_hz = float(
            args.get("sample_rate_hz", ObservationLimits.DEFAULT_SAMPLE_RATE_HZ)
        )
        requested_metrics = args.get(
            "metrics",
            ["angle_variance", "output_saturation_pct", "oscillation_detected"],
        )
        trigger = args.get("trigger", "immediate")

        # Handle trigger modes
        if trigger in ("on_arm", "on_balance"):
            target_mode = "ARMED" if trigger == "on_arm" else "BALANCING"
            trigger_start = time.time()
            while time.time() - trigger_start < ObservationLimits.TRIGGER_TIMEOUT_S:
                try:
                    status = self.gateway.get_status()
                    current_mode = str(status.get("mode", ""))
                    if current_mode == target_mode or (
                        trigger == "on_balance" and current_mode == "BALANCING"
                    ):
                        break
                except Exception:
                    pass
                time.sleep(0.1)
            else:
                return ToolResult(
                    ok=False,
                    tool="observe_telemetry",
                    error=T1Errors.E_TRIGGER_TIMEOUT,
                    data={
                        "message": f"Timeout waiting for {target_mode} mode",
                        "waited_s": ObservationLimits.TRIGGER_TIMEOUT_S,
                    },
                )

        # Collect samples
        samples: List[Dict[str, Any]] = []
        sample_interval = 1.0 / sample_rate_hz
        start_time = time.time()
        last_sample_time = 0.0
        expected_samples = int(duration_s * sample_rate_hz)

        while time.time() - start_time < duration_s:
            now = time.time()
            if now - last_sample_time >= sample_interval:
                try:
                    status = self.gateway.get_status()
                    if status:
                        samples.append(
                            {
                                "ts": now,
                                "ang": float(status.get("ang", 0)),
                                "raw": float(status.get("raw", 0)),
                                "out": float(status.get("out", 0)),
                                "mode": str(status.get("mode", "")),
                                "gyro": float(
                                    status.get(
                                        "gyro", status.get("gyr", status.get("gx", 0))
                                    )
                                ),
                            }
                        )
                        last_sample_time = now
                except Exception:
                    pass  # Skip failed samples
            time.sleep(0.01)  # Small sleep to prevent busy loop

        # Check if we got any samples
        if not samples:
            return ToolResult(
                ok=False,
                tool="observe_telemetry",
                error=T1Errors.E_WS_NO_SAMPLES,
                data={"message": "No samples collected", "duration_s": duration_s},
            )

        # Compute metrics
        metrics = self._compute_observation_metrics(samples, requested_metrics)

        # Determine if partial
        partial = len(samples) < expected_samples * 0.8  # Less than 80% of expected

        result_data = {
            "samples_collected": len(samples),
            "samples_expected": expected_samples,
            "duration_actual_s": round(time.time() - start_time, 2),
            "duration_requested_s": duration_s,
            "sample_rate_actual_hz": round(len(samples) / (time.time() - start_time), 1)
            if samples
            else 0,
            "metrics": metrics,
        }

        if partial:
            result_data["partial"] = True
            result_data["error_code"] = T1Errors.E_WS_DISCONNECT

        return ToolResult(ok=True, tool="observe_telemetry", data=result_data)

    def _compute_observation_metrics(
        self, samples: List[Dict[str, Any]], requested: List[str]
    ) -> Dict[str, Any]:
        """Compute requested metrics from collected samples."""
        metrics: Dict[str, Any] = {}

        if not samples:
            return metrics

        angles = [s["ang"] for s in samples]
        outputs = [s["out"] for s in samples]

        # Always compute sample_count
        metrics["sample_count"] = len(samples)

        if "angle_variance" in requested or "all" in requested:
            metrics["angle_variance"] = (
                round(statistics.variance(angles), 4) if len(angles) > 1 else 0.0
            )

        if "angle_mean" in requested or "all" in requested:
            metrics["angle_mean"] = round(statistics.mean(angles), 4)

        if "angle_peak" in requested or "all" in requested:
            metrics["angle_peak"] = round(max(abs(a) for a in angles), 4)

        if "angle_std" in requested or "all" in requested:
            metrics["angle_std"] = (
                round(statistics.stdev(angles), 4) if len(angles) > 1 else 0.0
            )

        if "output_mean" in requested or "all" in requested:
            metrics["output_mean"] = round(statistics.mean(outputs), 2)

        if "output_saturation_pct" in requested or "all" in requested:
            # Saturation is when |output| > 242 (95% of 255)
            saturated = sum(1 for o in outputs if abs(o) > 242)
            metrics["output_saturation_pct"] = round(100 * saturated / len(outputs), 1)

        if "oscillation_detected" in requested or "all" in requested:
            # Simple oscillation detection via sign changes in angle derivative
            metrics["oscillation_detected"] = self._detect_oscillation(angles)

        if "settling_time_ms" in requested or "all" in requested:
            metrics["settling_time_ms"] = self._compute_settling_time(samples)

        return metrics

    def _detect_oscillation(self, angles: List[float], threshold: float = 0.5) -> bool:
        """Detect oscillation via zero-crossing analysis."""
        if len(angles) < 10:
            return False

        # Compute deviations from mean
        mean_ang = statistics.mean(angles)
        deviations = [a - mean_ang for a in angles]

        # Count sign changes
        sign_changes = 0
        for i in range(1, len(deviations)):
            if deviations[i] * deviations[i - 1] < 0:
                sign_changes += 1

        # If more than 20% of samples have sign changes, likely oscillating
        return sign_changes > len(angles) * 0.2

    def _compute_settling_time(
        self, samples: List[Dict[str, Any]], threshold: float = 1.0
    ) -> Optional[int]:
        """Compute time until angle variance drops below threshold."""
        if len(samples) < 10:
            return None

        window_size = 5
        for i in range(window_size, len(samples)):
            window = [s["ang"] for s in samples[i - window_size : i]]
            if statistics.variance(window) < threshold:
                # Found settling point
                elapsed_ms = int((samples[i]["ts"] - samples[0]["ts"]) * 1000)
                return elapsed_ms

        return None  # Did not settle

    def _tool_read_burst_capture(self, args: Dict[str, Any]) -> ToolResult:
        """
        Read and analyze burst CSV capture data.
        Read-only - reads from files only, no serial interaction.
        """
        capture_id = args.get("capture_id", "latest")
        analysis_types = args.get("analysis", ["stats", "peak_detect"])
        freq_range = args.get("freq_range_hz", [0.5, 25])

        # Get burst status from host_capture
        if not self.host_capture:
            return ToolResult(
                ok=False,
                tool="read_burst_capture",
                error=T1Errors.E_NO_BURST_DATA,
                data={"message": "Host capture manager not configured"},
            )

        try:
            status = self.host_capture.status()
        except Exception as e:
            return ToolResult(
                ok=False,
                tool="read_burst_capture",
                error=T1Errors.E_NO_BURST_DATA,
                data={"message": f"Failed to get burst status: {e}"},
            )

        # Check if burst is in progress
        state = status.get("state", "idle")
        if state == "capturing":
            return ToolResult(
                ok=False,
                tool="read_burst_capture",
                error=T1Errors.E_BURST_IN_PROGRESS,
                data={
                    "message": "Burst capture in progress, cannot read incomplete data",
                    "state": state,
                },
            )

        # Get CSV path
        latest_run = status.get("latest_run")
        if capture_id == "latest":
            if not latest_run:
                return ToolResult(
                    ok=False,
                    tool="read_burst_capture",
                    error=T1Errors.E_NO_BURST_DATA,
                    data={"message": "No burst capture available", "status": status},
                )
            csv_path = Path(latest_run)
        else:
            # Try to find by capture_id (filename prefix)
            results_dir = self.repo_root / "tests" / "results"
            matches = list(results_dir.glob(f"*{capture_id}*.csv"))
            if not matches:
                return ToolResult(
                    ok=False,
                    tool="read_burst_capture",
                    error=T1Errors.E_CSV_NOT_FOUND,
                    data={"message": f"No CSV found matching '{capture_id}'"},
                )
            csv_path = matches[0]

        # Check if file exists
        if not csv_path.exists():
            return ToolResult(
                ok=False,
                tool="read_burst_capture",
                error=T1Errors.E_CSV_NOT_FOUND,
                data={"message": f"CSV file not found: {csv_path}"},
            )

        # Parse CSV
        rows: List[Dict[str, Any]] = []
        warnings: List[str] = []
        truncated = False
        skipped_rows = 0

        try:
            with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                for i, row in enumerate(reader):
                    if i >= ObservationLimits.MAX_BURST_ROWS:
                        truncated = True
                        break
                    try:
                        # Extract key fields with validation
                        parsed = {
                            "ts": float(row.get("host_ts", 0)),
                            "ang": float(row.get("ang", 0)),
                            "out": float(row.get("out", 0)),
                            "gyro": float(row.get("gyro", 0)),
                            "mode": row.get("mode", ""),
                        }
                        rows.append(parsed)
                    except (ValueError, TypeError):
                        skipped_rows += 1
        except Exception as e:
            return ToolResult(
                ok=False,
                tool="read_burst_capture",
                error=T1Errors.E_CSV_NOT_FOUND,
                data={"message": f"Failed to parse CSV: {e}"},
            )

        if skipped_rows > 0:
            warnings.append(f"skipped_rows: {skipped_rows}")

        if not rows:
            return ToolResult(
                ok=False,
                tool="read_burst_capture",
                error=T1Errors.E_NO_BURST_SAMPLES,
                data={
                    "message": "CSV contains no valid data rows",
                    "csv_path": str(csv_path),
                },
            )

        # Compute sample rate from timestamps
        if len(rows) >= 2:
            duration = rows[-1]["ts"] - rows[0]["ts"]
            sample_rate_hz = len(rows) / duration if duration > 0 else 0
        else:
            sample_rate_hz = 0

        # Build result
        result_data: Dict[str, Any] = {
            "capture_id": csv_path.stem,
            "csv_path": str(csv_path),
            "sample_count": len(rows),
            "duration_s": round(rows[-1]["ts"] - rows[0]["ts"], 3)
            if len(rows) > 1
            else 0,
            "sample_rate_hz": round(sample_rate_hz, 1),
        }

        if truncated:
            result_data["truncated"] = True
        if warnings:
            result_data["warnings"] = warnings

        # Run requested analyses
        angles = [r["ang"] for r in rows]
        outputs = [r["out"] for r in rows]

        if "stats" in analysis_types:
            result_data["stats"] = {
                "angle_mean": round(statistics.mean(angles), 4),
                "angle_std": round(statistics.stdev(angles), 4)
                if len(angles) > 1
                else 0,
                "angle_peak": round(max(abs(a) for a in angles), 4),
                "output_mean": round(statistics.mean(outputs), 2),
                "output_std": round(statistics.stdev(outputs), 2)
                if len(outputs) > 1
                else 0,
            }

        if "peak_detect" in analysis_types:
            result_data["peak_detect"] = self._detect_peaks(angles, sample_rate_hz)

        if "fft" in analysis_types:
            result_data["fft"] = self._compute_fft(angles, sample_rate_hz, freq_range)

        if "phase_lag" in analysis_types:
            result_data["phase_lag"] = self._compute_phase_lag(
                angles, outputs, sample_rate_hz
            )

        if "raw" in analysis_types:
            # Return first 100 rows as raw data
            result_data["raw_samples"] = rows[:100]

        # Generate diagnosis if oscillation detected
        if result_data.get("peak_detect", {}).get("oscillation_detected"):
            freq = result_data.get("peak_detect", {}).get("oscillation_freq_hz", 0)
            result_data["diagnosis"] = (
                f"{freq:.1f}Hz oscillation detected. Consider reducing Kd or checking loop delay."
            )

        return ToolResult(ok=True, tool="read_burst_capture", data=result_data)

    def _detect_peaks(
        self, angles: List[float], sample_rate_hz: float
    ) -> Dict[str, Any]:
        """Detect oscillation peaks in angle data."""
        if len(angles) < 10 or sample_rate_hz <= 0:
            return {"oscillation_detected": False}

        mean_ang = statistics.mean(angles)
        deviations = [a - mean_ang for a in angles]

        # Find peaks (local maxima)
        peaks = []
        for i in range(1, len(deviations) - 1):
            if deviations[i] > deviations[i - 1] and deviations[i] > deviations[i + 1]:
                if abs(deviations[i]) > 0.5:  # Minimum peak height
                    peaks.append(i)

        if len(peaks) < 2:
            return {"oscillation_detected": False}

        # Calculate frequency from peak spacing
        peak_intervals = [peaks[i + 1] - peaks[i] for i in range(len(peaks) - 1)]
        avg_interval = statistics.mean(peak_intervals)
        freq_hz = sample_rate_hz / avg_interval if avg_interval > 0 else 0

        # Calculate peak-to-peak amplitude
        peak_values = [abs(deviations[p]) for p in peaks]
        peak_to_peak = 2 * statistics.mean(peak_values)

        # Estimate damping ratio (simplified)
        if len(peak_values) >= 4:
            early_peaks = statistics.mean(peak_values[: len(peak_values) // 2])
            late_peaks = statistics.mean(peak_values[len(peak_values) // 2 :])
            damping_ratio = 1 - (late_peaks / early_peaks) if early_peaks > 0 else 0
        else:
            damping_ratio = None

        return {
            "oscillation_detected": True,
            "oscillation_freq_hz": round(freq_hz, 2),
            "peak_to_peak_deg": round(peak_to_peak, 2),
            "peak_count": len(peaks),
            "damping_ratio": round(damping_ratio, 3)
            if damping_ratio is not None
            else None,
        }

    def _compute_fft(
        self, angles: List[float], sample_rate_hz: float, freq_range: List[float]
    ) -> Dict[str, Any]:
        """Compute FFT frequency analysis (simplified without numpy)."""
        if len(angles) < 16 or sample_rate_hz <= 0:
            return {"error": "Insufficient data for FFT"}

        n = len(angles)
        mean_ang = statistics.mean(angles)
        centered = [a - mean_ang for a in angles]

        # Simple DFT for dominant frequency detection
        # Only compute for frequencies in range
        min_freq, max_freq = freq_range if len(freq_range) == 2 else (0.5, 25)

        freq_step = sample_rate_hz / n
        start_k = max(1, int(min_freq / freq_step))
        end_k = min(n // 2, int(max_freq / freq_step) + 1)

        max_amplitude = 0
        dominant_freq = 0
        secondary_freq = 0
        secondary_amplitude = 0

        for k in range(start_k, end_k):
            # DFT at frequency k
            real_sum = 0
            imag_sum = 0
            for i, x in enumerate(centered):
                angle = 2 * math.pi * k * i / n
                real_sum += x * math.cos(angle)
                imag_sum -= x * math.sin(angle)

            amplitude = math.sqrt(real_sum**2 + imag_sum**2) / n
            freq = k * freq_step

            if amplitude > max_amplitude:
                secondary_freq = dominant_freq
                secondary_amplitude = max_amplitude
                max_amplitude = amplitude
                dominant_freq = freq
            elif amplitude > secondary_amplitude:
                secondary_freq = freq
                secondary_amplitude = amplitude

        return {
            "dominant_freq_hz": round(dominant_freq, 2),
            "dominant_amplitude": round(max_amplitude * 2, 4),  # Scale for peak-to-peak
            "secondary_freq_hz": round(secondary_freq, 2)
            if secondary_freq > 0
            else None,
            "noise_floor_db": -45,  # Placeholder
        }

    def _compute_phase_lag(
        self, angles: List[float], outputs: List[float], sample_rate_hz: float
    ) -> Dict[str, Any]:
        """Compute phase lag between angle and output via cross-correlation."""
        if len(angles) < 20 or sample_rate_hz <= 0:
            return {"error": "Insufficient data for phase lag"}

        # Normalize signals
        ang_mean = statistics.mean(angles)
        out_mean = statistics.mean(outputs)
        ang_centered = [a - ang_mean for a in angles]
        out_centered = [o - out_mean for o in outputs]

        # Simple cross-correlation to find lag
        max_lag = min(len(angles) // 4, 50)
        best_corr = -float("inf")
        best_lag = 0

        for lag in range(-max_lag, max_lag + 1):
            corr = 0
            count = 0
            for i in range(len(angles)):
                j = i + lag
                if 0 <= j < len(outputs):
                    corr += ang_centered[i] * out_centered[j]
                    count += 1
            if count > 0:
                corr /= count
                if corr > best_corr:
                    best_corr = corr
                    best_lag = lag

        lag_ms = int(best_lag * 1000 / sample_rate_hz) if sample_rate_hz > 0 else 0

        # Convert to degrees (assuming dominant frequency)
        # This is approximate without actual FFT
        lag_deg = None

        return {
            "angle_to_output_ms": lag_ms,
            "angle_to_output_deg": lag_deg,
        }

    # ========================================================================
    # T2: Experimentation Tool Implementations
    # ========================================================================

    def _tool_diff_config(self, args: Dict[str, Any]) -> ToolResult:
        """
        Compare current runtime configuration to a checkpoint or baseline.
        Read-only - does not modify any state.
        """
        compare_to = args.get("compare_to", "checkpoint")
        checkpoint_id = args.get("checkpoint_id")
        snapshot_id = args.get("snapshot_id")
        include_sketch = args.get("include_sketch", False)

        # Get current config from gateway
        if not self.gateway:
            return ToolResult(
                ok=False,
                tool="diff_config",
                error=T2Errors.E_NO_DB,
                data={"message": "Gateway not configured, cannot read current config"},
            )

        try:
            current_status = self.gateway.get_status()
            if not current_status:
                return ToolResult(
                    ok=False,
                    tool="diff_config",
                    error=T1Errors.E_SERIAL_DISCONNECTED,
                    data={"message": "Could not read current config from robot"},
                )
        except Exception as e:
            return ToolResult(
                ok=False,
                tool="diff_config",
                error=T1Errors.E_SERIAL_DISCONNECTED,
                data={"message": f"Failed to read config: {e}"},
            )

        current_config = {
            "kp": float(current_status.get("kp", 0)),
            "ki": float(current_status.get("ki", 0)),
            "kd": float(current_status.get("kd", 0)),
            "setpoint": float(
                current_status.get("set", current_status.get("setpoint", 0))
            ),
        }

        # Get reference config based on compare_to
        reference_config: Dict[str, float] = {}
        reference_meta: Dict[str, Any] = {}

        if compare_to == "factory":
            reference_config = FACTORY_DEFAULTS.copy()
            reference_meta = {"source": "factory", "description": "Factory defaults"}

        elif compare_to == "checkpoint":
            if not self.db:
                return ToolResult(
                    ok=False,
                    tool="diff_config",
                    error=T2Errors.E_NO_DB,
                    data={"message": "Database not configured for checkpoint lookup"},
                )

            try:
                if checkpoint_id:
                    checkpoints = self.db.query_checkpoints(
                        robot_id=self.active_robot_id, limit=100
                    )
                    checkpoint = next(
                        (c for c in checkpoints if c.id == checkpoint_id), None
                    )
                else:
                    # Get best-rated checkpoint
                    for rating in RATING_HIERARCHY:
                        checkpoints = self.db.query_checkpoints(
                            robot_id=self.active_robot_id,
                            min_rating=rating,
                            limit=1,
                        )
                        if checkpoints:
                            checkpoint = checkpoints[0]
                            break
                    else:
                        checkpoint = None

                if not checkpoint:
                    return ToolResult(
                        ok=False,
                        tool="diff_config",
                        error=T2Errors.E_NO_CHECKPOINT,
                        data={"message": "No checkpoint found matching criteria"},
                    )

                reference_config = {
                    "kp": checkpoint.kp,
                    "ki": checkpoint.ki,
                    "kd": checkpoint.kd,
                    "setpoint": getattr(checkpoint, "setpoint", 0.0),
                }
                reference_meta = {
                    "source": "checkpoint",
                    "checkpoint_id": checkpoint.id,
                    "checkpoint_rating": checkpoint.rating,
                    "checkpoint_ts": checkpoint.ts,
                }
            except Exception as e:
                return ToolResult(
                    ok=False,
                    tool="diff_config",
                    error=T2Errors.E_NO_CHECKPOINT,
                    data={"message": f"Checkpoint lookup failed: {e}"},
                )

        elif compare_to == "session_start":
            # Session start would require storing initial config at startup
            # For now, fall back to factory defaults
            reference_config = FACTORY_DEFAULTS.copy()
            reference_meta = {
                "source": "session_start",
                "note": "Using factory defaults as session_start fallback",
            }

        else:
            return ToolResult(
                ok=False,
                tool="diff_config",
                error=T2Errors.E_INVALID_CHANGE,
                data={"message": f"Unknown compare_to value: {compare_to}"},
            )

        # Compute diffs
        diffs: List[Dict[str, Any]] = []
        identical: List[str] = []

        for param in ["kp", "ki", "kd", "setpoint"]:
            current_val = current_config.get(param, 0)
            ref_val = reference_config.get(param, 0)

            if abs(current_val - ref_val) < 0.0001:
                identical.append(param)
            else:
                delta_abs = current_val - ref_val
                delta_pct = (
                    f"{delta_abs / ref_val * 100:+.0f}%"
                    if ref_val != 0
                    else f"+{delta_abs}"
                )
                diffs.append(
                    {
                        "param": param,
                        "current": current_val,
                        "reference": ref_val,
                        "delta": delta_pct,
                    }
                )

        # Generate summary
        if not diffs:
            summary = f"Configuration matches {compare_to}. No differences."
        else:
            changes = ", ".join(f"{d['param']}: {d['delta']}" for d in diffs)
            summary = f"{len(diffs)} parameter(s) differ from {compare_to}: {changes}"

        return ToolResult(
            ok=True,
            tool="diff_config",
            data={
                "compared_to": compare_to,
                **reference_meta,
                "diffs": diffs,
                "identical": identical,
                "summary": summary,
            },
        )

    def _tool_safe_rollback(self, args: Dict[str, Any]) -> ToolResult:
        """
        Revert to a checkpoint with specified minimum rating.
        Writes PID/config commands to the robot.
        """
        min_rating = args.get("min_rating", "good")
        scope = args.get("scope", "pid")
        checkpoint_id = args.get("checkpoint_id")
        dry_run = args.get("dry_run", False)

        # Validate dependencies
        if not self.db:
            return ToolResult(
                ok=False,
                tool="safe_rollback",
                error=T2Errors.E_NO_DB,
                data={"message": "Database not configured"},
            )

        if not self.gateway:
            return ToolResult(
                ok=False,
                tool="safe_rollback",
                error=T1Errors.E_SERIAL_DISCONNECTED,
                data={"message": "Gateway not configured"},
            )

        # Check serial busy (use hasattr for gateways that may not implement is_busy)
        if hasattr(self.gateway, "is_busy") and self.gateway.is_busy():
            return ToolResult(
                ok=False,
                tool="safe_rollback",
                error=T2Errors.E_SERIAL_BUSY,
                data={"message": "Serial port busy, try again", "retry_after_ms": 500},
            )

        # Find matching checkpoint
        try:
            if checkpoint_id:
                checkpoints = self.db.query_checkpoints(
                    robot_id=self.active_robot_id, limit=100
                )
                checkpoint = next(
                    (c for c in checkpoints if c.id == checkpoint_id), None
                )
            else:
                # Find best checkpoint meeting min_rating
                rating_idx = (
                    RATING_HIERARCHY.index(min_rating)
                    if min_rating in RATING_HIERARCHY
                    else 1
                )
                for rating in RATING_HIERARCHY[: rating_idx + 1]:
                    checkpoints = self.db.query_checkpoints(
                        robot_id=self.active_robot_id,
                        min_rating=rating,
                        limit=1,
                    )
                    if checkpoints:
                        checkpoint = checkpoints[0]
                        break
                else:
                    checkpoint = None

            if not checkpoint:
                return ToolResult(
                    ok=False,
                    tool="safe_rollback",
                    error=T2Errors.E_NO_CHECKPOINT,
                    data={
                        "message": f"No checkpoint found with rating >= {min_rating}"
                    },
                )

        except Exception as e:
            return ToolResult(
                ok=False,
                tool="safe_rollback",
                error=T2Errors.E_NO_CHECKPOINT,
                data={"message": f"Checkpoint lookup failed: {e}"},
            )

        # Get current config for comparison
        try:
            current_status = self.gateway.get_status()
            current_kp = float(current_status.get("kp", 0))
            current_ki = float(current_status.get("ki", 0))
            current_kd = float(current_status.get("kd", 0))
        except Exception:
            current_kp = current_ki = current_kd = 0

        # Build commands based on scope
        commands: List[str] = []
        changes: List[Dict[str, Any]] = []

        if scope in ("pid", "all_runtime"):
            target_kp = checkpoint.kp
            target_ki = checkpoint.ki
            target_kd = checkpoint.kd

            if (
                abs(current_kp - target_kp) > 0.001
                or abs(current_ki - target_ki) > 0.001
                or abs(current_kd - target_kd) > 0.001
            ):
                commands.append(f"PID {target_kp} {target_ki} {target_kd}")
                if current_kp != target_kp:
                    changes.append({"param": "Kp", "from": current_kp, "to": target_kp})
                if current_ki != target_ki:
                    changes.append({"param": "Ki", "from": current_ki, "to": target_ki})
                if current_kd != target_kd:
                    changes.append({"param": "Kd", "from": current_kd, "to": target_kd})

        # Dry run - just show what would change
        if dry_run:
            return ToolResult(
                ok=True,
                tool="safe_rollback",
                data={
                    "checkpoint_id": checkpoint.id,
                    "checkpoint_rating": checkpoint.rating,
                    "checkpoint_ts": checkpoint.ts,
                    "scope": scope,
                    "changes_preview": changes,
                    "commands_preview": commands,
                    "dry_run": True,
                    "summary": f"Would rollback {scope} to checkpoint '{checkpoint.id}' (rated {checkpoint.rating})",
                },
            )

        # Execute commands
        commands_sent: List[str] = []
        for cmd in commands:
            try:
                result = self.gateway.command(cmd)
                commands_sent.append(cmd)
                if not result.get("ok", True):
                    return ToolResult(
                        ok=False,
                        tool="safe_rollback",
                        error=T2Errors.E_COMMAND_FAILED,
                        data={
                            "message": f"Command failed: {cmd}",
                            "result": result,
                            "commands_sent": commands_sent,
                        },
                    )
            except Exception as e:
                return ToolResult(
                    ok=False,
                    tool="safe_rollback",
                    error=T2Errors.E_COMMAND_FAILED,
                    data={
                        "message": f"Command error: {e}",
                        "commands_sent": commands_sent,
                    },
                )

        # Generate summary
        change_strs = [f"{c['param']}: {c['from']}→{c['to']}" for c in changes]
        summary = f"Rolled back {scope} to checkpoint '{checkpoint.id}' (rated {checkpoint.rating}). {', '.join(change_strs)}"

        return ToolResult(
            ok=True,
            tool="safe_rollback",
            data={
                "checkpoint_id": checkpoint.id,
                "checkpoint_rating": checkpoint.rating,
                "checkpoint_ts": checkpoint.ts,
                "scope": scope,
                "changes_applied": changes,
                "commands_sent": commands_sent,
                "dry_run": False,
                "summary": summary,
            },
        )

    def _tool_run_experiment(self, args: Dict[str, Any]) -> ToolResult:
        """
        Run controlled A/B experiment: capture baseline, apply change, observe, compare.
        Uses observe_telemetry internally for measurements.
        """
        change = args.get("change", {})
        baseline_s = min(
            float(args.get("baseline_s", 5)), ObservationLimits.MAX_BASELINE_DURATION_S
        )
        observe_s = min(
            float(args.get("observe_s", 10)), ObservationLimits.MAX_OBSERVE_DURATION_S
        )
        auto_revert = args.get("auto_revert", True)
        success_criteria = args.get(
            "success_criteria",
            {
                "max_angle_variance": 5.0,
                "max_output_saturation_pct": 80,
                "no_oscillation": True,
            },
        )
        description = args.get("description", "")

        # Validate change
        cmd = change.get("cmd")
        if not cmd:
            return ToolResult(
                ok=False,
                tool="run_experiment",
                error=T2Errors.E_INVALID_CHANGE,
                data={"message": "Change must include 'cmd' field"},
            )

        # Validate command is in allowlist
        cmd_prefix = cmd.split()[0].upper() if cmd else ""
        if cmd_prefix in BLOCKED_COMMANDS:
            return ToolResult(
                ok=False,
                tool="run_experiment",
                error=T2Errors.E_BLOCKED_COMMAND,
                data={"message": f"Command '{cmd_prefix}' is blocked for experiments"},
            )

        if cmd_prefix not in SAFE_COMMANDS:
            return ToolResult(
                ok=False,
                tool="run_experiment",
                error=T2Errors.E_BLOCKED_COMMAND,
                data={
                    "message": f"Command '{cmd_prefix}' not in safe command allowlist"
                },
            )

        # Validate dependencies
        if not self.gateway:
            return ToolResult(
                ok=False,
                tool="run_experiment",
                error=T1Errors.E_SERIAL_DISCONNECTED,
                data={"message": "Gateway not configured"},
            )

        # Check serial busy before starting experiment
        if hasattr(self.gateway, "is_busy") and self.gateway.is_busy():
            return ToolResult(
                ok=False,
                tool="run_experiment",
                error=T2Errors.E_SERIAL_BUSY,
                data={
                    "message": "Serial port busy, cannot start experiment",
                    "retry_after_ms": 500,
                },
            )

        # Generate experiment ID
        experiment_id = f"exp_{time.strftime('%Y%m%d_%H%M%S')}"

        # Store pre-change config for potential revert
        try:
            pre_status = self.gateway.get_status()
            pre_config = {
                "kp": float(pre_status.get("kp", 18)),
                "ki": float(pre_status.get("ki", 0.1)),
                "kd": float(pre_status.get("kd", 0.6)),
            }
        except Exception as e:
            return ToolResult(
                ok=False,
                tool="run_experiment",
                error=T1Errors.E_SERIAL_DISCONNECTED,
                data={"message": f"Could not read pre-config: {e}"},
            )

        # Capture baseline
        baseline_result = self._tool_observe_telemetry(
            {
                "duration_s": baseline_s,
                "metrics": [
                    "angle_variance",
                    "output_saturation_pct",
                    "oscillation_detected",
                ],
            }
        )

        if not baseline_result.ok:
            return ToolResult(
                ok=False,
                tool="run_experiment",
                error=T2Errors.E_BASELINE_FAILED,
                data={
                    "message": "Baseline capture failed",
                    "baseline_error": baseline_result.error,
                },
            )

        baseline_metrics = baseline_result.data.get("metrics", {})

        # Apply change
        try:
            cmd_result = self.gateway.command(cmd)
            if not cmd_result.get("ok", True):
                return ToolResult(
                    ok=False,
                    tool="run_experiment",
                    error=T2Errors.E_COMMAND_FAILED,
                    data={
                        "message": f"Failed to apply change: {cmd}",
                        "result": cmd_result,
                    },
                )
        except Exception as e:
            return ToolResult(
                ok=False,
                tool="run_experiment",
                error=T2Errors.E_COMMAND_FAILED,
                data={"message": f"Command error: {e}"},
            )

        # Wait for change to take effect
        time.sleep(ObservationLimits.EXPERIMENT_COOLDOWN_S)

        # Observe result
        result_obs = self._tool_observe_telemetry(
            {
                "duration_s": observe_s,
                "metrics": [
                    "angle_variance",
                    "output_saturation_pct",
                    "oscillation_detected",
                ],
            }
        )

        if not result_obs.ok:
            # Still continue - we have partial results
            result_metrics = {}
        else:
            result_metrics = result_obs.data.get("metrics", {})

        # Compare baseline vs result
        comparison: Dict[str, Any] = {}
        verdict = "improved"

        baseline_variance = baseline_metrics.get("angle_variance", 0)
        result_variance = result_metrics.get("angle_variance", 0)
        if baseline_variance > 0:
            variance_delta = result_variance - baseline_variance
            comparison["angle_variance_delta"] = round(variance_delta, 3)
            if variance_delta > baseline_variance * 0.2:  # >20% worse
                verdict = "degraded"

        baseline_sat = baseline_metrics.get("output_saturation_pct", 0)
        result_sat = result_metrics.get("output_saturation_pct", 0)
        sat_delta = result_sat - baseline_sat
        comparison["output_saturation_delta"] = round(sat_delta, 1)
        if sat_delta > 20:
            verdict = "degraded"

        comparison["verdict"] = verdict

        # Check success criteria
        criteria_met = True
        criteria_failures: List[str] = []

        max_var = success_criteria.get("max_angle_variance")
        if max_var is not None and result_variance > max_var:
            criteria_met = False
            criteria_failures.append(
                f"angle_variance {result_variance:.2f} > {max_var}"
            )

        max_sat = success_criteria.get("max_output_saturation_pct")
        if max_sat is not None and result_sat > max_sat:
            criteria_met = False
            criteria_failures.append(
                f"output_saturation {result_sat:.1f}% > {max_sat}%"
            )

        no_osc = success_criteria.get("no_oscillation")
        if no_osc and result_metrics.get("oscillation_detected"):
            criteria_met = False
            criteria_failures.append("oscillation detected")

        # Auto-revert if criteria not met
        auto_reverted = False
        revert_cmd = None
        if not criteria_met and auto_revert:
            revert_cmd = f"PID {pre_config['kp']} {pre_config['ki']} {pre_config['kd']}"
            try:
                self.gateway.command(revert_cmd)
                auto_reverted = True
            except Exception as e:
                logger.warning(f"Auto-revert failed: {e}")

        # Generate summary
        if criteria_met:
            summary = (
                f"Experiment succeeded. {comparison['verdict'].title()} performance."
            )
        else:
            fail_reasons = "; ".join(criteria_failures)
            if auto_reverted:
                summary = f"Experiment failed ({fail_reasons}). Auto-reverted to previous PID."
            else:
                summary = f"Experiment failed ({fail_reasons}). Auto-revert disabled."

        return ToolResult(
            ok=True,
            tool="run_experiment",
            data={
                "experiment_id": experiment_id,
                "description": description,
                "change_applied": {"cmd": cmd},
                "baseline": baseline_metrics,
                "result": result_metrics,
                "comparison": comparison,
                "success_criteria_met": criteria_met,
                "criteria_failures": criteria_failures if not criteria_met else [],
                "auto_reverted": auto_reverted,
                "revert_cmd": revert_cmd if auto_reverted else None,
                "summary": summary,
            },
        )

    # ========================================================================
    # T3: Intelligence Tool Implementations
    # ========================================================================

    def _tool_simulate_pid_response(self, args: Dict[str, Any]) -> ToolResult:
        """
        Simulate PID step response using linearized inverted pendulum model.
        Pure computation - no robot interaction.
        """
        proposed_pid = args.get("proposed_pid", {})
        step_size_deg = float(args.get("step_size_deg", 5))
        duration_s = float(args.get("duration_s", 3))
        compare_to_current = args.get("compare_to_current", True)

        # Validate proposed PID
        try:
            kp = float(proposed_pid.get("Kp", 0))
            ki = float(proposed_pid.get("Ki", 0))
            kd = float(proposed_pid.get("Kd", 0))
            if kp <= 0:
                return ToolResult(
                    ok=False,
                    tool="simulate_pid_response",
                    error=T3Errors.E_INVALID_PID,
                    data={"message": "Kp must be positive"},
                )
        except (TypeError, ValueError) as e:
            return ToolResult(
                ok=False,
                tool="simulate_pid_response",
                error=T3Errors.E_INVALID_PID,
                data={"message": f"Invalid PID values: {e}"},
            )

        # Simulate proposed PID
        proposed_result = self._simulate_step_response(
            kp, ki, kd, step_size_deg, duration_s
        )

        # Optionally simulate current PID for comparison
        current_result = None
        comparison = None

        if compare_to_current and self.gateway:
            try:
                status = self.gateway.get_status()
                current_kp = float(status.get("kp", FACTORY_DEFAULTS["kp"]))
                current_ki = float(status.get("ki", FACTORY_DEFAULTS["ki"]))
                current_kd = float(status.get("kd", FACTORY_DEFAULTS["kd"]))
                current_result = self._simulate_step_response(
                    current_kp, current_ki, current_kd, step_size_deg, duration_s
                )
                current_result["pid"] = {
                    "Kp": current_kp,
                    "Ki": current_ki,
                    "Kd": current_kd,
                }

                # Generate comparison
                comparison = self._compare_pid_simulations(
                    proposed_result, current_result
                )
            except Exception:
                pass  # Comparison optional

        proposed_result["pid"] = {"Kp": kp, "Ki": ki, "Kd": kd}

        data: Dict[str, Any] = {
            "proposed": proposed_result,
            "model_assumptions": f"Inverted pendulum, {ROBOT_DEFAULTS['mass_kg']*1000:.0f}g mass, {ROBOT_DEFAULTS['height_m']*100:.0f}cm height, {ROBOT_DEFAULTS['loop_period_ms']}ms loop",
        }

        if current_result:
            data["current"] = current_result
        if comparison:
            data["comparison"] = comparison

        return ToolResult(ok=True, tool="simulate_pid_response", data=data)

    def _simulate_step_response(
        self, kp: float, ki: float, kd: float, step_deg: float, duration_s: float
    ) -> Dict[str, Any]:
        """
        Simulate step response using simplified inverted pendulum dynamics.
        Returns settling time, overshoot, stability assessment.
        """
        dt = ROBOT_DEFAULTS["loop_period_ms"] / 1000.0
        steps = int(duration_s / dt)
        g = ROBOT_DEFAULTS["gravity"]
        L = ROBOT_DEFAULTS["height_m"]

        # Natural frequency of inverted pendulum: omega_n = sqrt(g/L)
        omega_n = math.sqrt(g / L)

        # Linearized closed-loop analysis
        # For PID control of inverted pendulum:
        # Characteristic equation involves Kp, Ki, Kd
        # Simplified 2nd order approximation for stability analysis

        # Effective damping ratio and natural frequency with PID
        # zeta = Kd / (2 * sqrt(Kp))  (approximate)
        # omega_cl = sqrt(Kp) * omega_n (approximate closed-loop freq)

        if kp > 0:
            zeta = kd / (2 * math.sqrt(kp)) if kp > 0 else 0
            omega_cl = math.sqrt(kp) * 0.5  # Scaling factor for realistic response
        else:
            zeta = 0
            omega_cl = omega_n

        # Stability check
        stability = "stable"
        oscillation_risk = "low"

        if zeta < 0.1:
            stability = "marginally_stable"
            oscillation_risk = "high"
        elif zeta < 0.4:
            oscillation_risk = "medium"
        elif zeta > 2.0:
            stability = "overdamped"

        # Settling time (2% criterion): ts ≈ 4 / (zeta * omega_cl)
        if zeta > 0 and omega_cl > 0:
            settling_time_s = 4 / (zeta * omega_cl)
            settling_time_ms = min(settling_time_s * 1000, duration_s * 1000)
        else:
            settling_time_ms = duration_s * 1000

        # Overshoot for underdamped system
        if 0 < zeta < 1:
            overshoot_pct = 100 * math.exp(-math.pi * zeta / math.sqrt(1 - zeta**2))
        else:
            overshoot_pct = 0

        # Steady-state error with integral term
        if ki > 0:
            steady_state_error_deg = 0.0  # Integral eliminates steady-state error
        else:
            # Without integral, error depends on Kp vs disturbance
            steady_state_error_deg = step_deg / (1 + kp * 0.1)

        return {
            "settling_time_ms": round(settling_time_ms, 0),
            "overshoot_pct": round(overshoot_pct, 1),
            "steady_state_error_deg": round(steady_state_error_deg, 2),
            "stability": stability,
            "oscillation_risk": oscillation_risk,
            "damping_ratio": round(zeta, 2),
        }

    def _compare_pid_simulations(
        self, proposed: Dict[str, Any], current: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Compare two PID simulation results."""
        prop_settling = proposed.get("settling_time_ms", 0)
        curr_settling = current.get("settling_time_ms", 0)

        if curr_settling > 0:
            settling_delta = (
                f"{(prop_settling - curr_settling) / curr_settling * 100:+.0f}%"
            )
        else:
            settling_delta = "N/A"

        prop_overshoot = proposed.get("overshoot_pct", 0)
        curr_overshoot = current.get("overshoot_pct", 0)
        overshoot_delta = f"{prop_overshoot - curr_overshoot:+.1f}%"

        # Generate recommendation
        recommendations: List[str] = []

        if prop_settling < curr_settling * 0.8:
            recommendations.append("Faster settling")
        elif prop_settling > curr_settling * 1.2:
            recommendations.append("Slower settling")

        if prop_overshoot > curr_overshoot + 10:
            recommendations.append("More overshoot—consider increasing Kd")
        elif prop_overshoot < curr_overshoot - 5:
            recommendations.append("Less overshoot")

        if (
            proposed.get("oscillation_risk") == "high"
            and current.get("oscillation_risk") != "high"
        ):
            recommendations.append("Higher oscillation risk—increase Kd")

        recommendation = (
            "; ".join(recommendations)
            if recommendations
            else "Similar performance to current PID"
        )

        return {
            "settling_time_delta": settling_delta,
            "overshoot_delta": overshoot_delta,
            "recommendation": recommendation,
        }

    def _tool_suggest_next_step(self, args: Dict[str, Any]) -> ToolResult:
        """
        Analyze current tuning state and suggest next actions.
        Uses rule-based heuristics + optional RAG search.
        """
        context = args.get("context", "")
        include_rationale = args.get("include_rationale", True)
        max_suggestions = min(int(args.get("max_suggestions", 3)), 5)

        # Gather current state
        current_state: Dict[str, Any] = {}
        current_pid: Dict[str, float] = {}

        if self.gateway:
            try:
                status = self.gateway.get_status()
                current_pid = {
                    "kp": float(status.get("kp", 18)),
                    "ki": float(status.get("ki", 0.1)),
                    "kd": float(status.get("kd", 0.6)),
                }

                # Get recent telemetry metrics
                obs_result = self._tool_observe_telemetry(
                    {"duration_s": 2, "metrics": ["all"]}
                )
                if obs_result.ok:
                    metrics = obs_result.data.get("metrics", {})
                    current_state = {
                        "angle_variance": metrics.get("angle_variance", 0),
                        "oscillation_detected": metrics.get(
                            "oscillation_detected", False
                        ),
                        "oscillation_freq_hz": metrics.get("oscillation_freq_hz"),
                        "output_saturation_pct": metrics.get(
                            "output_saturation_pct", 0
                        ),
                        "mode": obs_result.data.get("latest_sample", {}).get(
                            "mode", "UNKNOWN"
                        ),
                    }
            except Exception as e:
                logger.warning(f"Could not gather telemetry for suggestions: {e}")

        if not current_state:
            return ToolResult(
                ok=False,
                tool="suggest_next_step",
                error=T3Errors.E_NO_TELEMETRY,
                data={"message": "Could not gather current telemetry state"},
            )

        # Generate suggestions using rule-based expert system
        suggestions = self._generate_tuning_suggestions(
            current_state, current_pid, context, include_rationale
        )

        # Limit to max_suggestions
        suggestions = suggestions[:max_suggestions]

        # Data sources used
        data_sources = ["current_telemetry"]
        if self.db:
            data_sources.append("checkpoint_history")
        if self.rag:
            data_sources.append("knowledge_base")

        return ToolResult(
            ok=True,
            tool="suggest_next_step",
            data={
                "current_state": current_state,
                "current_pid": current_pid,
                "suggestions": suggestions,
                "data_sources": data_sources,
            },
        )

    def _generate_tuning_suggestions(
        self,
        state: Dict[str, Any],
        pid: Dict[str, float],
        context: str,
        include_rationale: bool,
    ) -> List[Dict[str, Any]]:
        """
        Generate ranked tuning suggestions based on current state.
        Rule-based expert system for PID tuning.
        """
        suggestions: List[Dict[str, Any]] = []
        kp = pid.get("kp", 18)
        ki = pid.get("ki", 0.1)
        kd = pid.get("kd", 0.6)

        variance = state.get("angle_variance", 0)
        osc_detected = state.get("oscillation_detected", False)
        osc_freq = state.get("oscillation_freq_hz")
        saturation = state.get("output_saturation_pct", 0)

        # Rule 1: High-frequency oscillation → reduce Kd
        if (
            osc_detected
            and osc_freq
            and osc_freq > TUNING_THRESHOLDS["oscillation_freq_high_hz"]
        ):
            new_kd = round(kd * 0.8, 2)
            suggestions.append(
                {
                    "rank": len(suggestions) + 1,
                    "action": f"Reduce Kd by 20% (high-freq oscillation at {osc_freq:.1f}Hz)",
                    "command": f"PID {kp} {ki} {new_kd}",
                    "confidence": 0.85,
                    "rationale": f"Oscillation at {osc_freq:.1f}Hz is characteristic of derivative kick. Reducing Kd dampens high-frequency response."
                    if include_rationale
                    else None,
                    "expected_outcome": "Oscillation should decrease within 2-3 seconds",
                }
            )

        # Rule 2: Low-frequency oscillation → reduce Ki or increase Kd
        if (
            osc_detected
            and osc_freq
            and osc_freq < TUNING_THRESHOLDS["oscillation_freq_low_hz"]
        ):
            new_ki = round(ki * 0.5, 3)
            suggestions.append(
                {
                    "rank": len(suggestions) + 1,
                    "action": f"Reduce Ki by 50% (low-freq oscillation at {osc_freq:.1f}Hz)",
                    "command": f"PID {kp} {new_ki} {kd}",
                    "confidence": 0.75,
                    "rationale": f"Low-frequency oscillation at {osc_freq:.1f}Hz suggests integral windup. Reducing Ki will improve stability."
                    if include_rationale
                    else None,
                    "expected_outcome": "Slower but more stable recovery",
                }
            )

        # Rule 3: High output saturation → reduce Kp
        if saturation > TUNING_THRESHOLDS["saturation_critical_pct"]:
            new_kp = round(kp * 0.85, 1)
            suggestions.append(
                {
                    "rank": len(suggestions) + 1,
                    "action": f"Reduce Kp by 15% (output saturation at {saturation:.0f}%)",
                    "command": f"PID {new_kp} {ki} {kd}",
                    "confidence": 0.80,
                    "rationale": f"Output saturation at {saturation:.0f}% indicates gain is too high. Motors are limiting response."
                    if include_rationale
                    else None,
                    "expected_outcome": "Reduced saturation, more control headroom",
                }
            )

        # Rule 4: High variance without oscillation → increase Kp
        if (
            variance > TUNING_THRESHOLDS["angle_variance_acceptable"]
            and not osc_detected
        ):
            new_kp = round(kp * 1.15, 1)
            suggestions.append(
                {
                    "rank": len(suggestions) + 1,
                    "action": f"Increase Kp by 15% (high variance {variance:.1f}°)",
                    "command": f"PID {new_kp} {ki} {kd}",
                    "confidence": 0.70,
                    "rationale": f"Angle variance of {variance:.1f}° without oscillation suggests insufficient proportional gain."
                    if include_rationale
                    else None,
                    "expected_outcome": "Tighter angle control, faster correction",
                }
            )

        # Rule 5: Oscillation detected but no freq data → increase Kd
        if osc_detected and not osc_freq:
            new_kd = round(kd * 1.2, 2)
            suggestions.append(
                {
                    "rank": len(suggestions) + 1,
                    "action": "Increase Kd by 20% (dampen oscillation)",
                    "command": f"PID {kp} {ki} {new_kd}",
                    "confidence": 0.60,
                    "rationale": "Oscillation detected. Increasing derivative gain adds damping."
                    if include_rationale
                    else None,
                    "expected_outcome": "Reduced oscillation amplitude",
                }
            )

        # Rule 6: Good state → suggest checkpoint
        if (
            variance < TUNING_THRESHOLDS["angle_variance_good"]
            and not osc_detected
            and saturation < TUNING_THRESHOLDS["saturation_warning_pct"]
        ):
            suggestions.append(
                {
                    "rank": len(suggestions) + 1,
                    "action": "Save checkpoint (current tuning looks good)",
                    "command": None,
                    "confidence": 0.90,
                    "rationale": f"Variance {variance:.1f}°, no oscillation, {saturation:.0f}% saturation—this is a good tuning point."
                    if include_rationale
                    else None,
                    "expected_outcome": "Preserve this configuration for future reference",
                }
            )

        # Rule 7: Fallback—try small Kp adjustment
        if len(suggestions) < 2:
            new_kp = round(kp * 1.1, 1)
            suggestions.append(
                {
                    "rank": len(suggestions) + 1,
                    "action": "Try 10% Kp increase (exploratory)",
                    "command": f"PID {new_kp} {ki} {kd}",
                    "confidence": 0.50,
                    "rationale": "No clear issue detected. Small Kp increase may improve responsiveness."
                    if include_rationale
                    else None,
                    "expected_outcome": "Slightly faster response",
                }
            )

        # Re-rank by confidence
        suggestions.sort(key=lambda x: x.get("confidence", 0), reverse=True)
        for i, s in enumerate(suggestions):
            s["rank"] = i + 1

        return suggestions

    def _tool_annotate_session(self, args: Dict[str, Any]) -> ToolResult:
        """
        Add annotation to current session timeline.
        Stores in session_annotations table for learning and recall.
        """
        note = str(args.get("note", "")).strip()
        if not note:
            return ToolResult(
                ok=False,
                tool="annotate_session",
                error="note is required",
                data={"message": "Annotation note cannot be empty"},
            )

        tags = args.get("tags", [])
        if not isinstance(tags, list):
            tags = [str(tags)] if tags else []
        tags = [str(t).strip() for t in tags if str(t).strip()]

        severity = str(args.get("severity", "info")).strip().lower()
        if severity not in ("info", "success", "warning", "failure"):
            severity = "info"

        related_config = args.get("related_config")
        if related_config and not isinstance(related_config, dict):
            related_config = None

        ts = args.get("ts")
        if ts is not None:
            try:
                ts = float(ts)
            except (TypeError, ValueError):
                ts = None

        # Generate session ID based on current date
        session_id = f"session_{time.strftime('%Y%m%d')}"

        # If no related_config provided, capture current state
        if related_config is None and self.gateway:
            try:
                status = self.gateway.get_status()
                related_config = {
                    "kp": status.get("kp"),
                    "ki": status.get("ki"),
                    "kd": status.get("kd"),
                    "setpoint": status.get("setpoint"),
                    "mode": status.get("mode"),
                }
            except Exception:
                related_config = {}

        # Save to database
        if not self.db:
            return ToolResult(
                ok=False,
                tool="annotate_session",
                error="database_not_configured",
                data={"message": "Database required for annotations"},
            )

        try:
            actual_ts = ts if ts is not None else time.time()
            annotation_id = self.db.save_annotation(
                note=note,
                tags=tags,
                severity=severity,
                related_config=related_config,
                ts=actual_ts,
                session_id=session_id,
                robot_id=self.active_robot_id or "",
            )

            # Generate annotation ID string
            ann_id_str = f"ann_{time.strftime('%Y%m%d_%H%M%S', time.localtime(actual_ts))}"

            return ToolResult(
                ok=True,
                tool="annotate_session",
                data={
                    "annotation_id": ann_id_str,
                    "db_id": annotation_id,
                    "ts": actual_ts,
                    "note": note,
                    "tags": tags,
                    "severity": severity,
                    "session_id": session_id,
                    "related_config": related_config or {},
                },
            )
        except Exception as e:
            logger.error(f"Failed to save annotation: {e}")
            return ToolResult(
                ok=False,
                tool="annotate_session",
                error=f"save_failed: {e}",
                data={"message": str(e)},
            )


def get_tool_definitions() -> List[Dict[str, Any]]:
    """Get OpenAI-compatible tool definitions."""
    return TOOL_DEFINITIONS

"""Contract readiness and compat policy utilities extracted from server.py."""

from __future__ import annotations

import json
import logging
import pathlib
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from app.bridge.nano_serial_gateway import NanoSerialGateway
    from app.bridge.bridge_control_state import BridgeControlState
    from app.bridge.prearm_safety_gate import PreArmSafetyGate

logger = logging.getLogger(__name__)


def _normalize_status_for_hud(status_raw: Dict[str, Any]) -> Dict[str, Any]:
    """Stub for Phase 1 - returns passthrough. Full impl in server.py."""
    return {"status": status_raw, "adapter": {}}


__all__ = [
    "V1_REQUIRED_FIELDS",
    "V1_GYRO_ALIASES",
    "V2_READINESS_FIELDS",
    "V2_FACTORY_FIELDS",
    "V2_OPTIONAL_FIELDS",
    "detect_contract_readiness",
    "_compute_action_gates",
    "_default_compat_policy",
    "_load_compat_policy",
    "_status_has_required_fields",
    "_resolve_compat_profile",
    "_resolve_action_gates",
    "_require_action_allowed",
]


V1_REQUIRED_FIELDS = ("mode", "ang", "raw", "out", "kp", "ki", "kd", "set")
V1_GYRO_ALIASES = ("gyro", "gyr", "gx")

# v2 readiness fields (backward-compatible gate)
V2_READINESS_FIELDS = ("gyro_bias", "vel_meas", "outer_loop_enabled")

# v2 factory telemetry fields (strict factory standard)
V2_FACTORY_FIELDS = (
    "gyro_bias",
    "accel_level_offset",
    "upright_trim",
    "vel_meas",
    "vel_target",
    "outer_loop_enabled",
    "target_angle_from_velocity",
    "motor_l_trim",
    "motor_r_trim",
    "drift_diag_state",
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
        - phase1_ready: bool (core calibration + v1 telemetry)
        - phase2_ready: bool (advanced anti-drift/v2 telemetry)
        - phase1_missing_fields: list of missing Phase 1 fields
        - phase1_present_fields: list of present Phase 1 fields
        - phase2_missing_fields: list of missing Phase 2 fields
        - phase2_present_fields: list of present Phase 2 fields
        - v2_missing_fields: list of missing v2 readiness fields
        - v2_present_fields: list of v2 optional fields that are present
        - readiness_checks: list of {check, status, detail}
    """
    if not status:
        return {
            "contract_version_detected": "unknown",
            "v1_ok": False,
            "v2_ready": False,
            "phase1_ready": False,
            "phase2_ready": False,
            "calibration_flow": "phase1_phase2",
            "phase1_missing_fields": list(V1_REQUIRED_FIELDS) + ["gyro|gyr|gx"],
            "phase1_present_fields": [],
            "phase2_missing_fields": list(V2_READINESS_FIELDS),
            "phase2_present_fields": [],
            "v2_missing_fields": list(V2_READINESS_FIELDS),
            "v2_factory_ready": False,
            "v2_factory_missing_fields": list(V2_FACTORY_FIELDS),
            "v2_present_fields": [],
            "readiness_checks": [
                {
                    "check": "telemetry_available",
                    "status": "fail",
                    "detail": "No telemetry data",
                }
            ],
        }

    checks: list[Dict[str, Any]] = []

    # v1 check
    v1_missing = [f for f in V1_REQUIRED_FIELDS if f not in status]
    has_gyro = any(alias in status for alias in V1_GYRO_ALIASES)
    if not has_gyro:
        v1_missing.append("gyro|gyr|gx")
    v1_ok = len(v1_missing) == 0
    phase1_present = [f for f in V1_REQUIRED_FIELDS if f in status]
    phase1_present.extend([alias for alias in V1_GYRO_ALIASES if alias in status])

    checks.append(
        {
            "check": "v1_required_fields",
            "status": "pass" if v1_ok else "fail",
            "detail": f"Missing: {v1_missing}"
            if v1_missing
            else "All v1 fields present",
        }
    )

    # v2 readiness check
    v2_missing = [f for f in V2_READINESS_FIELDS if f not in status]
    if not has_gyro and "gyro|gyr|gx" not in v2_missing:
        # Keep backward-compatible diagnostics: missing gyro alias should surface
        # in readiness output even though it is part of v1 base contract.
        v2_missing.append("gyro|gyr|gx")
    v2_ready = len(v2_missing) == 0
    v2_factory_missing = [f for f in V2_FACTORY_FIELDS if f not in status]
    v2_factory_ready = len(v2_factory_missing) == 0

    checks.append(
        {
            "check": "v2_readiness_fields",
            "status": "pass" if v2_ready else "warn",
            "detail": f"Missing: {v2_missing}"
            if v2_missing
            else "All v2 readiness fields present",
        }
    )

    # v2 optional fields present
    v2_present = [f for f in V2_FACTORY_FIELDS if f in status]

    checks.append(
        {
            "check": "v2_optional_fields",
            "status": "pass" if v2_present else "warn",
            "detail": f"Present: {v2_present}"
            if v2_present
            else "No v2 optional fields present",
        }
    )

    checks.append(
        {
            "check": "v2_factory_fields",
            "status": "pass" if v2_factory_ready else "warn",
            "detail": f"Missing: {v2_factory_missing}"
            if v2_factory_missing
            else "All factory v2 fields present",
        }
    )

    # Calibration readiness
    has_gyro_bias = "gyro_bias" in status
    has_accel_offset = "accel_level_offset" in status
    calibration_ready = has_gyro_bias and has_accel_offset

    checks.append(
        {
            "check": "calibration_data",
            "status": "pass" if calibration_ready else "warn",
            "detail": "Gyro bias and accel offset calibrated"
            if calibration_ready
            else "Calibration not complete",
        }
    )

    # Outer loop readiness
    has_velocity = "vel_meas" in status
    outer_enabled = status.get("outer_loop_enabled", False)

    checks.append(
        {
            "check": "outer_loop_ready",
            "status": "pass" if (has_velocity and outer_enabled) else "warn",
            "detail": "Velocity feedback and outer loop active"
            if (has_velocity and outer_enabled)
            else "Outer loop not active or no velocity data",
        }
    )

    checks.append(
        {
            "check": "phase1_core_ready",
            "status": "pass" if v1_ok else "fail",
            "detail": "Phase 1 core readiness satisfied"
            if v1_ok
            else "Phase 1 incomplete: core telemetry/calibration missing",
        }
    )
    checks.append(
        {
            "check": "phase2_advanced_ready",
            "status": "pass" if v2_ready else "warn",
            "detail": "Phase 2 advanced readiness satisfied"
            if v2_ready
            else "Phase 2 incomplete: advanced anti-drift fields missing",
        }
    )

    return {
        "contract_version_detected": "v2" if v2_ready else "v1",
        "v1_ok": v1_ok,
        "v2_ready": v2_ready,
        "phase1_ready": v1_ok,
        "phase2_ready": v2_ready,
        "calibration_flow": "phase1_phase2",
        "phase1_missing_fields": v1_missing,
        "phase1_present_fields": phase1_present,
        "phase2_missing_fields": v2_missing,
        "phase2_present_fields": v2_present,
        "v2_missing_fields": v2_missing,
        "v2_factory_ready": v2_factory_ready,
        "v2_factory_missing_fields": v2_factory_missing,
        "v2_present_fields": v2_present,
        "readiness_checks": checks,
    }


def _compute_action_gates(
    *,
    connected: bool,
    status: Dict[str, Any],
    control_snapshot: Dict[str, Any],
    session_fresh: bool,
    prearm_safety: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    status_map = status if isinstance(status, dict) else {}
    control_map = control_snapshot if isinstance(control_snapshot, dict) else {}
    mode = str(status_map.get("mode", "")).upper()
    estop = bool(control_map.get("estop_latched", False))
    arm_prepared = bool(control_map.get("arm_prepared", False))
    readiness = detect_contract_readiness(status_map)
    phase1_ready = bool(readiness.get("phase1_ready", readiness.get("v1_ok", False)))
    phase2_ready = bool(readiness.get("phase2_ready", readiness.get("v2_ready", False)))
    prearm = prearm_safety if isinstance(prearm_safety, dict) else {}
    prearm_required = bool(prearm.get("required", False))
    prearm_passed = bool(prearm.get("passed", False))

    def gate(reasons: list[str]) -> Dict[str, Any]:
        return {"ok": len(reasons) == 0, "reasons": reasons}

    gates: Dict[str, Dict[str, Any]] = {}

    arm_prepare_reasons: list[str] = []
    if not connected:
        arm_prepare_reasons.append("serial_disconnected")
    if not session_fresh:
        arm_prepare_reasons.append("session_stale")
    if estop:
        arm_prepare_reasons.append("estop_latched")
    if not phase1_ready:
        arm_prepare_reasons.append("telemetry_contract_incomplete")
    if mode in {"ARMED", "BALANCING"}:
        arm_prepare_reasons.append("already_armed")
    if prearm_required and not prearm_passed:
        arm_prepare_reasons.append("prearm_safety_check_required")
    gates["arm_prepare"] = gate(arm_prepare_reasons)

    arm_confirm_reasons: list[str] = []
    if not connected:
        arm_confirm_reasons.append("serial_disconnected")
    if not session_fresh:
        arm_confirm_reasons.append("session_stale")
    if estop:
        arm_confirm_reasons.append("estop_latched")
    if not arm_prepared:
        arm_confirm_reasons.append("arm_not_prepared")
    if mode in {"ARMED", "BALANCING"}:
        arm_confirm_reasons.append("already_armed")
    if prearm_required and not prearm_passed:
        arm_confirm_reasons.append("prearm_safety_check_required")
    gates["arm_confirm"] = gate(arm_confirm_reasons)

    arm_reasons: list[str] = []
    if not connected:
        arm_reasons.append("serial_disconnected")
    if not session_fresh:
        arm_reasons.append("session_stale")
    if estop:
        arm_reasons.append("estop_latched")
    if mode in {"ARMED", "BALANCING"}:
        arm_reasons.append("already_armed")
    if prearm_required and not prearm_passed:
        arm_reasons.append("prearm_safety_check_required")
    gates["arm"] = gate(arm_reasons)

    disarm_reasons: list[str] = []
    if not connected:
        disarm_reasons.append("serial_disconnected")
    gates["disarm"] = gate(disarm_reasons)

    cal_zero_reasons: list[str] = []
    if not connected:
        cal_zero_reasons.append("serial_disconnected")
    if estop:
        cal_zero_reasons.append("estop_latched")
    if mode == "BALANCING":
        cal_zero_reasons.append("disarm_required")
    gates["cal_zero"] = gate(cal_zero_reasons)

    burst_arm_reasons: list[str] = []
    if not connected:
        burst_arm_reasons.append("serial_disconnected")
    if estop:
        burst_arm_reasons.append("estop_latched")
    gates["burst_arm"] = gate(burst_arm_reasons)

    tune_reasons: list[str] = []
    if not connected:
        tune_reasons.append("serial_disconnected")
    if estop:
        tune_reasons.append("estop_latched")
    if not phase1_ready:
        tune_reasons.append("telemetry_contract_incomplete")
    gates["pid"] = gate(list(tune_reasons))
    motion_reasons = list(tune_reasons)
    if not phase2_ready:
        motion_reasons.append("phase2_required_for_motion")
    gates["motion"] = gate(motion_reasons)
    gates["setpoint"] = gate(list(tune_reasons))
    gates["limits"] = gate(list(tune_reasons))
    gates["prearm_safety"] = {
        "ok": (not prearm_required) or prearm_passed,
        "reasons": []
        if ((not prearm_required) or prearm_passed)
        else ["prearm_safety_check_required"],
    }

    return gates


_compat_policy_cache: Dict[str, Any] = {"content": None, "mtime": 0.0}


def _default_compat_policy() -> Dict[str, Any]:
    return {
        "version": "1.0",
        "default_profile": "baseline_v1",
        "required_fields": [
            "mode",
            "ang",
            "raw",
            "gyro|gyr|gx",
            "out",
            "kp",
            "ki",
            "kd",
            "set",
        ],
        "profiles": {
            "lean_v1": {
                "required_commands": [
                    "GET",
                    "HELP",
                    "ARM",
                    "DISARM",
                    "ESTOP",
                    "FAULTCLR",
                    "PID",
                    "SETPOINT",
                    "LIMITS",
                    "CAL ZERO",
                    "SAVECFG",
                ],
                "optional_commands": ["IDENT", "LOGT", "LOGCSV", "BURSTCSV", "CSVHDR"],
                "warn_only_missing_commands": [],
            },
            "baseline_v1": {
                "required_commands": [
                    "GET",
                    "ARM",
                    "DISARM",
                    "PID",
                    "SETPOINT",
                    "LIMITS",
                    "CAL ZERO",
                    "SAVECFG",
                    "FAULTCLR",
                ],
                "optional_commands": [
                    "IDENT",
                    "MOTION",
                    "FILTER",
                    "KAL",
                    "LOGT",
                    "LOGCSV",
                    "BURSTCSV",
                    "CSVHDR",
                    "IMU CAL",
                    "IMU LOAD",
                    "IMU SAVE",
                    "IMU INFO",
                ],
                "warn_only_missing_commands": ["MOTION"],
            },
            "profiled_runtime_v1": {
                "required_commands": [
                    "GET",
                    "ARM",
                    "DISARM",
                    "PID",
                    "SETPOINT",
                    "LIMITS",
                    "CAL ZERO",
                    "SAVECFG",
                    "FAULTCLR",
                ],
                "optional_commands": [
                    "IDENT",
                    "MOTION",
                    "FILTER",
                    "KAL",
                    "LOGT",
                    "LOGCSV",
                    "BURSTCSV",
                    "CSVHDR",
                    "LOADCFG",
                    "DEFAULTCFG",
                    "IMU CAL",
                    "IMU LOAD",
                    "IMU SAVE",
                    "IMU INFO",
                ],
                "warn_only_missing_commands": ["MOTION"],
            },
            "control_lab_v1": {
                "required_commands": [
                    "GET",
                    "ARM",
                    "DISARM",
                    "PID",
                    "SETPOINT",
                    "LIMITS",
                    "MOTION",
                    "FILTER",
                    "KAL",
                    "CAL ZERO",
                    "SAVECFG",
                    "FAULTCLR",
                ],
                "optional_commands": [
                    "IDENT",
                    "LOGT",
                    "LOGCSV",
                    "BURSTCSV",
                    "CSVHDR",
                    "CC",
                    "TF",
                    "IMU CAL",
                    "IMU LOAD",
                    "IMU SAVE",
                    "IMU INFO",
                ],
                "warn_only_missing_commands": [],
            },
        },
    }


def _load_compat_policy() -> Dict[str, Any]:
    global _compat_policy_cache
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    policy_path = repo_root / "docs" / "contracts" / "compat_policy_v1.json"
    default = _default_compat_policy()
    if not policy_path.exists():
        return default
    try:
        mtime = policy_path.stat().st_mtime
        if (
            _compat_policy_cache["content"] is not None
            and _compat_policy_cache["mtime"] == mtime
        ):
            return dict(_compat_policy_cache["content"])
        raw = json.loads(policy_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return default
        merged = dict(default)
        merged.update(raw)
        profiles = raw.get("profiles")
        if isinstance(profiles, dict) and profiles:
            merged["profiles"] = profiles
        _compat_policy_cache = {"content": merged, "mtime": mtime}
        return dict(merged)
    except Exception:
        return default


def _status_has_required_fields(
    status: Dict[str, Any], required_fields: list[str]
) -> list[str]:
    missing: list[str] = []
    for field in required_fields:
        if "|" in field:
            aliases = [token.strip() for token in field.split("|") if token.strip()]
            if not any(alias in status for alias in aliases):
                missing.append(field)
            continue
        if field not in status:
            missing.append(field)
    return missing


def _resolve_compat_profile(
    *,
    firmware_id: Optional[str],
    status: Dict[str, Any],
    help_blob: str,
    policy: Dict[str, Any],
) -> str:
    fid = str(firmware_id or "").upper()
    if "CONTROL_LAB" in fid:
        return "control_lab_v1"
    if "PROFILED_RUNTIME" in fid:
        return "profiled_runtime_v1"
    if "MVP_BASELINE" in fid:
        return "baseline_v1"
    if all(token in help_blob for token in ("MOTION", "FILTER", "KAL", "CC", "TF")):
        return "control_lab_v1"
    if "FAULTCLR" in help_blob:
        return "profiled_runtime_v1"
    default_profile = str(policy.get("default_profile", "baseline_v1"))
    if (
        isinstance(policy.get("profiles"), dict)
        and default_profile in policy["profiles"]
    ):
        return default_profile
    return "baseline_v1"


def _resolve_action_gates(
    gateway: NanoSerialGateway,
    control: BridgeControlState,
    prearm_gate: Optional[PreArmSafetyGate] = None,
    *,
    status_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    health = gateway.health()
    connected = bool(health.get("connected", False))
    status_src_raw = (
        status_override
        if isinstance(status_override, dict)
        else dict(health.get("last_status", {}))
    )
    status_src = _normalize_status_for_hud(status_src_raw).get("status", status_src_raw)
    control_snapshot = control.snapshot()
    return _compute_action_gates(
        connected=connected,
        status=status_src,
        control_snapshot=control_snapshot,
        session_fresh=control.session_fresh(),
        prearm_safety=(prearm_gate.snapshot() if prearm_gate is not None else None),
    )


def _require_action_allowed(
    action: str,
    gateway: NanoSerialGateway,
    control: BridgeControlState,
    prearm_gate: Optional[PreArmSafetyGate] = None,
    *,
    status_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    gates = _resolve_action_gates(
        gateway,
        control,
        prearm_gate=prearm_gate,
        status_override=status_override,
    )
    node = gates.get(action, {"ok": True, "reasons": []})
    if not bool(node.get("ok", False)):
        reasons = ",".join([str(r) for r in list(node.get("reasons", [])) if str(r)])
        raise RuntimeError(f"action_blocked:{action}:{reasons}")
    return gates

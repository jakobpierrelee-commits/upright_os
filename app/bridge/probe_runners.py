"""Probe runner and overwatch utilities extracted from server.py."""

from __future__ import annotations

import pathlib
import time
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from app.bridge.nano_serial_gateway import NanoSerialGateway
    from app.bridge.bridge_control_state import BridgeControlState
    from app.bridge.firmware_manager import FirmwareManager

# Optional imports with fallback
try:
    from serial.tools import list_ports
except Exception:
    list_ports = None

# Cross-zone dependency (Zone B must be merged first)
try:
    from app.bridge.contract_readiness import (
        detect_contract_readiness,
        _status_has_required_fields,
        _load_compat_policy,
        _default_compat_policy,
        _resolve_compat_profile,
    )
except ImportError:
    from contract_readiness import (  # type: ignore
        detect_contract_readiness,
        _status_has_required_fields,
        _load_compat_policy,
        _default_compat_policy,
        _resolve_compat_profile,
    )


# Helper functions (duplicated from server.py for Phase 1 standalone operation)
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


def _normalize_status_for_hud(status_raw: Dict[str, Any]) -> Dict[str, Any]:
    """Stub for Phase 1 - returns passthrough. Full impl in server.py."""
    return {"status": status_raw, "adapter": {}}


def _detect_tuning_capabilities(
    status: Dict[str, Any], supported_commands: list, help_lines: list
) -> Dict[str, Any]:
    """Stub for Phase 1 - returns basic capabilities. Full impl in tuning_guards.py."""
    cmds = set(supported_commands)
    return {
        "pid": "PID" in cmds,
        "motion": "MOTION" in cmds,
        "setpoint": "SETPOINT" in cmds,
        "limits": "LIMITS" in cmds,
        "filter": "FILTER" in cmds or "KAL" in cmds,
    }


__all__ = [
    "run_compat_probe",
    "_get_port_meta",
    "_guess_mcu",
    "run_connect_probe",
    "run_setup_compat_test",
    "run_setup_smoke_check",
    "run_setup_overwatch_check",
    "_latest_docs_folder",
    "_validate_docs_artifacts",
    "build_overwatch_report",
]


def run_compat_probe(
    gateway: NanoSerialGateway, *, profile_override: Optional[str] = None
) -> Dict[str, Any]:
    policy = _load_compat_policy()
    required_fields_policy = list(
        policy.get("required_fields", _default_compat_policy()["required_fields"])
    )
    profiles = (
        policy.get("profiles", {}) if isinstance(policy.get("profiles"), dict) else {}
    )
    report: Dict[str, Any] = {
        "ok": False,
        "policy_version": str(policy.get("version", "1.0")),
        "profile": "unknown",
        "firmware_id": None,
        "required_fields": required_fields_policy,
        "required_commands": [],
        "optional_commands": [],
        "missing_fields": [],
        "supported_commands": [],
        "missing_commands": [],
        "blocking_missing_commands": [],
        "warnings": [],
    }

    # 1) Firmware identity probe (best-effort fallback chain)
    firmware_id = None
    for ident_cmd in ("GET_ID", "ID", "WHOAMI", "IDENT"):
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
    status_raw = gateway.get_status()
    norm = _normalize_status_for_hud(status_raw)
    status = dict(norm.get("status", status_raw))
    report["status"] = status
    report["status_raw"] = status_raw
    report["telemetry_adapter"] = dict(norm.get("adapter", {}))
    missing_fields = _status_has_required_fields(status, required_fields_policy)
    report["missing_fields"] = missing_fields

    # 3) Command support probe from HELP output (safe, read-only)
    help_lines: list[str] = []
    try:
        h = gateway.command("HELP", timeout=1.5)
        help_lines = h.get("lines", [])
    except Exception as exc:
        report["warnings"].append(f"help_probe_failed:{exc}")

    help_blob = "\n".join(help_lines).upper()
    requested_profile = str(profile_override or "").strip()
    if requested_profile and requested_profile in profiles:
        selected_profile = requested_profile
    else:
        selected_profile = _resolve_compat_profile(
            firmware_id=firmware_id,
            status=status,
            help_blob=help_blob,
            policy=policy,
        )
    report["profile"] = selected_profile
    profile_policy = (
        profiles.get(selected_profile, {}) if isinstance(profiles, dict) else {}
    )
    required_commands = list(profile_policy.get("required_commands", []))
    optional_commands = list(profile_policy.get("optional_commands", []))
    warn_only_missing = set(profile_policy.get("warn_only_missing_commands", []))
    command_expect = list(dict.fromkeys(required_commands + optional_commands))
    report["required_commands"] = required_commands
    report["optional_commands"] = optional_commands
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
    blocking_missing = [
        c for c in missing if c in required_commands and c not in warn_only_missing
    ]
    report["blocking_missing_commands"] = blocking_missing
    optional_missing = [
        c for c in missing if c in optional_commands or c in warn_only_missing
    ]
    if optional_missing:
        report["warnings"].append(
            f"optional_commands_missing:{','.join(optional_missing)}"
        )
    report["tuning_capabilities"] = _detect_tuning_capabilities(
        status, supported, help_lines
    )

    report["ok"] = len(missing_fields) == 0 and len(blocking_missing) == 0
    if missing_fields:
        report["warnings"].append("status schema mismatch")
    if firmware_id is None:
        report["warnings"].append("no explicit firmware identity command detected")

    # v2 readiness (additive, non-breaking)
    v2_readiness = detect_contract_readiness(status)
    report["contract_version_detected"] = v2_readiness["contract_version_detected"]
    report["v1_ok"] = v2_readiness["v1_ok"]
    report["v2_ready"] = v2_readiness["v2_ready"]
    report["phase1_ready"] = v2_readiness.get("phase1_ready", report["v1_ok"])
    report["phase2_ready"] = v2_readiness.get("phase2_ready", report["v2_ready"])
    report["calibration_flow"] = v2_readiness.get("calibration_flow", "phase1_phase2")
    report["phase1_missing_fields"] = v2_readiness.get("phase1_missing_fields", [])
    report["phase1_present_fields"] = v2_readiness.get("phase1_present_fields", [])
    report["phase2_missing_fields"] = v2_readiness.get(
        "phase2_missing_fields", v2_readiness["v2_missing_fields"]
    )
    report["phase2_present_fields"] = v2_readiness.get(
        "phase2_present_fields", v2_readiness["v2_present_fields"]
    )
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
        compat = {
            "ok": False,
            "error": str(exc),
            "missing_fields": [],
            "missing_commands": [],
        }
        report["warnings"].append(f"compat probe failed: {exc}")

    status = compat.get("status") if isinstance(compat, dict) else None
    status_raw = compat.get("status_raw") if isinstance(compat, dict) else None
    adapter_meta = compat.get("telemetry_adapter") if isinstance(compat, dict) else None
    if not status:
        try:
            status_raw = gateway.get_status()
            norm = _normalize_status_for_hud(status_raw)
            status = dict(norm.get("status", status_raw))
            adapter_meta = dict(norm.get("adapter", {}))
        except Exception as exc:
            report["status_error"] = str(exc)
            status = {}
            status_raw = {}
            adapter_meta = {}

    report["compat"] = compat
    report["status"] = status
    report["status_raw"] = status_raw
    report["telemetry_adapter"] = dict(adapter_meta or {})
    report["firmware_profile"] = str(compat.get("profile", "unknown"))
    report["commands"] = list(compat.get("supported_commands", []))
    report["missing_commands"] = list(compat.get("missing_commands", []))
    report["tuning_capabilities"] = dict(compat.get("tuning_capabilities", {}))

    required_fields = ("mode", "ang", "raw", "out", "kp", "ki", "kd", "set")
    has_gyro = any(k in status for k in ("gyro", "gyr", "gx"))
    report["status_schema_ok"] = all(f in status for f in required_fields) and has_gyro
    report["components"]["imu"] = "ang" in status and "raw" in status and has_gyro
    report["components"]["motor_driver"] = "out" in status
    report["components"]["encoder_feedback"] = "encL" in status or "encR" in status
    report["components"]["voltage_telemetry"] = "volRaw" in status
    report["components"]["wheel_model"] = "wspd" in status and "wpos" in status
    cmds = set(report["commands"])
    report["components"]["persistent_calibration"] = (
        "CAL ZERO" in cmds and "SAVECFG" in cmds
    )

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
        report["warnings"].append(
            "kalman telemetry missing gyro rate field (expected one of: gyro/gyr/gx)"
        )
    if report["missing_commands"]:
        report["warnings"].append(
            "some expected commands were not found in HELP output"
        )

    # v2 readiness (additive, non-breaking)
    v2_readiness = detect_contract_readiness(status)
    report["contract_version_detected"] = v2_readiness["contract_version_detected"]
    report["v1_ok"] = v2_readiness["v1_ok"]
    report["v2_ready"] = v2_readiness["v2_ready"]
    report["phase1_ready"] = v2_readiness.get("phase1_ready", report["v1_ok"])
    report["phase2_ready"] = v2_readiness.get("phase2_ready", report["v2_ready"])
    report["calibration_flow"] = v2_readiness.get("calibration_flow", "phase1_phase2")
    report["phase1_missing_fields"] = v2_readiness.get("phase1_missing_fields", [])
    report["phase1_present_fields"] = v2_readiness.get("phase1_present_fields", [])
    report["phase2_missing_fields"] = v2_readiness.get(
        "phase2_missing_fields", v2_readiness["v2_missing_fields"]
    )
    report["phase2_present_fields"] = v2_readiness.get(
        "phase2_present_fields", v2_readiness["v2_present_fields"]
    )
    report["v2_missing_fields"] = v2_readiness["v2_missing_fields"]
    report["v2_factory_ready"] = v2_readiness["v2_factory_ready"]
    report["v2_factory_missing_fields"] = v2_readiness["v2_factory_missing_fields"]
    report["v2_present_fields"] = v2_readiness["v2_present_fields"]
    report["readiness_checks"] = v2_readiness["readiness_checks"]

    # Recommended next action for Phase 2 readiness.
    phase2_recommended_action: Optional[str] = None
    if not v2_readiness["phase1_ready"]:
        phase2_recommended_action = "Run Calibration Phase 1 (core sensor zero + baseline checks) before arming."
    elif not v2_readiness["v2_ready"]:
        missing = v2_readiness["v2_missing_fields"]
        if "gyro_bias" in missing:
            phase2_recommended_action = "Run Calibration Phase 2 to establish gyro bias and advanced anti-drift telemetry."
        elif "vel_meas" in missing:
            phase2_recommended_action = (
                "Complete Calibration Phase 2: enable velocity feedback telemetry."
            )
        elif "outer_loop_enabled" in missing:
            phase2_recommended_action = "Complete Calibration Phase 2: enable outer velocity loop for anti-drift."
        else:
            phase2_recommended_action = (
                "Complete Calibration Phase 2 for advanced anti-drift capabilities."
            )
    report["phase2_recommended_action"] = phase2_recommended_action
    # Backward-compatible alias retained for migration window.
    report["v2_recommended_action"] = phase2_recommended_action

    return report


def run_setup_compat_test(gateway: NanoSerialGateway) -> Dict[str, Any]:
    compat = run_compat_probe(gateway)
    missing_fields = list(
        compat.get("missing_fields", []) if isinstance(compat, dict) else []
    )
    missing_commands = list(
        compat.get("missing_commands", []) if isinstance(compat, dict) else []
    )
    blocking_missing_commands = list(
        compat.get("blocking_missing_commands", []) if isinstance(compat, dict) else []
    )
    optional_commands = {"MOTION"}
    hard_missing_commands = (
        blocking_missing_commands
        if blocking_missing_commands
        else [c for c in missing_commands if c not in optional_commands]
    )
    warnings = list(compat.get("warnings", []) if isinstance(compat, dict) else [])
    blocking_issues: list[str] = []
    if missing_fields:
        blocking_issues.append(f"missing_fields:{','.join(missing_fields)}")
    if hard_missing_commands:
        blocking_issues.append(f"missing_commands:{','.join(hard_missing_commands)}")
    if bool(compat.get("ok", False)) and not hard_missing_commands:
        status = (
            "warn"
            if (
                warnings
                or (len(missing_commands) > 0 and len(hard_missing_commands) == 0)
            )
            else "pass"
        )
    else:
        status = "fail"
    if gateway.health().get("connected", False) is False:
        status = "unavailable"
        if "serial_disconnected" not in blocking_issues:
            blocking_issues.append("serial_disconnected")
    prompts: list[str] = []
    if missing_fields:
        prompts.append(
            "Summarize missing telemetry fields and provide exact sketch additions needed to satisfy compat."
        )
    if hard_missing_commands:
        prompts.append(
            "List missing commands and generate minimal command handler updates for compat pass."
        )
    elif missing_commands:
        prompts.append(
            "Optional commands are missing. Confirm whether MOTION should be implemented for this profile."
        )
    if not prompts:
        prompts.append("Compat passed. Recommend next smoke-check sequence.")
    return {
        "status": status,
        "blocking_issues": blocking_issues,
        "warnings": warnings,
        "recommended_fix_prompts": prompts,
        "compat": compat,
        "tested_at": time.time(),
    }


def run_setup_smoke_check(
    gateway: NanoSerialGateway, control: BridgeControlState
) -> Dict[str, Any]:
    health = gateway.health()
    connected = bool(health.get("connected", False))
    status = health.get("last_status", {})
    feed_hz = _safe_float(status.get("hz"))
    angle = _safe_float(status.get("ang"))
    mode = str(status.get("mode", "UNKNOWN")).upper()
    estop = bool(control.snapshot().get("estop_latched", False))

    checks: list[Dict[str, Any]] = []
    checks.append(
        {
            "id": "serial_connected",
            "status": "pass" if connected else "fail",
            "detail": "serial connected" if connected else "serial disconnected",
        }
    )
    checks.append(
        {
            "id": "estop_clear",
            "status": "pass" if not estop else "fail",
            "detail": "e-stop clear" if not estop else "e-stop latched",
        }
    )
    checks.append(
        {
            "id": "telemetry_mode_known",
            "status": "pass" if mode not in {"", "UNKNOWN"} else "warn",
            "detail": f"mode={mode or 'UNKNOWN'}",
        }
    )
    checks.append(
        {
            "id": "telemetry_feed",
            "status": "pass" if (feed_hz is not None and feed_hz >= 5.0) else "warn",
            "detail": f"feed_hz={feed_hz if feed_hz is not None else 'n/a'}",
        }
    )
    checks.append(
        {
            "id": "angle_streaming",
            "status": "pass" if angle is not None else "warn",
            "detail": f"angle={angle if angle is not None else 'n/a'}",
        }
    )

    fail_count = sum(1 for c in checks if c["status"] == "fail")
    warn_count = sum(1 for c in checks if c["status"] == "warn")
    if not connected:
        overall = "unavailable"
    elif fail_count > 0:
        overall = "fail"
    elif warn_count > 0:
        overall = "warn"
    else:
        overall = "pass"
    failing = [c["id"] for c in checks if c["status"] in {"fail", "warn"}]
    return {
        "status": overall,
        "checks": checks,
        "failure_summary": ", ".join(failing) if failing else "",
        "tested_at": time.time(),
    }


def run_setup_overwatch_check(
    gateway: NanoSerialGateway, firmware: FirmwareManager
) -> Dict[str, Any]:
    report = build_overwatch_report(
        gateway=gateway, firmware=firmware, compat=None, connect=None
    )
    overall = str(report.get("overall", "warn")).lower()
    status = overall if overall in {"pass", "warn", "fail"} else "warn"
    return {
        "status": status,
        "overwatch": report,
        "tested_at": time.time(),
    }


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

    def add_check(
        check_id: str, label: str, status: str, detail: str, evidence: str = ""
    ) -> None:
        checks.append(
            {
                "id": check_id,
                "label": label,
                "status": status,
                "detail": detail,
                "evidence": evidence,
            }
        )
        if status != "pass":
            actions.append(f"{label}: {detail}")

    health = gateway.health()
    connected = bool(health.get("connected", False))
    add_check(
        "serial_connected",
        "Serial Link",
        "pass" if connected else "fail",
        "Bridge has active serial session"
        if connected
        else "Bridge is not connected to serial device",
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
        "Required telemetry fields present"
        if v1_ok
        else "Required telemetry fields missing",
        f"version={readiness.get('contract_version_detected', 'unknown')}",
    )
    add_check(
        "antidrift_v2_ready",
        "Anti-Drift Readiness",
        "pass" if v2_ready else ("warn" if v1_ok else "fail"),
        "v2 anti-drift fields present"
        if v2_ready
        else "v2 anti-drift fields incomplete",
        f"missing={','.join(readiness.get('v2_missing_fields', [])) or 'none'}",
    )

    compat_report = compat if isinstance(compat, dict) else {}
    missing_commands = (
        list(compat_report.get("missing_commands", []))
        if isinstance(compat_report.get("missing_commands", []), list)
        else []
    )
    optional_commands = {"MOTION"}
    hard_missing_commands = [c for c in missing_commands if c not in optional_commands]
    only_optional_missing = bool(missing_commands) and not hard_missing_commands
    command_status = (
        "pass"
        if not missing_commands
        else ("warn" if only_optional_missing else "fail")
    )
    command_detail = (
        "Required command set detected"
        if not missing_commands
        else (
            "Optional commands missing"
            if only_optional_missing
            else "Missing required commands"
        )
    )
    add_check(
        "command_contract",
        "Command Contract",
        command_status,
        command_detail,
        ",".join(missing_commands) if missing_commands else "none",
    )

    fw_status = firmware.status()
    default_sketch = pathlib.Path(str(fw_status.get("defaults", {}).get("sketch", "")))
    sketch_path = default_sketch
    if sketch_path.exists() and sketch_path.is_dir():
        preferred = sketch_path / f"{sketch_path.name}.ino"
        if preferred.exists() and preferred.is_file():
            sketch_path = preferred
        else:
            fallback = sorted(sketch_path.glob("*.ino"))
            if fallback:
                sketch_path = fallback[0]
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
    docs_check = (
        _validate_docs_artifacts(docs_dir)
        if docs_exists and docs_dir is not None
        else {"ok": False, "missing": [], "invalid": [], "required": []}
    )
    docs_mtime = (
        docs_dir.stat().st_mtime if docs_exists and docs_dir is not None else None
    )
    docs_fresh = bool(
        sketch_mtime is not None
        and docs_mtime is not None
        and docs_mtime >= sketch_mtime
    )
    docs_ok = bool(docs_exists and docs_check.get("ok", False) and docs_fresh)
    docs_status = "pass" if docs_ok else ("warn" if not docs_exists else "fail")
    docs_detail = (
        "Docs pack is synced to sketch"
        if docs_ok
        else (
            "Docs pack not generated yet"
            if not docs_exists
            else "Docs pack missing, invalid, or stale vs sketch"
        )
    )
    docs_evidence = f"docs={str(docs_dir) if docs_dir else 'none'}; fresh={str(docs_fresh).lower()}; missing={','.join(docs_check.get('missing', [])) or 'none'}; invalid={','.join(docs_check.get('invalid', [])) or 'none'}"
    add_check("docs_sync", "Docs Integrity", docs_status, docs_detail, docs_evidence)

    gyro_present = any(k in status for k in ("gyro", "gyr", "gx"))
    hud_ok = ("ang" in status) and ("raw" in status) and gyro_present
    add_check(
        "hud_sensor_contract",
        "HUD Sensor Contract",
        "pass" if hud_ok else "fail",
        "HUD sensor fields available"
        if hud_ok
        else "HUD fields missing (need ang/raw/gyro alias)",
        f"fields={','.join(sorted(status.keys())[:12])}",
    )

    setpoint = _first_float(status, "set")
    filtered_angle = _first_float(status, "ang")
    raw_angle = _first_float(status, "raw")
    pid_err = _first_float(status, "pid_err", "err")
    out_sat = _first_float(status, "pid_u_sat", "out")
    out_unsat = _first_float(status, "pid_u_unsat", "pid_u", "u")
    if pid_err is None and setpoint is not None and filtered_angle is not None:
        pid_err = setpoint - filtered_angle

    signal_chain_ok = (
        setpoint is not None
        and filtered_angle is not None
        and pid_err is not None
        and out_sat is not None
    )
    add_check(
        "control_signal_chain",
        "Signal/Error/Output Chain",
        "pass" if signal_chain_ok else "warn",
        "Signal, error, and output telemetry present"
        if signal_chain_ok
        else "Missing one or more of set/ang/pid_err/out telemetry fields",
        f"set={setpoint if setpoint is not None else 'n/a'}; ang={filtered_angle if filtered_angle is not None else 'n/a'}; err={pid_err if pid_err is not None else 'n/a'}; out={out_sat if out_sat is not None else 'n/a'}",
    )

    innovation = _first_float(status, "kal_innov", "innovation")
    if innovation is None and raw_angle is not None and filtered_angle is not None:
        innovation = raw_angle - filtered_angle
    if innovation is not None:
        innovation_abs = abs(float(innovation))
        innovation_status = (
            "pass"
            if innovation_abs <= 5.0
            else ("warn" if innovation_abs <= 12.0 else "fail")
        )
        innovation_detail = (
            "Estimator innovation is nominal"
            if innovation_status == "pass"
            else (
                "Estimator innovation elevated; verify calibration/filter tuning"
                if innovation_status == "warn"
                else "Estimator innovation high; check sensor alignment/calibration"
            )
        )
        add_check(
            "kalman_innovation",
            "Kalman Innovation",
            innovation_status,
            innovation_detail,
            f"innovation_deg={innovation:.3f}",
        )
    else:
        add_check(
            "kalman_innovation",
            "Kalman Innovation",
            "warn",
            "Innovation telemetry not available (derive raw-ang or emit kal_innov)",
            "innovation_deg=n/a",
        )

    if out_unsat is not None and out_sat is not None:
        sat_delta = abs(out_unsat - out_sat)
        sat_status = (
            "pass" if sat_delta < 0.5 else ("warn" if sat_delta < 5.0 else "fail")
        )
        add_check(
            "output_clamp_visibility",
            "Output Clamp Visibility",
            sat_status,
            "Saturation metadata available"
            if sat_status == "pass"
            else (
                "Clamp activity present (expected during aggressive maneuvers)"
                if sat_status == "warn"
                else "Heavy clamp activity; revisit limits/gains"
            ),
            f"u_unsat={out_unsat:.3f}; u_sat={out_sat:.3f}",
        )

    loop_hz = _first_float(status, "loop_hz", "loopHz", "hz")
    if loop_hz is None:
        period_us = _first_float(status, "period_us", "loop_period_us")
        if period_us is not None and period_us > 0.0:
            loop_hz = 1000000.0 / period_us
    loop_status = (
        "pass"
        if (loop_hz is not None and loop_hz >= 45.0)
        else ("warn" if (loop_hz is not None and loop_hz >= 20.0) else "fail")
    )
    add_check(
        "loop_rate",
        "Loop Feed Quality",
        loop_status,
        "Loop rate optimal"
        if loop_status == "pass"
        else (
            "Loop rate sufficient but not optimal"
            if loop_status == "warn"
            else "Loop rate too low"
        ),
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
        "counts": {
            "pass": pass_count,
            "warn": warn_count,
            "fail": fail_count,
            "total": len(checks),
        },
        "actions": actions[:8],
        "contract_version_detected": readiness.get(
            "contract_version_detected", "unknown"
        ),
        "connect_confidence_pct": int(connect_report.get("confidence_pct", 0) or 0)
        if connect_report
        else 0,
        "docs": {
            "latest_folder": str(docs_dir) if docs_dir else None,
            "exists": docs_exists,
            "fresh": docs_fresh,
            "check": docs_check,
            "sketch_path": str(sketch_path),
        },
    }

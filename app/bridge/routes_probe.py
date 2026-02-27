"""
Probe route handlers extracted from server.py (Phase B+).

These handlers manage hardware probing and compatibility checks.
"""
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from app.bridge.clean_probe import build_compat_probe_payload, build_probe_payload
except ImportError:
    from clean_probe import build_compat_probe_payload, build_probe_payload  # type: ignore


def handle_probe_compat_get(
    *,
    query: Dict[str, List[str]],
    gateway: Any,
    cached_probe_fn: Callable[[str], Optional[Dict[str, Any]]],
    store_probe_fn: Callable[[str, Dict[str, Any]], None],
    run_compat_probe_fn: Callable[..., Dict[str, Any]],
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /probe/compat GET request.

    Returns (status_code, payload).
    """
    requested_profile = str(
        (query.get("profile", [""]) or [""])[0] or ""
    ).strip()
    cache_key = (
        f"compat:{requested_profile}" if requested_profile else "compat"
    )
    cached = cached_probe_fn(cache_key)
    if cached is not None:
        return 200, build_compat_probe_payload(compat=cached)

    if int(gateway.health().get("queue_depth", 0) or 0) > 2:
        fallback = {
            "ok": False,
            "profile": "unknown",
            "firmware_id": None,
            "required_fields": [],
            "missing_fields": [],
            "supported_commands": [],
            "missing_commands": [],
            "warnings": ["compat_probe_throttled_queue_busy"],
        }
        return 200, build_compat_probe_payload(compat=fallback)

    out = run_compat_probe_fn(gateway, profile_override=requested_profile or None)
    store_probe_fn(cache_key, out)
    return 200, build_compat_probe_payload(compat=out)


def handle_probe_connect_get(
    *,
    gateway: Any,
    cached_probe_fn: Callable[[str], Optional[Dict[str, Any]]],
    store_probe_fn: Callable[[str, Dict[str, Any]], None],
    run_connect_probe_fn: Callable[..., Dict[str, Any]],
    get_port_meta_fn: Callable[[str], Dict[str, Any]],
    detect_tuning_capabilities_fn: Callable[..., Dict[str, Any]],
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /probe/connect GET request.

    Returns (status_code, payload).
    """
    cached = cached_probe_fn("connect")
    if cached is not None:
        return 200, build_probe_payload(probe=cached)

    if int(gateway.health().get("queue_depth", 0) or 0) > 2:
        fallback = {
            "ok": False,
            "connected": bool(gateway.health().get("connected", False)),
            "port": str(gateway.health().get("port", "")),
            "baud": int(gateway.health().get("baud", 0) or 0),
            "port_meta": get_port_meta_fn(str(gateway.health().get("port", ""))),
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
            "warnings": ["connect_probe_throttled_queue_busy"],
            "next_questions": [],
            "compat": None,
            "tuning_capabilities": detect_tuning_capabilities_fn({}, [], []),
        }
        return 200, build_probe_payload(probe=fallback)

    out = run_connect_probe_fn(gateway)
    store_probe_fn("connect", out)
    return 200, build_probe_payload(probe=out)


def handle_setup_compat_test(
    *,
    body: Dict[str, Any],
    gateway: Any,
    setup_attempt_history: Any,
    run_setup_compat_test_fn: Callable,
    current_sketch_hash_fn: Callable[[], str],
    report_design_observation_fn: Callable,
    build_setup_check_payload_fn: Callable,
) -> Tuple[int, Dict[str, Any]]:
    """Handle /v1/setup/compat-test POST request."""
    sketch_revision = str(body.get("sketch_revision", "")).strip()
    action_source = str(body.get("action_source", "setup_page")).strip() or "setup_page"
    session_key = str(body.get("session_key", "")).strip() or "local:setup"
    profile_id = str(body.get("profile_id", "")).strip()
    profile_label = str(body.get("profile_label", "")).strip()
    
    out = run_setup_compat_test_fn(gateway)
    attempt = setup_attempt_history.append(
        test_type="compat",
        status=str(out.get("status", "unknown")),
        sketch_revision=sketch_revision,
        sketch_hash=current_sketch_hash_fn(),
        action_source=action_source,
        profile_id=profile_id,
        profile_label=profile_label,
        result=out,
    )
    try:
        report_design_observation_fn(
            session_key=session_key,
            success=str(out.get("status", "")).strip().lower() == "pass",
            source="setup_compat_test",
            note=str(out.get("failure_summary", "")).strip(),
            profile_id=profile_id,
            profile_label=profile_label,
            sketch_revision=sketch_revision,
            sketch_hash=str(attempt.get("sketch_hash", "")).strip(),
            test_type="compat",
        )
    except Exception:
        pass
    return 200, build_setup_check_payload_fn(
        check_key="compat_test", check_result=out, attempt=attempt
    )


def handle_setup_smoke_check(
    *,
    body: Dict[str, Any],
    gateway: Any,
    control: Any,
    setup_attempt_history: Any,
    run_setup_smoke_check_fn: Callable,
    current_sketch_hash_fn: Callable[[], str],
    report_design_observation_fn: Callable,
    build_setup_check_payload_fn: Callable,
) -> Tuple[int, Dict[str, Any]]:
    """Handle /v1/setup/smoke-check POST request."""
    sketch_revision = str(body.get("sketch_revision", "")).strip()
    action_source = str(body.get("action_source", "setup_page")).strip() or "setup_page"
    session_key = str(body.get("session_key", "")).strip() or "local:setup"
    profile_id = str(body.get("profile_id", "")).strip()
    profile_label = str(body.get("profile_label", "")).strip()
    
    out = run_setup_smoke_check_fn(gateway, control)
    attempt = setup_attempt_history.append(
        test_type="smoke",
        status=str(out.get("status", "unknown")),
        sketch_revision=sketch_revision,
        sketch_hash=current_sketch_hash_fn(),
        action_source=action_source,
        profile_id=profile_id,
        profile_label=profile_label,
        result=out,
    )
    try:
        report_design_observation_fn(
            session_key=session_key,
            success=str(out.get("status", "")).strip().lower() == "pass",
            source="setup_smoke_check",
            note=str(out.get("failure_summary", "")).strip(),
            profile_id=profile_id,
            profile_label=profile_label,
            sketch_revision=sketch_revision,
            sketch_hash=str(attempt.get("sketch_hash", "")).strip(),
            test_type="smoke",
        )
    except Exception:
        pass
    return 200, build_setup_check_payload_fn(
        check_key="smoke_check", check_result=out, attempt=attempt
    )


def handle_setup_overwatch_check(
    *,
    body: Dict[str, Any],
    gateway: Any,
    firmware: Any,
    setup_attempt_history: Any,
    run_setup_overwatch_check_fn: Callable,
    current_sketch_hash_fn: Callable[[], str],
    report_design_observation_fn: Callable,
    build_setup_check_payload_fn: Callable,
) -> Tuple[int, Dict[str, Any]]:
    """Handle /v1/setup/overwatch-check POST request."""
    sketch_revision = str(body.get("sketch_revision", "")).strip()
    action_source = str(body.get("action_source", "setup_page")).strip() or "setup_page"
    session_key = str(body.get("session_key", "")).strip() or "local:setup"
    profile_id = str(body.get("profile_id", "")).strip()
    profile_label = str(body.get("profile_label", "")).strip()
    
    out = run_setup_overwatch_check_fn(gateway, firmware)
    attempt = setup_attempt_history.append(
        test_type="overwatch",
        status=str(out.get("status", "unknown")),
        sketch_revision=sketch_revision,
        sketch_hash=current_sketch_hash_fn(),
        action_source=action_source,
        profile_id=profile_id,
        profile_label=profile_label,
        result=out,
    )
    try:
        report_design_observation_fn(
            session_key=session_key,
            success=str(out.get("status", "")).strip().lower() == "pass",
            source="setup_overwatch_check",
            note=str(out.get("failure_summary", "")).strip(),
            profile_id=profile_id,
            profile_label=profile_label,
            sketch_revision=sketch_revision,
            sketch_hash=str(attempt.get("sketch_hash", "")).strip(),
            test_type="overwatch",
        )
    except Exception:
        pass
    return 200, build_setup_check_payload_fn(
        check_key="overwatch_check", check_result=out, attempt=attempt
    )


def classify_imu_command_result(
    res: Dict[str, Any], *, cmd_name: str
) -> Dict[str, Any]:
    """Classify an IMU command result into success/error categories."""
    lines = list(res.get("lines", [])) if isinstance(res, dict) else []
    matched = str(res.get("matched", "")) if isinstance(res, dict) else ""
    candidates: list[str] = []
    if matched:
        candidates.append(matched)
    candidates.extend(reversed(lines))
    imu_line = ""
    for ln in candidates:
        txt = str(ln or "").strip()
        if "IMU" in txt.upper():
            imu_line = txt
            break
    if not imu_line:
        return {
            "ok": False,
            "error": f"imu_{cmd_name.lower()}_no_response",
            "detail": "",
        }

    up = imu_line.upper()
    if up.startswith("OK IMU_"):
        return {"ok": True, "error": "", "detail": imu_line}
    if "ERR UNKNOWN" in up and "IMU" in up:
        return {
            "ok": False,
            "error": "imu_command_unsupported:flash_runtime_with_imu_calibration_support",
            "detail": imu_line,
        }
    if "EEPROM_UNAVAILABLE" in up:
        return {
            "ok": False,
            "error": "imu_eeprom_unavailable",
            "detail": imu_line,
        }
    if "IMU_NOT_READY" in up:
        return {"ok": False, "error": "imu_not_ready", "detail": imu_line}
    return {
        "ok": False,
        "error": f"imu_{cmd_name.lower()}_failed",
        "detail": imu_line,
    }

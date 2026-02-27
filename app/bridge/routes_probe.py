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

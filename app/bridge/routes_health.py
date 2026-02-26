"""
Health/status route handlers extracted from server.py (Phase B, Slice 1).

These handlers provide system health and robot status endpoints.
"""

from typing import Any, Dict, Tuple

try:
    from app.bridge.clean_status import (
        build_health_payload,
        build_status_payload,
    )
except ImportError:
    from clean_status import (  # type: ignore
        build_health_payload,
        build_status_payload,
    )


def handle_health(
    *,
    gateway: Any,
    control: Any,
    prearm_safety: Any,
    telemetry_port: int,
    telemetry_enabled: bool,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /health GET request.

    Returns (status_code, payload).
    """
    return 200, build_health_payload(
        serial_health=gateway.health(),
        control_snapshot=control.snapshot(),
        prearm_snapshot=prearm_safety.snapshot(),
        telemetry_port=telemetry_port,
        telemetry_enabled=telemetry_enabled,
    )


def handle_status(
    *,
    gateway: Any,
    control: Any,
    prearm_safety: Any,
    normalize_status_fn: Any,
    resolve_action_gates_fn: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /status GET request.

    Returns (status_code, payload).
    Non-blocking: returns cached status only.
    """
    st_raw = dict(gateway.health().get("last_status", {}))
    normalized = normalize_status_fn(st_raw)
    st = dict(normalized.get("status", st_raw))
    return 200, build_status_payload(
        status=st,
        status_raw=st_raw,
        telemetry_adapter=normalized.get("adapter", {}),
        control_snapshot=control.snapshot(),
        prearm_snapshot=prearm_safety.snapshot(),
        action_gates=resolve_action_gates_fn(
            gateway,
            control,
            prearm_gate=prearm_safety,
            status_override=st,
        ),
    )

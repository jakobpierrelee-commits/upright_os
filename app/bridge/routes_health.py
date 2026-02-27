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


def handle_telemetry_adapter_map_get(
    *,
    gateway: Any,
    normalize_status_fn: Any,
    build_telemetry_adapters_payload_fn: Any,
    runtime_telemetry_adapters: Any,
    hud_canonical_fields: list,
) -> Tuple[int, Dict[str, Any]]:
    """Handle /telemetry/adapter-map GET request."""
    st_raw = dict(gateway.health().get("last_status", {}))
    normalized = normalize_status_fn(st_raw)
    return 200, build_telemetry_adapters_payload_fn(
        adapter=normalized.get("adapter", {}),
        adapters=runtime_telemetry_adapters,
        canonical_fields=hud_canonical_fields,
    )


def handle_diag_serial_get(
    *,
    gateway: Any,
    control: Any,
    build_diag_serial_payload_fn: Any,
) -> Tuple[int, Dict[str, Any]]:
    """Handle /diag/serial GET request."""
    return 200, build_diag_serial_payload_fn(
        serial=gateway.health(),
        control=control.snapshot(),
    )


def handle_lines_get(
    *,
    gateway: Any,
    n: int,
    build_lines_payload_fn: Any,
) -> Tuple[int, Dict[str, Any]]:
    """Handle /lines GET request."""
    return 200, build_lines_payload_fn(lines=gateway.recent_lines(n))

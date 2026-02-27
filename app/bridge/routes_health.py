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


def handle_burst_status_get(
    *,
    burst_status_fn: Any,
    build_burst_status_payload_fn: Any,
) -> Tuple[int, Dict[str, Any]]:
    """Handle /burst/status GET request."""
    return 200, build_burst_status_payload_fn(burst=burst_status_fn())


def handle_commissioning_status_get(
    *,
    commissioning: Any,
    build_commissioning_status_payload_fn: Any,
) -> Tuple[int, Dict[str, Any]]:
    """Handle /commissioning/status GET request."""
    return 200, build_commissioning_status_payload_fn(commissioning=commissioning.status())


def read_csv_tail(path: Any, max_tail: int = 80) -> Dict[str, Any]:
    """Read the tail of a CSV file for AI context."""
    import collections
    total_lines = 0
    header = ""
    tail: "collections.deque[str]" = collections.deque(maxlen=max(1, max_tail))
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for idx, line in enumerate(f):
            txt = line.rstrip("\n")
            if idx == 0:
                header = txt
            else:
                tail.append(txt)
            total_lines = idx + 1
    return {
        "header": header,
        "tail": list(tail),
        "total_lines": total_lines,
        "max_tail": max_tail,
    }


def commissioning_ai_context(commissioning: Any, *, read_csv_tail_fn: Any) -> Dict[str, Any]:
    """Build commissioning context for AI."""
    import json
    import pathlib
    out: Dict[str, Any] = {
        "status": commissioning.status(),
        "artifacts": commissioning.artifacts(),
    }

    latest_metrics = out["artifacts"].get("latest_metrics")
    if isinstance(latest_metrics, str) and latest_metrics:
        p = pathlib.Path(latest_metrics)
        try:
            out["latest_metrics_json"] = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            out["latest_metrics_error"] = str(exc)

    latest_run = out["artifacts"].get("latest_run")
    if isinstance(latest_run, str) and latest_run:
        p = pathlib.Path(latest_run)
        try:
            out["latest_run_csv"] = read_csv_tail_fn(p, max_tail=80)
        except Exception as exc:
            out["latest_run_error"] = str(exc)

    return out


def host_capture_ai_context(host_capture: Any, *, read_csv_tail_fn: Any) -> Dict[str, Any]:
    """Build host capture context for AI."""
    import pathlib
    out: Dict[str, Any] = {"status": host_capture.status()}
    latest = out["status"].get("latest_run")
    if isinstance(latest, str) and latest:
        p = pathlib.Path(latest)
        if p.exists():
            try:
                out["latest_run_csv"] = read_csv_tail_fn(p, max_tail=80)
            except Exception as exc:
                out["latest_run_error"] = str(exc)
    return out


def handle_commissioning_artifacts_get(
    *,
    commissioning: Any,
    build_commissioning_artifacts_payload_fn: Any,
) -> Tuple[int, Dict[str, Any]]:
    """Handle /commissioning/artifacts GET request."""
    return 200, build_commissioning_artifacts_payload_fn(commissioning=commissioning.artifacts())

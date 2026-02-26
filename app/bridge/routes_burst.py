"""
Burst capture route handlers extracted from server.py (Phase C).

These handlers manage burst capture arming and labeling.
"""
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from app.bridge.clean_misc import (
        build_burst_label_payload,
        build_firmware_cmd_status_payload,
    )
except ImportError:
    from clean_misc import (  # type: ignore
        build_burst_label_payload,
        build_firmware_cmd_status_payload,
    )


def handle_burst_arm(
    *,
    body: Dict[str, Any],
    gateway: Any,
    host_capture: Any,
    burst_status_fn: Callable[[], Dict[str, Any]],
    active_profile: Optional[Dict[str, Any]],
    defaults: Dict[str, Any],
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /burst/arm POST request.

    Returns (status_code, payload).
    """
    delay_raw = body.get("delay_ms")
    delay_ms = int(delay_raw) if delay_raw is not None else 3000
    lines = int(body.get("lines", 80) or 80)
    freq_hz = (
        float(body.get("freq_hz"))
        if body.get("freq_hz") is not None
        else float(defaults.get("freq_hz", 25.0))
    )
    trigger_enabled = (
        bool(body.get("trigger_enabled"))
        if body.get("trigger_enabled") is not None
        else bool(defaults.get("trigger_enabled", True))
    )
    prebuffer_lines = (
        int(body.get("prebuffer_lines"))
        if body.get("prebuffer_lines") is not None
        else int(defaults.get("prebuffer_lines", 24))
    )
    trigger_angle_deg = (
        float(body.get("trigger_angle_deg"))
        if body.get("trigger_angle_deg") is not None
        else float(defaults.get("trigger_angle_deg", 8.0))
    )
    trigger_out_frac = (
        float(body.get("trigger_out_frac"))
        if body.get("trigger_out_frac") is not None
        else float(defaults.get("trigger_out_frac", 0.90))
    )
    trigger_runaway = (
        float(body.get("trigger_runaway"))
        if body.get("trigger_runaway") is not None
        else float(defaults.get("trigger_runaway", 0.65))
    )
    post_trigger_lines = (
        int(body.get("post_trigger_lines"))
        if body.get("post_trigger_lines") is not None
        else int(defaults.get("post_trigger_lines", 20))
    )
    run_intent = (
        str(body.get("run_intent", "unassisted_tuning")).strip() or "unassisted_tuning"
    )
    changed_params_raw = body.get("changed_params", [])
    changed_params: List[str] = []
    if isinstance(changed_params_raw, list):
        changed_params = [
            str(x).strip() for x in changed_params_raw if str(x).strip()
        ][:4]
    operator_outcome = str(body.get("operator_outcome", "")).strip()
    operator_assisted = bool(body.get("operator_assisted", False))
    operator_notes = str(body.get("operator_notes", "")).strip()

    h = gateway.health()
    st = dict(h.get("last_status", {}))
    if not bool(h.get("connected", False)):
        return 409, {"ok": False, "error": "serial_disconnected"}

    cmd = f"BURSTCSV {max(0, min(delay_ms, 60000))} {max(1, min(lines, 3000))}"
    host = host_capture.arm(
        delay_ms=delay_ms,
        lines=lines,
        freq_hz=freq_hz,
        trigger_enabled=trigger_enabled,
        prebuffer_lines=prebuffer_lines,
        trigger_angle_deg=trigger_angle_deg,
        trigger_out_frac=trigger_out_frac,
        trigger_runaway=trigger_runaway,
        post_trigger_lines=post_trigger_lines,
        run_intent=run_intent,
        changed_params=changed_params,
        operator_outcome=operator_outcome,
        operator_assisted=operator_assisted,
        operator_notes=operator_notes,
    )

    fw: Dict[str, Any] = {"ok": True, "cmd": cmd, "queued": True}
    try:
        # Keep endpoint responsive when serial is momentarily busy.
        fw["result"] = gateway.command(cmd, timeout=1.0)
    except Exception as exc:
        fw["ok"] = False
        fw["error"] = str(exc)

    return 200, build_firmware_cmd_status_payload(
        status=st,
        firmware=fw,
        capture_defaults=defaults,
        burst=burst_status_fn(),
        host_capture=host,
    )


def handle_burst_label(
    *,
    body: Dict[str, Any],
    host_capture: Any,
    burst_status_fn: Callable[[], Dict[str, Any]],
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /burst/label POST request.

    Returns (status_code, payload).
    """
    outcome = str(body.get("operator_outcome", "")).strip()
    assisted = bool(body.get("operator_assisted", False))
    notes = str(body.get("operator_notes", "")).strip()
    run_intent = str(body.get("run_intent", "")).strip()
    changed_params_raw = body.get("changed_params", None)
    changed_params: Optional[List[str]] = None
    if isinstance(changed_params_raw, list):
        changed_params = [
            str(x).strip() for x in changed_params_raw if str(x).strip()
        ][:4]

    host = host_capture.label_latest_run(
        outcome=outcome,
        assisted=assisted,
        notes=notes,
        run_intent=run_intent,
        changed_params=changed_params,
    )

    return 200, build_burst_label_payload(burst=burst_status_fn(), host_capture=host)

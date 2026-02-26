"""
Arm/disarm route handlers extracted from server.py (Phase B/C).

These handlers manage arm, disarm, estop, precheck, and command operations.
"""
from typing import Any, Callable, Dict, Optional, Tuple

try:
    from app.bridge.clean_misc import (
        build_control_payload,
        build_result_control_payload,
    )
    from app.bridge.clean_safety import (
        build_arm_precheck_payload,
        build_status_control_payload,
    )
    from app.bridge.clean_contracts import validate_prearm_precheck_response
except ImportError:
    from clean_misc import (  # type: ignore
        build_control_payload,
        build_result_control_payload,
    )
    from clean_safety import (  # type: ignore
        build_arm_precheck_payload,
        build_status_control_payload,
    )
    from clean_contracts import validate_prearm_precheck_response  # type: ignore


def handle_command(
    *,
    body: Dict[str, Any],
    gateway: Any,
    control: Any,
    blocked_while_latched_fn: Callable[[str], bool],
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /command POST request.

    Returns (status_code, payload).
    """
    cmd = str(body.get("cmd", "")).strip()
    if not cmd:
        return 400, {"ok": False, "error": "missing cmd"}
    if control.snapshot()["estop_latched"] and blocked_while_latched_fn(cmd):
        return 423, {
            "ok": False,
            "error": "estop_latched",
            "control": control.snapshot(),
        }
    expect = body.get("expect")
    timeout = float(body.get("timeout", 2.0))
    res = (
        gateway.command(cmd, expect_contains=str(expect), timeout=timeout)
        if expect
        else gateway.command(cmd, timeout=timeout)
    )
    return 200, build_result_control_payload(result=res, control=control.snapshot())


def handle_arm_prepare(
    *,
    control: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /arm/prepare POST request.

    Returns (status_code, payload).
    """
    return 200, build_control_payload(control=control.prepare_arm())


def handle_arm_confirm(
    *,
    gateway: Any,
    control: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /arm/confirm POST request.

    Returns (status_code, payload).
    """
    control.consume_arm_prepare()
    gateway.command("ARM", timeout=1.0)
    return 200, build_status_control_payload(
        status=gateway.get_status(),
        control=control.snapshot(),
    )


def handle_arm(
    *,
    gateway: Any,
    control: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /arm POST request.

    Returns (status_code, payload).
    """
    gateway.command("ARM", timeout=1.0)
    control.clear_arm_prepare()
    return 200, build_status_control_payload(
        status=gateway.get_status(),
        control=control.snapshot(),
    )


def handle_disarm(
    *,
    gateway: Any,
    control: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /disarm POST request.

    Returns (status_code, payload).
    """
    gateway.command("DISARM", timeout=1.0)
    control.clear_arm_prepare()
    return 200, build_status_control_payload(
        status=gateway.get_status(),
        control=control.snapshot(),
    )


def handle_estop_latch(
    *,
    gateway: Any,
    control: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /estop/latch POST request.

    Returns (status_code, payload).
    """
    gateway.command("DISARM", timeout=1.0)
    return 200, build_status_control_payload(
        status=gateway.get_status(),
        control=control.latch_estop(),
    )


def handle_estop_reset(
    *,
    gateway: Any,
    control: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /estop/reset POST request.

    Returns (status_code, payload).
    """
    gateway.command("DISARM", timeout=1.0)
    return 200, build_status_control_payload(
        status=gateway.get_status(),
        control=control.reset_estop(),
    )


def handle_arm_precheck(
    *,
    body: Dict[str, Any],
    gateway: Any,
    control: Any,
    prearm_safety: Any,
    run_prearm_hardware_check_fn: Callable[..., Dict[str, Any]],
    report_design_observation_fn: Callable[..., None],
    resolve_action_gates_fn: Callable[..., Dict[str, Any]],
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /arm/precheck POST request.

    Returns (status_code, payload).
    Safety-critical: validates hardware state before allowing arm.
    """
    report = run_prearm_hardware_check_fn(gateway, control, body)
    if bool(report.get("ok", False)):
        prearm = prearm_safety.mark_pass(report)
    else:
        prearm = prearm_safety.require("prearm_failed")

    try:
        report_design_observation_fn(
            session_key=(
                str(body.get("session_key", "")).strip() or "local:prearm"
            ),
            success=bool(report.get("ok", False)),
            source="prearm_check",
            note=(
                str(report.get("summary", "")).strip()
                or str(report.get("error", "")).strip()
            ),
            profile_id=str(body.get("profile_id", "")).strip(),
            profile_label=str(body.get("profile_label", "")).strip(),
            sketch_revision=str(body.get("sketch_revision", "")).strip(),
            test_type="prearm",
        )
    except Exception:
        pass

    payload = build_arm_precheck_payload(
        report=report,
        prearm_safety=prearm,
        action_gates=resolve_action_gates_fn(
            gateway, control, prearm_gate=prearm_safety
        ),
    )
    validate_prearm_precheck_response(payload)
    return (200 if bool(report.get("ok", False)) else 409), payload

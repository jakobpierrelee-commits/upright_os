"""
Arm/disarm route handlers extracted from server.py (Phase C).

These handlers manage arm, disarm, estop, and command operations.
"""
from typing import Any, Callable, Dict, Optional, Tuple

try:
    from app.bridge.clean_misc import (
        build_control_payload,
        build_result_control_payload,
    )
    from app.bridge.clean_safety import build_status_control_payload
except ImportError:
    from clean_misc import (  # type: ignore
        build_control_payload,
        build_result_control_payload,
    )
    from clean_safety import build_status_control_payload  # type: ignore


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

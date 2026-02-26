"""
Calibration route handlers extracted from server.py (Phase C).

These handlers manage calibration, IMU, and config operations.
"""
from typing import Any, Callable, Dict, Tuple

try:
    from app.bridge.clean_misc import (
        build_command_result_payload,
        build_result_control_payload,
    )
    from app.bridge.clean_serial import build_result_status_control_payload
except ImportError:
    from clean_misc import (  # type: ignore
        build_command_result_payload,
        build_result_control_payload,
    )
    from clean_serial import build_result_status_control_payload  # type: ignore


def handle_cal_zero(
    *,
    gateway: Any,
    control: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /cal_zero POST request.

    Returns (status_code, payload).
    """
    res = gateway.command("CAL ZERO", expect_contains="OK CAL ZERO", timeout=4.0)
    return 200, build_command_result_payload(
        result=res,
        status=gateway.get_status(),
        control=control.snapshot(),
    )


def handle_imu_calibrate(
    *,
    gateway: Any,
    control: Any,
    classify_imu_fn: Callable[[str, str], Dict[str, Any]],
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /imu/calibrate POST request.

    Returns (status_code, payload).
    """
    res = gateway.command("IMU CAL", expect_contains="IMU", timeout=8.0)
    outcome = classify_imu_fn(res, "cal")
    if not bool(outcome.get("ok", False)):
        return 409, {
            "ok": False,
            "error": outcome.get("error"),
            "detail": outcome.get("detail"),
            "result": res,
        }
    return 200, build_command_result_payload(
        result=res,
        status=gateway.get_status(),
        control=control.snapshot(),
    )


def handle_imu_load(
    *,
    gateway: Any,
    control: Any,
    classify_imu_fn: Callable[[str, str], Dict[str, Any]],
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /imu/load POST request.

    Returns (status_code, payload).
    """
    res = gateway.command("IMU LOAD", expect_contains="IMU", timeout=4.0)
    outcome = classify_imu_fn(res, "load")
    if not bool(outcome.get("ok", False)):
        return 409, {
            "ok": False,
            "error": outcome.get("error"),
            "detail": outcome.get("detail"),
            "result": res,
        }
    return 200, build_command_result_payload(
        result=res,
        status=gateway.get_status(),
        control=control.snapshot(),
    )


def handle_imu_save(
    *,
    gateway: Any,
    control: Any,
    classify_imu_fn: Callable[[str, str], Dict[str, Any]],
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /imu/save POST request.

    Returns (status_code, payload).
    """
    res = gateway.command("IMU SAVE", expect_contains="IMU", timeout=4.0)
    outcome = classify_imu_fn(res, "save")
    if not bool(outcome.get("ok", False)):
        return 409, {
            "ok": False,
            "error": outcome.get("error"),
            "detail": outcome.get("detail"),
            "result": res,
        }
    return 200, build_command_result_payload(
        result=res,
        status=gateway.get_status(),
        control=control.snapshot(),
    )


def handle_imu_info(
    *,
    gateway: Any,
    control: Any,
    classify_imu_fn: Callable[[str, str], Dict[str, Any]],
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /imu/info POST request.

    Returns (status_code, payload).
    """
    res = gateway.command("IMU INFO", expect_contains="IMU", timeout=4.0)
    outcome = classify_imu_fn(res, "info")
    if not bool(outcome.get("ok", False)):
        return 409, {
            "ok": False,
            "error": outcome.get("error"),
            "detail": outcome.get("detail"),
            "result": res,
        }
    return 200, build_command_result_payload(
        result=res,
        status=gateway.get_status(),
        control=control.snapshot(),
    )


def handle_savecfg(
    *,
    gateway: Any,
    control: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /savecfg POST request.

    Returns (status_code, payload).
    """
    res = gateway.command("SAVECFG", expect_contains="OK SAVECFG", timeout=2.0)
    return 200, build_result_control_payload(result=res, control=control.snapshot())


def handle_loadcfg(
    *,
    gateway: Any,
    control: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /loadcfg POST request.

    Returns (status_code, payload).
    """
    res = gateway.command("LOADCFG", expect_contains="OK LOADCFG", timeout=2.0)
    return 200, build_result_status_control_payload(
        result=res,
        status=gateway.get_status(),
        control=control.snapshot(),
    )


def handle_defaultcfg(
    *,
    gateway: Any,
    control: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /defaultcfg POST request.

    Returns (status_code, payload).
    """
    res = gateway.command("DEFAULTCFG", expect_contains="OK DEFAULTCFG", timeout=2.0)
    return 200, build_result_status_control_payload(
        result=res,
        status=gateway.get_status(),
        control=control.snapshot(),
    )

"""
Commissioning route handlers extracted from server.py (Phase C).

These handlers manage commissioning run and step operations.
"""
from typing import Any, Dict, Optional, Tuple

try:
    from app.bridge.clean_tuning import build_commissioning_run_payload
except ImportError:
    from clean_tuning import build_commissioning_run_payload  # type: ignore


def handle_commissioning_run(
    *,
    body: Dict[str, Any],
    gateway: Any,
    commissioning: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /commissioning/run POST request.

    Returns (status_code, payload).
    """
    if gateway.health().get("connected", False):
        return 409, {
            "ok": False,
            "error": "serial_port_in_use_by_bridge",
            "hint": "Run commissioning_runner.py directly when bridge is stopped, or add step-mode commissioning through the bridge.",
        }

    st = commissioning.run(
        port=body.get("port"),
        baud=body.get("baud"),
        config=body.get("config"),
        out_dir=body.get("out_dir"),
        auto_prompts=bool(body.get("auto_prompts", True)),
    )
    return 200, build_commissioning_run_payload(commissioning=st)


def handle_commissioning_step() -> Tuple[int, Dict[str, Any]]:
    """
    Handle /commissioning/step POST request.

    Returns (status_code, payload).
    """
    return 501, {
        "ok": False,
        "error": "not_implemented",
        "hint": "Use /commissioning/run for now",
    }

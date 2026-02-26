from __future__ import annotations

from typing import Any, Dict


def build_arm_precheck_payload(
    *,
    report: Dict[str, Any],
    prearm_safety: Dict[str, Any],
    action_gates: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "ok": bool(report.get("ok", False)),
        "prearm_check": report,
        "prearm_safety": prearm_safety,
        "action_gates": action_gates,
    }


def build_status_control_payload(
    *, status: Dict[str, Any], control: Dict[str, Any]
) -> Dict[str, Any]:
    return {
        "ok": True,
        "status": status,
        "control": control,
    }

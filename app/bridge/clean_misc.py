from __future__ import annotations

from typing import Any, Dict, List


def build_sketch_payload(*, sketch: str) -> Dict[str, Any]:
    return {"ok": True, "sketch": sketch}


def build_boards_payload(*, boards: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"ok": True, "boards": boards}


def build_firmware_check_payload(*, firmware_check: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "firmware_check": firmware_check}


def build_firmware_result_payload(*, firmware: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "firmware": firmware}


def build_overwatch_payload(*, overwatch: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "overwatch": overwatch}


def build_capabilities_payload(
    *, capabilities: Dict[str, Any], source: str
) -> Dict[str, Any]:
    return {"ok": True, "capabilities": capabilities, "source": source}


def build_design_payload(*, design: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "design": design}


def build_reset_payload(*, reset: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "reset": reset}


def build_targets_payload(*, targets: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"ok": True, "targets": targets}

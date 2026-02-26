from __future__ import annotations

from typing import Any, Dict, List


def build_firmware_status_payload(*, firmware_status: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "firmware": firmware_status}


def build_firmware_artifacts_payload(
    *, firmware_artifacts: List[Dict[str, Any]]
) -> Dict[str, Any]:
    return {"ok": True, "firmware_artifacts": firmware_artifacts}


def build_runtime_manifest_validate_payload(*, check: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ok": bool(check.get("ok", False)),
        "validation": check,
    }


def build_firmware_sketch_folders_payload(
    *, sketch_folders: List[Dict[str, Any]]
) -> Dict[str, Any]:
    return {"ok": True, "sketch_folders": sketch_folders}

from __future__ import annotations

from typing import Any, Dict, List


def build_burst_status_payload(*, burst: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "burst": burst}


def build_commissioning_status_payload(
    *, commissioning: Dict[str, Any]
) -> Dict[str, Any]:
    return {"ok": True, "commissioning": commissioning}


def build_commissioning_artifacts_payload(
    *, artifacts: List[Dict[str, Any]]
) -> Dict[str, Any]:
    return {"ok": True, "artifacts": artifacts}


def build_lines_payload(*, lines: List[str]) -> Dict[str, Any]:
    return {"ok": True, "lines": lines}

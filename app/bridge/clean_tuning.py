from __future__ import annotations

from typing import Any, Dict, List, Optional


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


def build_commissioning_run_payload(
    *, commissioning: Dict[str, Any]
) -> Dict[str, Any]:
    return {"ok": True, "commissioning": commissioning}


def build_tuning_result_payload(
    *,
    result: str,
    snapshot: Dict[str, Any],
    status: Dict[str, Any],
    control: Dict[str, Any],
    preflight_id: Optional[str],
) -> Dict[str, Any]:
    return {
        "ok": True,
        "result": result,
        "snapshot": snapshot,
        "status": status,
        "control": control,
        "preflight_id": preflight_id,
    }


def build_lines_payload(*, lines: List[str]) -> Dict[str, Any]:
    return {"ok": True, "lines": lines}


def build_tuning_recommend_payload(
    *,
    recommendation: Dict[str, Any],
    surrogate: Optional[Dict[str, Any]],
    replay: List[Dict[str, Any]],
    quality_gate: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "ok": True,
        "recommendation": recommendation,
        "surrogate": surrogate,
        "replay": replay,
        "quality_gate": quality_gate,
    }

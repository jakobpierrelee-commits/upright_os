from __future__ import annotations

from typing import Any, Dict, List, Optional


def build_probe_payload(*, probe: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "probe": probe}


def build_compat_probe_payload(*, compat: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "compat": compat}


def build_design_memory_payload(
    *, design_memory: List[Dict[str, Any]]
) -> Dict[str, Any]:
    return {"ok": True, "design_memory": design_memory}


def build_design_memory_best_payload(
    *, best_design: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    return {"ok": True, "best_design": best_design}


def build_tooling_traces_payload(*, traces: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"ok": True, "traces": traces}


def build_tuning_capabilities_payload(
    *, capabilities: Dict[str, Any]
) -> Dict[str, Any]:
    return {"ok": True, "tuning_capabilities": capabilities}

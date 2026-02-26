from __future__ import annotations

from typing import Any, Dict, List


def build_diag_serial_payload(
    *, serial: Dict[str, Any], control: Dict[str, Any]
) -> Dict[str, Any]:
    return {"ok": True, "serial": serial, "control": control}


def build_telemetry_adapters_payload(
    *,
    adapter: Dict[str, Any],
    adapters: Dict[str, Any],
    canonical_fields: List[str],
) -> Dict[str, Any]:
    return {
        "ok": True,
        "adapter": adapter,
        "adapters": adapters,
        "canonical_fields": canonical_fields,
    }


def build_unified_schema_payload(*, schema: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "schema": schema}

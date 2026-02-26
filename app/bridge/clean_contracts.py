from __future__ import annotations

from typing import Any, Dict, List, TypedDict


class PreflightResult(TypedDict):
    id: str
    ok: bool
    dt_ms: int
    limit_ms: int
    expect_tools: bool
    tool_calls: list
    error: str
    reply: str


class PreflightPayload(TypedDict):
    ok: bool
    mode: str
    failures: int
    max_ms: int
    max_ms_tools: int
    results: List[PreflightResult]


def _require_key(d: Dict[str, Any], key: str, typ: type) -> None:
    if key not in d:
        raise ValueError(f"missing_key:{key}")
    if not isinstance(d.get(key), typ):
        raise ValueError(f"invalid_type:{key}")


def validate_firmware_targets_response(payload: Dict[str, Any]) -> None:
    _require_key(payload, "ok", bool)
    _require_key(payload, "targets", dict)
    targets = payload["targets"]
    _require_key(targets, "version", int)
    _require_key(targets, "families", list)
    _require_key(targets, "boards", list)


def validate_prearm_precheck_response(payload: Dict[str, Any]) -> None:
    _require_key(payload, "ok", bool)
    _require_key(payload, "prearm_check", dict)
    _require_key(payload, "prearm_safety", dict)
    _require_key(payload, "action_gates", dict)
    _require_key(payload["prearm_check"], "ok", bool)
    _require_key(payload["prearm_check"], "checks", list)


def validate_clean_preflight_response(payload: Dict[str, Any]) -> None:
    _require_key(payload, "ok", bool)
    _require_key(payload, "mode", str)
    _require_key(payload, "failures", int)
    _require_key(payload, "max_ms", int)
    _require_key(payload, "max_ms_tools", int)
    _require_key(payload, "results", list)
    for idx, row_any in enumerate(payload["results"]):
        if not isinstance(row_any, dict):
            raise ValueError(f"invalid_result_row:{idx}")
        row = row_any
        _require_key(row, "id", str)
        _require_key(row, "ok", bool)
        _require_key(row, "dt_ms", int)
        _require_key(row, "limit_ms", int)
        _require_key(row, "expect_tools", bool)
        _require_key(row, "tool_calls", list)
        _require_key(row, "error", str)
        _require_key(row, "reply", str)

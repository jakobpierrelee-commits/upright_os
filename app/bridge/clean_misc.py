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


def build_picked_payload(*, picked: str) -> Dict[str, Any]:
    return {"ok": True, "picked": picked}


def build_unified_payload(*, unified: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "unified": unified}


def build_docs_pack_payload(*, docs_pack: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "docs_pack": docs_pack}


def build_validation_payload(*, validation: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "validation": validation}


def build_attachment_payload(*, attachment: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "attachment": attachment}


def build_replay_payload(*, replay: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "replay": replay}


def build_sweep_payload(*, sweep: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "sweep": sweep}


def build_profiles_list_payload(*, profiles: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"ok": True, "profiles": profiles}


def build_agent_state_payload(*, agent: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "agent": agent}


def build_action_payload(*, action: str) -> Dict[str, Any]:
    return {"ok": True, "action": action}


def build_result_payload(*, result: str) -> Dict[str, Any]:
    return {"ok": True, "result": result}


def build_result_control_payload(
    *, result: Dict[str, Any], control: Dict[str, Any]
) -> Dict[str, Any]:
    return {"ok": True, "result": result, "control": control}


def build_sketch_write_payload(*, sketch: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "sketch": sketch}


def build_revert_control_payload(
    *, revert: Dict[str, Any], control: Dict[str, Any]
) -> Dict[str, Any]:
    return {"ok": True, "revert": revert, "control": control}


def build_control_payload(*, control: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "control": control}


def build_active_profiles_payload(
    *, active: Dict[str, Any], profiles: List[Dict[str, Any]]
) -> Dict[str, Any]:
    return {"ok": True, "active": active, "profiles": profiles}


def build_snapshots_payload(*, snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"ok": True, "snapshots": snapshots}


def build_attempt_history_payload(
    *, attempts: List[Dict[str, Any]], next_cursor: str, has_more: bool
) -> Dict[str, Any]:
    return {"ok": True, "attempts": attempts, "next_cursor": next_cursor, "has_more": has_more}


def build_tool_metrics_payload(
    *,
    since_hours: float,
    tool_metrics: Dict[str, Any],
    db_stats: Dict[str, Any],
    ts: float,
) -> Dict[str, Any]:
    return {
        "ok": True,
        "since_hours": since_hours,
        "tool_metrics": tool_metrics,
        "db_stats": db_stats,
        "ts": ts,
    }


def build_stats_payload(*, stats: Dict[str, Any], ts: float) -> Dict[str, Any]:
    return {"ok": True, "stats": stats, "ts": ts}


def build_setup_check_payload(
    *, check_key: str, check_result: Dict[str, Any], attempt: Dict[str, Any]
) -> Dict[str, Any]:
    return {"ok": True, check_key: check_result, "attempt": attempt}


def build_capabilities_payload(
    *, capabilities: Dict[str, Any], source: str
) -> Dict[str, Any]:
    return {"ok": True, "capabilities": capabilities, "source": source}


def build_saved_profiles_payload(
    *, saved: Dict[str, Any], profiles: List[Dict[str, Any]]
) -> Dict[str, Any]:
    return {"ok": True, "saved": saved, "profiles": profiles}

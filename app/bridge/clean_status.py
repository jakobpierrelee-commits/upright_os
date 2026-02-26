from __future__ import annotations

from typing import Any, Dict, List


def clean_api_capabilities() -> List[str]:
    return [
        "agent_clean_status_v2",
        "firmware_compile",
        "firmware_upload_guarded",
        "firmware_upload_precheck",
        "runtime_manifest_validate",
        "runtime_manifest_preflight_gate",
        "runtime_manifest_profile_compat",
        "clean_chat_stream",
        "clean_preflight",
        "legacy_exec_gated_default",
    ]


def build_agent_status_payload(
    *,
    mode_state: Dict[str, Any],
    resolved: Dict[str, Any],
    codex_login: Dict[str, Any],
    runtime_exec: Dict[str, Any],
    runtime_model: str,
    runtime_model_allowed: bool,
    runtime_configured: bool,
    serial_health: Dict[str, Any],
    control_snapshot: Dict[str, Any],
    knowledge_context: Dict[str, Any],
    lines: List[str],
) -> Dict[str, Any]:
    use_codex_cli = bool(codex_login.get("logged_in", False))
    return {
        "ok": True,
        "agent": {
            "mode": mode_state.get("mode", "robot_dev"),
            "allowed_modes": mode_state.get("allowed_modes", []),
            "updated_at": mode_state.get("updated_at"),
            "openai_configured": runtime_configured,
            "openai_model": runtime_model,
            "openai_model_allowed": runtime_model_allowed,
            "provider": "codex_cli"
            if use_codex_cli
            else str(resolved.get("provider", "openai")),
            "executor": str(runtime_exec.get("executor", "unknown")),
            "can_execute": bool(runtime_exec.get("can_execute", False)),
            "degraded": bool(runtime_exec.get("degraded", False)),
            "degraded_reason": str(runtime_exec.get("degraded_reason", "")),
            "model_source": "codex_cli"
            if use_codex_cli
            else str(resolved.get("model_source", "")),
            "api_key_source": "codex_login"
            if use_codex_cli
            else str(resolved.get("api_key_source", "")),
            "codex_login": codex_login,
        },
        "knowledge": knowledge_context,
        "health": serial_health,
        "control": control_snapshot,
        "status": dict(serial_health.get("last_status", {})),
        "lines": lines,
    }


def build_health_payload(
    *,
    serial_health: Dict[str, Any],
    control_snapshot: Dict[str, Any],
    prearm_snapshot: Dict[str, Any],
    telemetry_port: int,
    telemetry_enabled: bool,
) -> Dict[str, Any]:
    return {
        "ok": True,
        "health": serial_health,
        "control": control_snapshot,
        "prearm_safety": prearm_snapshot,
        "telemetry_ws": f"ws://127.0.0.1:{telemetry_port}/telemetry",
        "telemetry_enabled": telemetry_enabled,
    }


def build_status_payload(
    *,
    status: Dict[str, Any],
    status_raw: Dict[str, Any],
    telemetry_adapter: Dict[str, Any],
    control_snapshot: Dict[str, Any],
    prearm_snapshot: Dict[str, Any],
    action_gates: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "ok": True,
        "status": status,
        "status_raw": status_raw,
        "telemetry_adapter": telemetry_adapter,
        "control": control_snapshot,
        "prearm_safety": prearm_snapshot,
        "action_gates": action_gates,
    }


def build_clean_status_payload(
    *,
    mode: str,
    codex_login: Dict[str, Any],
    serial_health: Dict[str, Any],
    control_snapshot: Dict[str, Any],
    model: str,
    lines: List[str],
) -> Dict[str, Any]:
    can_chat = bool(codex_login.get("logged_in", False))
    return {
        "ok": True,
        "clean_api": {
            "version": 2,
            "min_ui_version": 2,
            "capabilities": clean_api_capabilities(),
        },
        "agent": {
            "mode": mode,
            "executor": "codex_cli_exec" if can_chat else "blocked",
            "provider": "codex_cli",
            "model": model,
            "can_chat": can_chat,
            "degraded_reason": "" if can_chat else "codex_login_required",
            "codex_login": codex_login,
        },
        "health": serial_health,
        "control": control_snapshot,
        "status": dict(serial_health.get("last_status", {})),
        "lines": lines,
    }

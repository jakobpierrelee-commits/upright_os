import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from clean_status import (
    build_agent_status_payload,
    build_clean_status_payload,
    build_health_payload,
    build_status_payload,
    clean_api_capabilities,
)


def test_clean_api_capabilities_contains_required_flags() -> None:
    caps = clean_api_capabilities()
    assert "agent_clean_status_v2" in caps
    assert "clean_chat_stream" in caps
    assert "clean_preflight" in caps
    assert "legacy_exec_gated_default" in caps


def test_build_agent_status_payload_codex_path() -> None:
    payload = build_agent_status_payload(
        mode_state={"mode": "app_dev", "allowed_modes": ["app_dev"], "updated_at": 123},
        resolved={"provider": "openai", "model_source": "env", "api_key_source": "env"},
        codex_login={"logged_in": True, "available": True},
        runtime_exec={
            "executor": "codex_cli_exec",
            "can_execute": True,
            "degraded": False,
            "degraded_reason": "",
        },
        runtime_model="gpt-5-codex",
        runtime_model_allowed=True,
        runtime_configured=True,
        serial_health={"last_status": {"mode": "SAFE_IDLE"}},
        control_snapshot={"arm_prepared": False},
        knowledge_context={"facts": []},
        lines=["STATUS mode=SAFE_IDLE"],
    )
    assert payload["ok"] is True
    assert payload["agent"]["provider"] == "codex_cli"
    assert payload["agent"]["api_key_source"] == "codex_login"
    assert payload["status"]["mode"] == "SAFE_IDLE"


def test_build_agent_status_payload_openai_path() -> None:
    payload = build_agent_status_payload(
        mode_state={
            "mode": "robot_dev",
            "allowed_modes": ["robot_dev"],
            "updated_at": 456,
        },
        resolved={
            "provider": "openai",
            "model_source": "user",
            "api_key_source": "user",
        },
        codex_login={"logged_in": False, "available": True},
        runtime_exec={
            "executor": "openai_tools",
            "can_execute": True,
            "degraded": False,
            "degraded_reason": "",
        },
        runtime_model="gpt-5-mini",
        runtime_model_allowed=True,
        runtime_configured=True,
        serial_health={"last_status": {}},
        control_snapshot={},
        knowledge_context={},
        lines=[],
    )
    assert payload["agent"]["provider"] == "openai"
    assert payload["agent"]["model_source"] == "user"
    assert payload["agent"]["api_key_source"] == "user"


def test_build_clean_status_payload_blocked_when_not_logged_in() -> None:
    payload = build_clean_status_payload(
        mode="app_dev",
        codex_login={"logged_in": False},
        serial_health={"last_status": {"mode": "UNKNOWN"}},
        control_snapshot={"arm_prepared": False},
        model="gpt-5-codex",
        lines=[],
    )
    assert payload["ok"] is True
    assert payload["agent"]["executor"] == "blocked"
    assert payload["agent"]["degraded_reason"] == "codex_login_required"
    assert payload["clean_api"]["version"] == 2


def test_build_health_payload_shape() -> None:
    payload = build_health_payload(
        serial_health={"connected": True},
        control_snapshot={"armed": False},
        prearm_snapshot={"ok": True},
        telemetry_port=8788,
        telemetry_enabled=True,
    )
    assert payload["ok"] is True
    assert payload["health"]["connected"] is True
    assert payload["control"]["armed"] is False
    assert payload["prearm_safety"]["ok"] is True
    assert payload["telemetry_ws"].endswith(":8788/telemetry")
    assert payload["telemetry_enabled"] is True


def test_build_status_payload_shape() -> None:
    payload = build_status_payload(
        status={"mode": "SAFE_IDLE"},
        status_raw={"mode": "SAFE_IDLE", "encL": 10},
        telemetry_adapter={"id": "generic_v1"},
        control_snapshot={"arm_prepared": False},
        prearm_snapshot={"ok": True},
        action_gates={"can_arm": True},
    )
    assert payload["ok"] is True
    assert payload["status"]["mode"] == "SAFE_IDLE"
    assert payload["status_raw"]["encL"] == 10
    assert payload["telemetry_adapter"]["id"] == "generic_v1"
    assert payload["control"]["arm_prepared"] is False
    assert payload["prearm_safety"]["ok"] is True
    assert payload["action_gates"]["can_arm"] is True

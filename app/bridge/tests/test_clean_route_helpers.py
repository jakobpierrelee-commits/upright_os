import pathlib
import sys
from typing import Any

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from clean_route_helpers import (
    build_clean_agent_context,
    build_clean_system_prompt,
    run_clean_auto_tools,
)


class _Gateway:
    def health(self) -> dict[str, Any]:
        return {"last_status": {"mode": "SAFE_IDLE", "ang": 0.1, "out": 0.0}}


class _Firmware:
    def status(self) -> dict[str, Any]:
        return {"state": "idle", "phase": "verify", "running": False, "log_tail": []}

    def compile(self, **kwargs: Any) -> dict[str, Any]:
        return {"state": "done", "phase": "compile", "returncode": 0}


class _SetupAttempts:
    def list_recent(self, limit: int = 4) -> list[dict[str, Any]]:
        return [
            {"test_type": "compat", "status": "pass", "result": {"failure_summary": ""}}
        ]


class _AI:
    def history(self, session_key: str, thread_id: str | None) -> list[dict[str, str]]:
        return [{"role": "assistant", "text": "fact"}]


class _MissionMemory:
    def __init__(self) -> None:
        self.data: dict[str, Any] = {}

    def upsert(self, session_key: str, facts: dict[str, Any], source: str = "") -> None:
        self.data = facts

    def get(self, session_key: str) -> dict[str, Any]:
        return self.data


class _Knowledge:
    def context(self) -> dict[str, Any]:
        return {"k": 1}


class _ConfigHistory:
    def list_snapshots(self, limit: int = 6) -> list[dict[str, Any]]:
        return []


class _Control:
    def snapshot(self) -> dict[str, Any]:
        return {"armed": False}


def test_run_clean_auto_tools_triggers_tagged_tools() -> None:
    calls = run_clean_auto_tools(
        message="[tool:connect_probe] [tool:compat_probe] [tool:compile_profiled_runtime_v1]",
        gateway=_Gateway(),
        firmware=_Firmware(),
        repo_root=pathlib.Path("."),
        default_sketch_path_fn=lambda repo_root, firmware: "app/bridge/firmware.ino",
        default_fqbn_fn=lambda: "arduino:avr:nano",
        run_connect_probe_fn=lambda gateway: {"ok": True, "confidence_pct": 97},
        run_compat_probe_fn=lambda gateway: {
            "ok": True,
            "missing_fields": [],
            "missing_commands": [],
        },
    )
    names = [c.get("name") for c in calls]
    assert "connect_probe" in names
    assert "compat_probe" in names
    assert "firmware_compile" in names


def test_build_clean_agent_context_includes_facts_and_attachments() -> None:
    mission = _MissionMemory()
    best_known = {"design_id": "design_abc123", "score": 12.0}
    ctx = build_clean_agent_context(
        mode="app_dev",
        session_key="local:clean:app_dev",
        thread_id="t1",
        attachments=[{"name": "x.txt"}],
        clean_tool_calls=[{"name": "connect_probe"}],
        gateway=_Gateway(),
        firmware=_Firmware(),
        setup_attempt_history=_SetupAttempts(),
        ai=_AI(),
        extract_mission_facts_fn=lambda history: {"objective": "balance"},
        mission_memory=mission,
        knowledge=_Knowledge(),
        config_history=_ConfigHistory(),
        control=_Control(),
        assistant_capabilities_context_fn=lambda **kwargs: {"capabilities": []},
        best_known_design=best_known,
    )
    assert ctx["mission_mode"] == "app_dev"
    assert ctx["mission_facts"]["objective"] == "balance"
    assert ctx["attachments"][0]["name"] == "x.txt"
    assert ctx["clean_tool_calls"][0]["name"] == "connect_probe"
    assert ctx["best_known_design"]["design_id"] == "design_abc123"


def test_build_clean_system_prompt_includes_mode_prompt() -> None:
    out = build_clean_system_prompt(
        mode="robot_dev",
        agent_mode_system_prompt_fn=lambda mode: f"MODE:{mode}",
    )
    assert "UpRight.os clean console" in out
    assert "MODE:robot_dev" in out

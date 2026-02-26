import pathlib
import sys
from typing import Any

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from clean_contracts import validate_clean_preflight_response
from clean_preflight import run_clean_preflight


class _AIStub:
    def __init__(self) -> None:
        self.calls = 0

    def create_thread(self, session_key: str, title: str) -> dict[str, str]:
        return {"id": "t-clean"}

    def chat_codex_cli(self, **kwargs: Any) -> dict[str, str]:
        self.calls += 1
        return {"thread_id": "t-clean", "answer": "ok"}


def _build_context(**kwargs: Any) -> dict[str, str]:
    return {"ctx": "ok"}


def _system_prompt_for_mode(mode: str) -> str:
    return f"mode={mode}"


def _normalize_reply(prompt: str, reply: str) -> str:
    return reply


def test_run_clean_preflight_manifest_gate_fail_emits_done() -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    payload = run_clean_preflight(
        mode="app_dev",
        max_ms=45000,
        max_ms_tools=120000,
        gate_only=False,
        with_compile=False,
        model="gpt-5-codex",
        clean_timeout_s=120,
        manifest_gate={"ok": False, "errors": ["missing_manifest"]},
        compat_gate={"ok": True, "errors": []},
        active_profile_id="p1",
        ai=_AIStub(),
        run_auto_tools=lambda **kwargs: [],
        build_context=_build_context,
        system_prompt_for_mode=_system_prompt_for_mode,
        normalize_reply_for_prompt=_normalize_reply,
        validate_preflight_payload=validate_clean_preflight_response,
        emit=lambda name, body: events.append((name, body)),
    )
    assert payload["ok"] is False
    assert payload["results"][0]["id"] == "manifest_gate"
    assert [name for (name, _) in events] == ["check_done", "done"]


def test_run_clean_preflight_gate_only_success() -> None:
    ai = _AIStub()
    payload = run_clean_preflight(
        mode="app_dev",
        max_ms=45000,
        max_ms_tools=120000,
        gate_only=True,
        with_compile=False,
        model="gpt-5-codex",
        clean_timeout_s=120,
        manifest_gate={"ok": True, "errors": []},
        compat_gate={"ok": True, "errors": []},
        active_profile_id="p1",
        ai=ai,
        run_auto_tools=lambda **kwargs: [],
        build_context=_build_context,
        system_prompt_for_mode=_system_prompt_for_mode,
        normalize_reply_for_prompt=_normalize_reply,
        validate_preflight_payload=validate_clean_preflight_response,
    )
    assert payload["ok"] is True
    assert payload["gate"]["gate_only"] is True
    assert payload["results"][0]["id"] == "manifest_gate"
    assert ai.calls == 0


def test_run_clean_preflight_full_flow_emits_progress() -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    tool_prompts: list[str] = []
    ai = _AIStub()

    def _run_auto_tools(**kwargs: Any) -> list[dict[str, Any]]:
        message = str(kwargs.get("message", ""))
        tool_prompts.append(message)
        lower = message.lower()
        if "connect_probe" in lower:
            return [
                {
                    "name": "connect_probe",
                    "result": {"ok": True, "data": {"ok": True, "confidence_pct": 97}},
                }
            ]
        if "compat_probe" in lower:
            return [
                {
                    "name": "compat_probe",
                    "result": {
                        "ok": True,
                        "data": {
                            "ok": True,
                            "missing_fields": [],
                            "missing_commands": [],
                        },
                    },
                }
            ]
        return [
            {
                "name": "firmware_compile",
                "result": {"ok": True, "data": {"phase": "compile", "returncode": 0}},
            }
        ]

    payload = run_clean_preflight(
        mode="app_dev",
        max_ms=45000,
        max_ms_tools=120000,
        gate_only=False,
        with_compile=True,
        model="gpt-5-codex",
        clean_timeout_s=120,
        manifest_gate={"ok": True, "errors": []},
        compat_gate={"ok": True, "errors": []},
        active_profile_id="p1",
        ai=ai,
        run_auto_tools=_run_auto_tools,
        build_context=_build_context,
        system_prompt_for_mode=_system_prompt_for_mode,
        normalize_reply_for_prompt=_normalize_reply,
        validate_preflight_payload=validate_clean_preflight_response,
        emit=lambda name, body: events.append((name, body)),
    )
    assert payload["ok"] is True
    assert payload["failures"] == 0
    assert len(payload["results"]) == 6
    assert ai.calls == 0
    assert len(tool_prompts) == 3
    event_names = [name for (name, _) in events]
    assert event_names.count("check_start") == 6
    assert event_names.count("check_done") == 6
    assert event_names[-1] == "done"

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional


def clean_tool_call(
    *,
    name: str,
    arguments: Dict[str, Any],
    ok: bool,
    data: Optional[Dict[str, Any]] = None,
    error: str = "",
    started_ms: int = 0,
) -> Dict[str, Any]:
    ended_ms = int(time.time() * 1000)
    dt = max(0, ended_ms - int(started_ms or ended_ms))
    return {
        "name": name,
        "arguments": arguments,
        "result": {
            "ok": bool(ok),
            "data": data or {},
            "error": str(error or ""),
            "execution_time_ms": dt,
        },
    }


def run_clean_auto_tools(
    *,
    message: str,
    gateway: Any,
    firmware: Any,
    repo_root: Any,
    default_sketch_path_fn: Callable[[Any, Any], str],
    default_fqbn_fn: Callable[[], str],
    run_connect_probe_fn: Callable[[Any], Dict[str, Any]],
    run_compat_probe_fn: Callable[[Any], Dict[str, Any]],
) -> list[Dict[str, Any]]:
    txt = str(message or "").lower()
    calls: list[Dict[str, Any]] = []
    wants_connect = "[tool:connect_probe]" in txt
    wants_compat = "[tool:compat_probe]" in txt
    wants_compile = "[tool:compile_profiled_runtime_v1]" in txt

    if wants_connect:
        t0 = int(time.time() * 1000)
        try:
            rep = run_connect_probe_fn(gateway)
            calls.append(
                clean_tool_call(
                    name="connect_probe",
                    arguments={},
                    ok=True,
                    data={
                        "ok": bool(rep.get("ok", False)),
                        "confidence_pct": int(rep.get("confidence_pct", 0) or 0),
                    },
                    started_ms=t0,
                )
            )
        except Exception as exc:
            calls.append(
                clean_tool_call(
                    name="connect_probe",
                    arguments={},
                    ok=False,
                    error=str(exc),
                    started_ms=t0,
                )
            )

    if wants_compat:
        t0 = int(time.time() * 1000)
        try:
            rep = run_compat_probe_fn(gateway)
            calls.append(
                clean_tool_call(
                    name="compat_probe",
                    arguments={},
                    ok=True,
                    data={
                        "ok": bool(rep.get("ok", False)),
                        "missing_fields": list(rep.get("missing_fields", [])[:12]),
                        "missing_commands": list(rep.get("missing_commands", [])[:12]),
                    },
                    started_ms=t0,
                )
            )
        except Exception as exc:
            calls.append(
                clean_tool_call(
                    name="compat_probe",
                    arguments={},
                    ok=False,
                    error=str(exc),
                    started_ms=t0,
                )
            )

    if wants_compile:
        t0 = int(time.time() * 1000)
        sketch = default_sketch_path_fn(repo_root, firmware)
        fqbn = default_fqbn_fn()
        try:
            st = firmware.compile(sketch=sketch, fqbn=fqbn)
            calls.append(
                clean_tool_call(
                    name="firmware_compile",
                    arguments={"sketch": sketch, "fqbn": fqbn},
                    ok=True,
                    data={
                        "state": str(st.get("state", "")),
                        "phase": str(st.get("phase", "")),
                        "returncode": st.get("returncode"),
                    },
                    started_ms=t0,
                )
            )
        except Exception as exc:
            calls.append(
                clean_tool_call(
                    name="firmware_compile",
                    arguments={"sketch": sketch, "fqbn": fqbn},
                    ok=False,
                    error=str(exc),
                    started_ms=t0,
                )
            )

    return calls


def build_clean_agent_context(
    *,
    mode: str,
    session_key: str,
    thread_id: Optional[str],
    attachments: Optional[list[Dict[str, Any]]] = None,
    clean_tool_calls: Optional[list[Dict[str, Any]]] = None,
    gateway: Any,
    firmware: Any,
    setup_attempt_history: Any,
    ai: Any,
    extract_mission_facts_fn: Callable[[list[Dict[str, Any]]], Dict[str, Any]],
    mission_memory: Any,
    knowledge: Any,
    config_history: Any,
    control: Any,
    assistant_capabilities_context_fn: Callable[..., Dict[str, Any]],
    best_known_design: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    serial_h = gateway.health()
    cached_status = dict(serial_h.get("last_status", {}))
    fw = firmware.status()
    fw_tail = list(fw.get("log_tail", [])[-8:]) if isinstance(fw, dict) else []
    recent_attempts_raw = setup_attempt_history.list_recent(limit=4)
    recent_attempts: list[Dict[str, Any]] = []
    for node in recent_attempts_raw:
        if not isinstance(node, dict):
            continue
        result = node.get("result") if isinstance(node.get("result"), dict) else {}
        recent_attempts.append(
            {
                "test_type": str(node.get("test_type", "")),
                "status": str(node.get("status", "")),
                "created_at": node.get("created_at"),
                "failure_summary": str(result.get("failure_summary", "")),
            }
        )

    telemetry_summary = {
        "mode": str(cached_status.get("mode", "UNKNOWN")),
        "angle": str(cached_status.get("ang", "n/a")),
        "raw": str(cached_status.get("raw", "n/a")),
        "gyro": str(
            cached_status.get(
                "gyro",
                cached_status.get("gyr", cached_status.get("gx", "n/a")),
            )
        ),
        "output": str(cached_status.get("out", "n/a")),
        "feed_present": bool(cached_status),
    }

    try:
        full_history = ai.history(session_key, thread_id) if thread_id else []
    except Exception:
        full_history = []
    extracted_facts = extract_mission_facts_fn(full_history)
    if extracted_facts:
        mission_memory.upsert(
            session_key, extracted_facts, source="clean_thread_history"
        )
    mission_facts = mission_memory.get(session_key)

    ctx: Dict[str, Any] = {
        "mission_mode": mode,
        "status": cached_status,
        "status_source": "gateway.health.last_status_cached",
        "serial_health": serial_h,
        "control": control.snapshot(),
        "firmware": fw,
        "telemetry_summary": telemetry_summary,
        "recent_firmware_outcome": {
            "state": str(fw.get("state", "")) if isinstance(fw, dict) else "",
            "phase": str(fw.get("phase", "")) if isinstance(fw, dict) else "",
            "running": bool(fw.get("running", False))
            if isinstance(fw, dict)
            else False,
            "returncode": fw.get("returncode") if isinstance(fw, dict) else None,
            "last_cmd": list(fw.get("last_cmd", [])[-8:])
            if isinstance(fw, dict)
            else [],
            "log_tail": fw_tail,
        },
        "recent_setup_attempts": recent_attempts,
        "assistant_knowledge": knowledge.context(),
        "config_snapshots": config_history.list_snapshots(limit=6),
        "assistant_capabilities": assistant_capabilities_context_fn(allow_apply=False),
    }
    if mission_facts:
        ctx["mission_facts"] = mission_facts
    if attachments:
        ctx["attachments"] = attachments
    if clean_tool_calls:
        ctx["clean_tool_calls"] = clean_tool_calls
    if best_known_design:
        ctx["best_known_design"] = dict(best_known_design)
    return ctx


def build_clean_system_prompt(
    *,
    mode: str,
    agent_mode_system_prompt_fn: Callable[[str], str],
) -> str:
    return (
        "You are Codex for UpRight.os clean console. "
        "Be concise, practical, and evidence-driven. "
        "Use mission_facts, telemetry_summary, recent_firmware_outcome, and recent_setup_attempts when relevant. "
        f"{agent_mode_system_prompt_fn(mode)}"
    )

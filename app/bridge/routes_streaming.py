"""
Streaming route handlers for server.py.

Extracts SSE streaming logic to reduce Handler class size.
"""

import json
import os
import threading
from typing import Any, Callable, Dict, Optional, Tuple


def build_agent_chat_stream_context(
    *,
    body: Dict[str, Any],
    mode: str,
    gateway: Any,
    control: Any,
    firmware: Any,
    commissioning: Any,
    host_capture: Any,
    config_history: Any,
    knowledge: Any,
    burst_status_fn: Any,
    commissioning_ai_context_fn: Any,
    host_capture_ai_context_fn: Any,
    assistant_capabilities_context_fn: Any,
    sanitize_attachments_fn: Any,
) -> Dict[str, Any]:
    """Build context dict for agent chat streaming."""
    serial_h = gateway.health()
    cached_status = dict(serial_h.get("last_status", {}))
    attachments = sanitize_attachments_fn(body.get("attachments"))
    ctx = {
        "mission_mode": mode,
        "status": cached_status,
        "status_source": "gateway.health.last_status_cached",
        "serial_health": serial_h,
        "control": control.snapshot(),
        "firmware": firmware.status(),
        "commissioning": commissioning_ai_context_fn(commissioning),
        "host_capture": host_capture_ai_context_fn(host_capture),
        "burst": burst_status_fn(),
        "config_snapshots": config_history.list_snapshots(limit=8),
        "assistant_knowledge": knowledge.context(),
        "assistant_capabilities": assistant_capabilities_context_fn(allow_apply=False),
    }
    if attachments:
        ctx["attachments"] = attachments
    return ctx


def resolve_agent_stream_runtime(
    *,
    body: Dict[str, Any],
    mode: str,
    auth: Any,
    me: Optional[Dict[str, Any]],
    ai: Any,
    provider_router: Any,
    codex_agent: Any,
    codex_cli_login_status_fn: Any,
    agent_choose_executor_fn: Any,
    agent_resolve_model_fn: Any,
    agent_model_allowed_fn: Any,
    env_model: str,
) -> Tuple[Optional[Tuple[int, Dict[str, Any]]], Dict[str, Any]]:
    """
    Resolve runtime for agent chat streaming.
    
    Returns (error_response, runtime_info) where error_response is None if OK.
    """
    user_creds = (
        auth.get_openai_key(int(me["id"]))
        if me and isinstance(me.get("id"), int)
        else None
    )
    resolved = provider_router.resolve_agent_runtime(
        mode=mode,
        requested_api_key=str(body.get("api_key", "")).strip() or None,
        requested_model=str(body.get("model", "")).strip() or None,
        user_creds=user_creds,
        env_api_key=ai.default_api_key,
        env_model=env_model,
    )
    codex_login = codex_cli_login_status_fn()
    api_key = str(resolved.get("api_key", "")).strip()
    use_codex_cli = bool(codex_login.get("logged_in", False))
    enable_tools = bool(body.get("enable_tools", True))
    runtime_exec = agent_choose_executor_fn(
        mode=mode,
        enable_tools=enable_tools,
        has_api_key=bool(api_key),
        codex_logged_in=use_codex_cli,
        codex_agent_available=bool(codex_agent is not None),
    )
    executor = str(runtime_exec.get("executor", "blocked"))
    model = agent_resolve_model_fn(
        mode,
        str(resolved.get("model", "")),
        prefer_codex=use_codex_cli,
    )
    
    # Check for blocked executor
    if executor == "blocked":
        return (
            (403, {
                "ok": False,
                "error": str(runtime_exec.get("degraded_reason", "runtime_blocked")),
                "executor": executor,
                "can_execute": False,
            }),
            {},
        )
    
    # Check model allowed
    if (not use_codex_cli) and (not agent_model_allowed_fn(model)):
        return (
            (409, {
                "ok": False,
                "error": "agent_model_not_allowed",
                "required_substring": ",".join(resolved.get("allowed_model_substrings", [])),
                "resolved_model": model,
            }),
            {},
        )
    
    return None, {
        "api_key": api_key,
        "model": model,
        "executor": executor,
        "use_codex_cli": use_codex_cli,
        "resolved": resolved,
    }


def make_inline_sse_emitter(wfile: Any) -> Callable[[str, Dict[str, Any]], None]:
    """Create an inline SSE emitter function."""
    def send_evt(name: str, payload_obj: Dict[str, Any]) -> None:
        blob = (
            f"event: {name}\ndata: {json.dumps(payload_obj, ensure_ascii=True)}\n\n"
        ).encode("utf-8")
        wfile.write(blob)
        wfile.flush()
    return send_evt


def apply_sse_response_headers(handler: Any) -> None:
    """Apply SSE response headers to handler."""
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Connection", "keep-alive")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header(
        "Access-Control-Allow-Headers",
        "Content-Type, Authorization, X-Session-Token",
    )
    handler.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    handler.end_headers()


def run_agent_chat_stream_executor(
    *,
    executor: str,
    msg: str,
    mode: str,
    model: str,
    api_key: str,
    ctx: Dict[str, Any],
    session_key: str,
    thread_id: Optional[str],
    body: Dict[str, Any],
    ai: Any,
    codex_agent: Any,
    firmware: Any,
    mode_state: Dict[str, Any],
    agent_mode_system_prompt_fn: Any,
    normalize_reply_for_prompt_fn: Any,
    build_agent_chat_reply_payload_fn: Any,
    send_evt: Callable[[str, Dict[str, Any]], None],
) -> None:
    """Execute the appropriate agent chat streaming executor."""
    if executor == "openai_tools":
        fw_status = firmware.status()
        fw_defaults = fw_status.get("defaults", {}) if isinstance(fw_status, dict) else {}
        active_sketch = str(
            body.get("sketch_path") or fw_status.get("sketch_path", "") or fw_defaults.get("sketch", "")
        )
        board_fqbn = str(
            body.get("board") or fw_status.get("board", "") or fw_defaults.get("fqbn", "arduino:avr:nano")
        )
        port = str(
            body.get("port") or fw_status.get("port", "") or fw_defaults.get("port", "")
        )
        prior_history = ai.history(session_key, thread_id) if thread_id else []
        tool_out = codex_agent.chat_with_tools(
            message=msg,
            context=ctx,
            api_key=api_key,
            model=model,
            system_prompt=agent_mode_system_prompt_fn(mode),
            enable_tools=True,
            active_sketch_path=active_sketch or None,
            active_robot_id=str(body.get("robot_id", "default")),
            board_fqbn=board_fqbn,
            port=port,
            conversation_history=prior_history,
        )
        answer = str(tool_out.get("answer", "")).strip() or "(no output)"
        send_evt("delta", {"text": answer})
        tid = ai._append(session_key, "user", msg, thread_id=thread_id)
        ai._append(session_key, "assistant", answer, thread_id=tid)
        hist = ai.history(session_key, tid)[-80:]
        send_evt(
            "done",
            build_agent_chat_reply_payload_fn(
                agent=mode_state,
                reply=normalize_reply_for_prompt_fn(msg, answer),
                thread_id=tid,
                history=hist,
                threads=ai.list_threads(session_key),
                tool_calls=tool_out.get("tool_calls", []),
                iterations=int(tool_out.get("iterations", 1) or 1),
                provider="openai_tools",
                executor=executor,
            ),
        )
        return

    if executor == "codex_cli_exec":
        out = ai.chat_codex_cli(
            message=msg,
            context=ctx,
            session_key=session_key,
            model=model,
            thread_id=thread_id,
            system_prompt=agent_mode_system_prompt_fn(mode),
        )
        answer = str(out.get("answer", "")).strip() or "(no output)"
        send_evt("delta", {"text": answer})
        tid = str(out.get("thread_id", "")).strip() or None
        hist = ai.history(session_key, tid)[-80:] if tid else []
        send_evt(
            "done",
            build_agent_chat_reply_payload_fn(
                agent=mode_state,
                reply=normalize_reply_for_prompt_fn(msg, answer),
                thread_id=tid,
                history=hist,
                threads=ai.list_threads(session_key),
                tool_calls=[],
                iterations=1,
                provider="codex_cli",
                executor=executor,
            ),
        )
        return

    # Default: openai_chat
    out = ai.chat_stream(
        message=msg,
        context=ctx,
        session_key=session_key,
        api_key=api_key,
        model=model,
        on_delta=lambda txt: send_evt("delta", {"text": txt}),
        thread_id=thread_id,
        system_prompt=agent_mode_system_prompt_fn(mode),
    )
    tid = str(out.get("thread_id", "")).strip() or None
    hist = ai.history(session_key, tid)[-80:] if tid else []
    send_evt(
        "done",
        build_agent_chat_reply_payload_fn(
            agent=mode_state,
            reply=normalize_reply_for_prompt_fn(
                msg, str(out.get("answer", "")).strip() or "(no output)"
            ),
            thread_id=tid,
            history=hist,
            threads=ai.list_threads(session_key),
            tool_calls=[],
            iterations=1,
            provider="openai",
            executor="openai_chat",
        ),
    )

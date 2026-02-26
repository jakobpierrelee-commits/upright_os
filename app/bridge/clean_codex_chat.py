from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple


EmitEvent = Callable[[str, Dict[str, Any]], None]


def run_clean_chat(
    *,
    msg: str,
    mode: str,
    model: str,
    clean_timeout_s: int,
    session_key: str,
    thread_id: Optional[str],
    attachments: list[Dict[str, Any]],
    auto_tools: bool,
    ai: Any,
    run_auto_tools: Callable[..., list[Dict[str, Any]]],
    build_context: Callable[..., Dict[str, Any]],
    system_prompt_for_mode: Callable[[str], str],
    normalize_reply_for_prompt: Callable[[str, str], str],
) -> Tuple[int, Dict[str, Any]]:
    tool_calls: list[Dict[str, Any]] = []
    if auto_tools:
        tool_calls = run_auto_tools(message=msg, model=model)
    ctx = build_context(
        mode=mode,
        session_key=session_key,
        thread_id=thread_id,
        attachments=attachments,
        clean_tool_calls=tool_calls,
    )
    try:
        out = ai.chat_codex_cli(
            message=msg,
            context=ctx,
            session_key=session_key,
            model=model,
            thread_id=thread_id,
            system_prompt=system_prompt_for_mode(mode),
            timeout_s_override=max(30, clean_timeout_s),
        )
    except RuntimeError as exc:
        emsg = str(exc)
        lower = emsg.lower()
        if emsg.startswith("codex_cli_timeout:"):
            return (
                504,
                {
                    "ok": False,
                    "error": emsg,
                    "error_kind": "timeout",
                    "executor": "codex_cli_exec",
                    "tool_calls": tool_calls,
                },
            )
        if ("usage limit" in lower) or ("purchase more credits" in lower):
            return (
                429,
                {
                    "ok": False,
                    "error": "codex_usage_limited",
                    "detail": emsg[-420:],
                    "error_kind": "quota",
                    "executor": "codex_cli_exec",
                    "tool_calls": tool_calls,
                },
            )
        return (
            502,
            {
                "ok": False,
                "error": emsg,
                "error_kind": "upstream",
                "executor": "codex_cli_exec",
                "tool_calls": tool_calls,
            },
        )
    tid = str(out.get("thread_id", "")).strip() or None
    hist = ai.history(session_key, tid)[-80:] if tid else []
    return (
        200,
        {
            "ok": True,
            "mode": mode,
            "reply": normalize_reply_for_prompt(
                msg, str(out.get("answer", "(no output)"))
            ),
            "thread_id": tid,
            "history": hist,
            "threads": ai.list_threads(session_key),
            "provider": "codex_cli",
            "executor": "codex_cli_exec",
            "tool_calls": tool_calls,
        },
    )


def run_clean_chat_stream(
    *,
    msg: str,
    mode: str,
    model: str,
    clean_timeout_s: int,
    session_key: str,
    thread_id: Optional[str],
    attachments: list[Dict[str, Any]],
    auto_tools: bool,
    ai: Any,
    run_auto_tools: Callable[..., list[Dict[str, Any]]],
    build_context: Callable[..., Dict[str, Any]],
    system_prompt_for_mode: Callable[[str], str],
    normalize_reply_for_prompt: Callable[[str, str], str],
    emit: EmitEvent,
    is_disconnected: Callable[[], bool],
    cancel_event: Any,
) -> None:
    tool_calls: list[Dict[str, Any]] = []
    if auto_tools:
        tool_calls = run_auto_tools(message=msg, model=model)
    ctx = build_context(
        mode=mode,
        session_key=session_key,
        thread_id=thread_id,
        attachments=attachments,
        clean_tool_calls=tool_calls,
    )
    try:
        out = ai.chat_codex_cli_stream(
            message=msg,
            context=ctx,
            session_key=session_key,
            model=model,
            thread_id=thread_id,
            system_prompt=system_prompt_for_mode(mode),
            timeout_s_override=max(30, clean_timeout_s),
            cancel_event=cancel_event,
            on_progress=lambda line: emit("progress", {"line": line}),
            on_delta=lambda txt: emit("delta", {"text": txt}),
        )
        if is_disconnected():
            return
        tid = str(out.get("thread_id", "")).strip() or None
        hist = ai.history(session_key, tid)[-80:] if tid else []
        emit(
            "done",
            {
                "ok": True,
                "mode": mode,
                "reply": normalize_reply_for_prompt(
                    msg, str(out.get("answer", "(no output)"))
                ),
                "thread_id": tid,
                "history": hist,
                "threads": ai.list_threads(session_key),
                "provider": "codex_cli",
                "executor": "codex_cli_exec",
                "tool_calls": tool_calls,
            },
        )
    except Exception as exc:
        if is_disconnected():
            return
        emit(
            "error",
            {
                "ok": False,
                "error": str(exc),
                "executor": "codex_cli_exec",
                "tool_calls": tool_calls,
            },
        )

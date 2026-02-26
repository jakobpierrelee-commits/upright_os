from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


def clean_session_key(mode: str) -> str:
    return f"local:clean:{str(mode or 'app_dev').strip() or 'app_dev'}"


def handle_clean_threads_get(
    *,
    mode: str,
    ai: Any,
    codex_logged_in: bool,
    model: str,
) -> Dict[str, Any]:
    session_key = clean_session_key(mode)
    return {
        "ok": True,
        "mode": mode,
        "threads": ai.list_threads(session_key),
        "ai": ai.status(
            configured=bool(codex_logged_in),
            model=str(model),
            session_key=session_key,
        ),
    }


def handle_clean_thread_new(
    *,
    mode: str,
    title: Optional[str],
    ai: Any,
) -> Dict[str, Any]:
    session_key = clean_session_key(mode)
    thread = ai.create_thread(session_key, title)
    return {
        "ok": True,
        "mode": mode,
        "thread": thread,
        "threads": ai.list_threads(session_key),
        "history": ai.history(session_key, str(thread.get("id")))[-80:],
    }


def handle_clean_thread_select(
    *,
    mode: str,
    thread_id: str,
    ai: Any,
) -> Tuple[int, Dict[str, Any]]:
    if not str(thread_id or "").strip():
        return 400, {"ok": False, "error": "thread_id_required"}
    session_key = clean_session_key(mode)
    try:
        thread = ai.select_thread(session_key, str(thread_id).strip())
    except RuntimeError as exc:
        if str(exc) == "thread_not_found":
            return 404, {"ok": False, "error": "thread_not_found"}
        raise
    return (
        200,
        {
            "ok": True,
            "mode": mode,
            "thread": thread,
            "threads": ai.list_threads(session_key),
            "history": ai.history(session_key, str(thread_id).strip())[-80:],
        },
    )

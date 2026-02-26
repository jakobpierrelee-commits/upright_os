"""
AI/agent route handlers extracted from server.py (Phase B, Slice 5).

These handlers manage AI threads, profiles, and authentication-gated operations.
"""
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from app.bridge.clean_ai import (
        build_ai_thread_payload,
        build_ai_profiles_payload,
    )
except ImportError:
    from clean_ai import (  # type: ignore
        build_ai_thread_payload,
        build_ai_profiles_payload,
    )


def handle_ai_thread_new(
    *,
    body: Dict[str, Any],
    me: Dict[str, Any],
    ai: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /ai/thread/new POST request.

    Returns (status_code, payload).
    Requires authenticated user (me).
    """
    skey = f"user:{me['id']}"
    created = ai.create_thread(skey, title=body.get("title"))
    st = ai.status(
        configured=bool(me.get("openai_configured")),
        model=str(me.get("openai_model") or "gpt-5-codex"),
        session_key=skey,
    )
    return 200, build_ai_thread_payload(
        thread=created,
        threads=ai.list_threads(skey),
        ai_status=st,
        history=ai.history(skey, st.get("active_thread_id"))[-80:],
    )


def handle_ai_thread_select(
    *,
    body: Dict[str, Any],
    me: Dict[str, Any],
    ai: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /ai/thread/select POST request.

    Returns (status_code, payload).
    Requires authenticated user (me).
    """
    thread_id = str(body.get("thread_id", "")).strip()
    if not thread_id:
        return 400, {"ok": False, "error": "thread_id_required"}
    skey = f"user:{me['id']}"
    selected = ai.select_thread(skey, thread_id)
    st = ai.status(
        configured=bool(me.get("openai_configured")),
        model=str(me.get("openai_model") or "gpt-5-codex"),
        session_key=skey,
    )
    return 200, build_ai_thread_payload(
        thread=selected,
        threads=ai.list_threads(skey),
        ai_status=st,
        history=ai.history(skey, thread_id)[-80:],
    )


def handle_ai_profile_save(
    *,
    body: Dict[str, Any],
    me: Dict[str, Any],
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /ai/profile/save POST request.

    Returns (status_code, payload).
    Currently locked — profiles managed via local repo edits only.
    """
    return 403, {
        "ok": False,
        "error": "ai_profile_edit_locked",
        "hint": "Assistant profiles are managed via local repository edits only.",
    }


def handle_ai_profile_activate(
    *,
    body: Dict[str, Any],
    me: Dict[str, Any],
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /ai/profile/activate POST request.

    Returns (status_code, payload).
    Currently locked — profiles managed via local repo edits only.
    """
    return 403, {
        "ok": False,
        "error": "ai_profile_edit_locked",
        "hint": "Assistant profiles are managed via local repository edits only.",
    }


def handle_ai_profiles_get(
    *,
    ai_profiles: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /ai/profiles GET request.

    Returns (status_code, payload).
    """
    return 200, build_ai_profiles_payload(profiles=ai_profiles.list())


def handle_agent_file_upload(
    *,
    body: Dict[str, Any],
    repo_root: str,
    agent_upload_from_body_fn: Callable[..., Dict[str, Any]],
    build_attachment_payload_fn: Callable[..., Dict[str, Any]],
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /agent/file/upload and /agent/clean/file/upload POST requests.

    Returns (status_code, payload).
    """
    try:
        attachment = agent_upload_from_body_fn(repo_root, body)
    except RuntimeError as exc:
        return 400, {"ok": False, "error": str(exc)}
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}
    return 200, build_attachment_payload_fn(attachment=attachment)

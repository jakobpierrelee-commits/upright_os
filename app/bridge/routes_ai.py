"""
AI/agent route handlers extracted from server.py (Phase B, Slice 5).

These handlers manage AI threads, profiles, and authentication-gated operations.
"""
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from app.bridge.clean_ai import (
        build_ai_status_payload,
        build_ai_thread_payload,
        build_ai_profiles_payload,
        build_ai_knowledge_payload,
    )
except ImportError:
    from clean_ai import (  # type: ignore
        build_ai_status_payload,
        build_ai_thread_payload,
        build_ai_profiles_payload,
        build_ai_knowledge_payload,
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


def handle_ai_status_get(
    *,
    me: Optional[Dict[str, Any]],
    ai: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /ai/status GET request.

    Returns (status_code, payload).
    Works for both authenticated and unauthenticated users.
    """
    if not me:
        return 200, build_ai_status_payload(
            ai_status=ai.status(
                configured=False,
                model="gpt-5-codex",
                session_key="anon",
            ),
            history=[],
            threads=[],
        )
    model = str(me.get("openai_model") or "gpt-5-codex")
    configured = bool(me.get("openai_configured"))
    skey = f"user:{me['id']}"
    st = ai.status(configured=configured, model=model, session_key=skey)
    tid = st.get("active_thread_id")
    return 200, build_ai_status_payload(
        ai_status=st,
        history=ai.history(skey, tid)[-80:],
        threads=ai.list_threads(skey),
    )


def handle_ai_knowledge_get(
    *,
    knowledge: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /ai/knowledge GET request.

    Returns (status_code, payload).
    """
    return 200, build_ai_knowledge_payload(knowledge=knowledge.context())


def handle_agent_mode_set(
    *,
    body: Dict[str, Any],
    agent_mission: Any,
    build_agent_state_payload_fn: Callable[..., Dict[str, Any]],
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /agent/mode POST request.

    Returns (status_code, payload).
    """
    mode = str(body.get("mode", "")).strip()
    if not mode:
        return 400, {"ok": False, "error": "mode_required"}
    try:
        state = agent_mission.set_mode(mode)
    except RuntimeError as exc:
        if str(exc) == "invalid_mode":
            return 400, {
                "ok": False,
                "error": "invalid_mode",
                "allowed_modes": agent_mission.status().get("allowed_modes", []),
            }
        raise
    return 200, build_agent_state_payload_fn(agent=state)


def handle_session_heartbeat(
    *,
    control: Any,
    build_session_heartbeat_payload_fn: Callable[..., Dict[str, Any]],
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /session/heartbeat POST request.

    Returns (status_code, payload).
    """
    return 200, build_session_heartbeat_payload_fn(control=control.heartbeat())


def handle_setup_attempt_history_get(
    *,
    query: Dict[str, List[str]],
    setup_attempt_history: Any,
    build_attempt_history_payload_fn: Callable[..., Dict[str, Any]],
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /v1/setup/attempt-history GET request.

    Returns (status_code, payload).
    """
    limit = int((query.get("limit", ["40"]) or ["40"])[0] or 40)
    cursor = str((query.get("cursor", [""]) or [""])[0] or "")
    kind = str((query.get("kind", ["all"]) or ["all"])[0] or "all")
    page = setup_attempt_history.list_recent_page(
        limit=limit, cursor_attempt_id=cursor, kind=kind
    )
    return 200, build_attempt_history_payload_fn(
        attempts=page.get("attempts", []),
        next_cursor=page.get("next_cursor", ""),
        has_more=bool(page.get("has_more", False)),
    )


def handle_ai_threads_get(
    *,
    me: Dict[str, Any],
    ai: Any,
    build_ai_threads_status_payload_fn: Callable[..., Dict[str, Any]],
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /ai/threads GET request.

    Returns (status_code, payload).
    """
    skey = f"user:{me['id']}"
    return 200, build_ai_threads_status_payload_fn(
        threads=ai.list_threads(skey),
        ai=ai.status(
            configured=bool(me.get("openai_configured")),
            model=str(me.get("openai_model") or "gpt-5-codex"),
            session_key=skey,
        ),
    )


def handle_ai_rag_stats_get(
    *,
    me: Dict[str, Any],
    auth: Any,
    env_api_key: str,
    get_codex_rag_fn: Optional[Callable[..., Any]],
    build_stats_payload_fn: Callable[..., Dict[str, Any]],
    current_time: float,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /ai/rag/stats GET request.

    Returns (status_code, payload).
    """
    if not get_codex_rag_fn:
        return 503, {"ok": False, "error": "rag_not_available"}

    user_creds = auth.get_openai_key(int(me["id"]))
    openai_key = str(
        (user_creds or {}).get("api_key") or env_api_key or ""
    ).strip()
    rag = get_codex_rag_fn(openai_key)
    stats = rag.get_index_stats()
    return 200, build_stats_payload_fn(stats=stats, ts=current_time)


def handle_ai_metrics_get(
    *,
    query: Dict[str, List[str]],
    get_codex_db_fn: Callable[..., Any],
    build_tool_metrics_payload_fn: Callable[..., Dict[str, Any]],
    current_time: float,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /ai/metrics GET request.

    Returns (status_code, payload).
    """
    since_hours = float(
        (query.get("since_hours", ["24"]) or ["24"])[0] or 24
    )
    since_ts = (
        current_time - (since_hours * 3600) if since_hours > 0 else None
    )
    tool_filter = str((query.get("tool", [""]) or [""])[0]).strip() or None
    db = get_codex_db_fn()
    tool_metrics = db.get_tool_metrics(since_ts=since_ts, tool_filter=tool_filter)
    db_stats = db.get_stats()
    return 200, build_tool_metrics_payload_fn(
        since_hours=since_hours,
        tool_metrics=tool_metrics,
        db_stats=db_stats,
        ts=current_time,
    )


def handle_agent_clean_status_get(
    *,
    query: Dict[str, List[str]],
    gateway: Any,
    control: Any,
    codex_cli_login_status_fn: Callable[[], Dict[str, Any]],
    env_model: str,
    build_clean_status_payload_fn: Callable[..., Dict[str, Any]],
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /agent/clean/status GET request.

    Returns (status_code, payload).
    """
    mode = (
        str((query.get("mode", ["app_dev"]) or ["app_dev"])[0] or "app_dev").strip()
        or "app_dev"
    )
    codex_login = codex_cli_login_status_fn()
    serial_h = gateway.health()
    control_state = control.snapshot()
    model = str(env_model).strip() or "gpt-5-codex"
    payload = build_clean_status_payload_fn(
        mode=mode,
        codex_login=codex_login,
        serial_health=serial_h,
        control_snapshot=control_state,
        model=model,
        lines=gateway.recent_lines(80),
    )
    return 200, payload


def handle_agent_threads_get(
    *,
    query: Dict[str, List[str]],
    me: Optional[Dict[str, Any]],
    auth: Any,
    agent_mission: Any,
    provider_router: Any,
    ai: Any,
    env_model: str,
    codex_cli_login_status_fn: Callable[[], Dict[str, Any]],
    agent_resolve_model_fn: Callable[..., str],
    build_agent_status_payload_fn: Callable[..., Dict[str, Any]],
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /agent/threads GET request.

    Returns (status_code, payload).
    """
    mode_state = agent_mission.status()
    mode = str((query.get("mode", [""]) or [""])[0] or "").strip() or str(
        mode_state.get("mode", "robot_dev")
    )
    user_creds = (
        auth.get_openai_key(int(me["id"]))
        if me and isinstance(me.get("id"), int)
        else None
    )
    session_key = (
        f"user:{me['id']}:agent:{mode}"
        if me and isinstance(me.get("id"), int)
        else f"local:{mode}"
    )
    resolved = provider_router.resolve_agent_runtime(
        mode=mode,
        requested_api_key=None,
        requested_model=None,
        user_creds=user_creds,
        env_api_key=ai.default_api_key,
        env_model=env_model,
    )
    codex_login = codex_cli_login_status_fn()
    use_codex_cli = bool(codex_login.get("logged_in", False))
    runtime_model = agent_resolve_model_fn(
        mode,
        str(resolved.get("model", "")),
        prefer_codex=use_codex_cli,
    )
    runtime_configured = bool(resolved.get("api_key")) or bool(use_codex_cli)
    return 200, build_agent_status_payload_fn(
        agent=mode_state,
        threads=ai.list_threads(session_key),
        ai=ai.status(
            configured=runtime_configured,
            model=runtime_model or "(unset)",
            session_key=session_key,
        ),
    )


def handle_agent_status_get(
    *,
    me: Optional[Dict[str, Any]],
    auth: Any,
    agent_mission: Any,
    provider_router: Any,
    ai: Any,
    gateway: Any,
    control: Any,
    knowledge: Any,
    codex_agent_available: bool,
    env_model: str,
    codex_cli_login_status_fn: Callable[[], Dict[str, Any]],
    agent_choose_executor_fn: Callable[..., str],
    agent_resolve_model_fn: Callable[..., str],
    agent_model_allowed_fn: Callable[[str], bool],
    build_agent_status_payload_fn: Callable[..., Dict[str, Any]],
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /agent/status GET request.

    Returns (status_code, payload).
    """
    user_creds = (
        auth.get_openai_key(int(me["id"]))
        if me and isinstance(me.get("id"), int)
        else None
    )
    mode_state = agent_mission.status()
    resolved = provider_router.resolve_agent_runtime(
        mode=str(mode_state.get("mode", "robot_dev")),
        requested_api_key=None,
        requested_model=None,
        user_creds=user_creds,
        env_api_key=ai.default_api_key,
        env_model=env_model,
    )
    codex_login = codex_cli_login_status_fn()
    use_codex_cli = bool(codex_login.get("logged_in", False))
    has_api_key = bool(str(resolved.get("api_key", "")).strip())
    runtime_exec = agent_choose_executor_fn(
        mode=str(mode_state.get("mode", "robot_dev")),
        enable_tools=True,
        has_api_key=has_api_key,
        codex_logged_in=use_codex_cli,
        codex_agent_available=codex_agent_available,
    )
    runtime_model = agent_resolve_model_fn(
        str(mode_state.get("mode", "robot_dev")),
        str(resolved.get("model", "")),
        prefer_codex=use_codex_cli,
    )
    runtime_model_allowed = (
        True if use_codex_cli else agent_model_allowed_fn(runtime_model)
    )
    runtime_configured = has_api_key or bool(use_codex_cli)
    serial_h = gateway.health()
    payload = build_agent_status_payload_fn(
        mode_state=mode_state,
        resolved=resolved,
        codex_login=codex_login,
        runtime_exec=runtime_exec,
        runtime_model=runtime_model,
        runtime_model_allowed=runtime_model_allowed,
        runtime_configured=runtime_configured,
        serial_health=serial_h,
        control_snapshot=control.snapshot(),
        knowledge_context=knowledge.context(),
        lines=gateway.recent_lines(80),
    )
    return 200, payload

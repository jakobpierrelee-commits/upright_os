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


def handle_agent_thread_new(
    *,
    body: Dict[str, Any],
    me: Optional[Dict[str, Any]],
    agent_mission: Any,
    ai: Any,
    build_agent_thread_state_payload_fn: Callable[..., Dict[str, Any]],
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /agent/thread/new POST request.

    Returns (status_code, payload).
    """
    mode_state = agent_mission.status()
    mode = str(body.get("mode", "")).strip() or str(
        mode_state.get("mode", "robot_dev")
    )
    session_key = (
        f"user:{me['id']}:agent:{mode}"
        if me and isinstance(me.get("id"), int)
        else f"local:{mode}"
    )
    title = str(body.get("title", "")).strip() or None
    thread = ai.create_thread(session_key, title)
    return 200, build_agent_thread_state_payload_fn(
        agent=mode_state,
        thread=thread,
        threads=ai.list_threads(session_key),
        history=ai.history(session_key, str(thread.get("id")))[-80:],
    )


def handle_agent_thread_select(
    *,
    body: Dict[str, Any],
    me: Optional[Dict[str, Any]],
    agent_mission: Any,
    ai: Any,
    build_agent_thread_state_payload_fn: Callable[..., Dict[str, Any]],
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /agent/thread/select POST request.

    Returns (status_code, payload).
    """
    mode_state = agent_mission.status()
    mode = str(body.get("mode", "")).strip() or str(
        mode_state.get("mode", "robot_dev")
    )
    thread_id = str(body.get("thread_id", "")).strip()
    if not thread_id:
        return 400, {"ok": False, "error": "thread_id_required"}
    session_key = (
        f"user:{me['id']}:agent:{mode}"
        if me and isinstance(me.get("id"), int)
        else f"local:{mode}"
    )
    try:
        thread = ai.select_thread(session_key, thread_id)
    except RuntimeError as exc:
        if str(exc) == "thread_not_found":
            return 404, {"ok": False, "error": "thread_not_found"}
        raise
    return 200, build_agent_thread_state_payload_fn(
        agent=mode_state,
        thread=thread,
        threads=ai.list_threads(session_key),
        history=ai.history(session_key, str(thread.get("id")))[-80:],
    )


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


def handle_agent_chat_post(
    *,
    body: Dict[str, Any],
    gateway: Any,
    control: Any,
    firmware: Any,
    commissioning: Any,
    host_capture: Any,
    config_history: Any,
    knowledge: Any,
    ai: Any,
    auth: Any,
    agent_mission: Any,
    provider_router: Any,
    codex_agent: Any,
    burst_status_fn: Callable[[], Dict[str, Any]],
    legacy_execution_guard_fn: Callable[[str], Optional[Dict[str, Any]]],
    extract_auth_token_fn: Callable,
    codex_cli_login_status_fn: Callable[[], Dict[str, Any]],
    agent_choose_executor_fn: Callable,
    agent_resolve_model_fn: Callable,
    agent_model_allowed_fn: Callable[[str], bool],
    agent_mode_system_prompt_fn: Callable[[str], str],
    sanitize_agent_attachments_fn: Callable,
    commissioning_ai_context_fn: Callable,
    host_capture_ai_context_fn: Callable,
    assistant_capabilities_context_fn: Callable,
    normalize_reply_for_prompt_fn: Callable[[str, str], str],
    build_agent_chat_reply_payload_fn: Callable,
    handler_self: Any,
    env_openai_model: str,
) -> Tuple[int, Dict[str, Any]]:
    """Handle /agent/chat POST request."""
    guard = legacy_execution_guard_fn("/agent/chat")
    if guard is not None:
        return 403, guard
    
    msg = str(body.get("message", "")).strip()
    if not msg:
        return 400, {"ok": False, "error": "missing_message"}
    
    mode_state = agent_mission.status()
    mode = str(body.get("mode", "")).strip() or str(mode_state.get("mode", "robot_dev"))
    if mode != mode_state.get("mode"):
        try:
            mode_state = agent_mission.set_mode(mode)
        except RuntimeError:
            mode = str(mode_state.get("mode", "robot_dev"))
    
    tok = extract_auth_token_fn(handler_self, body)
    me = auth.me(tok) if tok else None
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
        env_model=env_openai_model,
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
    model = agent_resolve_model_fn(mode, str(resolved.get("model", "")), prefer_codex=use_codex_cli)
    
    if executor == "blocked":
        return 403, {
            "ok": False,
            "error": str(runtime_exec.get("degraded_reason", "runtime_blocked")),
            "executor": executor,
            "can_execute": False,
        }
    
    if not model:
        return 409, {
            "ok": False,
            "error": "openai_model_missing",
            "required": "codex_model",
            "model_source": str(resolved.get("model_source", "")),
        }
    
    if (not use_codex_cli) and (not agent_model_allowed_fn(model)):
        return 409, {
            "ok": False,
            "error": "agent_model_not_allowed",
            "required_substring": ",".join(resolved.get("allowed_model_substrings", [])),
            "resolved_model": model,
        }
    
    serial_h = gateway.health()
    cached_status = dict(serial_h.get("last_status", {}))
    attachments = sanitize_agent_attachments_fn(body.get("attachments"))
    
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
    
    thread_id = str(body.get("thread_id", "")).strip() or None
    session_key = (
        f"user:{me['id']}:agent:{mode}"
        if me and isinstance(me.get("id"), int)
        else f"local:{mode}"
    )
    prior_history = ai.history(session_key, thread_id) if thread_id else []
    
    try:
        if executor == "openai_tools":
            fw_status = firmware.status()
            fw_defaults = fw_status.get("defaults", {}) if isinstance(fw_status, dict) else {}
            active_sketch = str(
                body.get("sketch_path")
                or fw_status.get("sketch_path", "")
                or fw_defaults.get("sketch", "")
            )
            board_fqbn = str(
                body.get("board")
                or fw_status.get("board", "")
                or fw_defaults.get("fqbn", "arduino:avr:nano")
            )
            port = str(
                body.get("port")
                or fw_status.get("port", "")
                or fw_defaults.get("port", "")
            )
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
            tid = ai._append(session_key, "user", msg, thread_id=thread_id)
            ai._append(session_key, "assistant", answer, thread_id=tid)
            hist = ai.history(session_key, tid)[-80:]
            return 200, build_agent_chat_reply_payload_fn(
                agent=mode_state,
                reply=normalize_reply_for_prompt_fn(msg, answer),
                thread_id=tid,
                history=hist,
                threads=ai.list_threads(session_key),
                tool_calls=tool_out.get("tool_calls", []),
                iterations=int(tool_out.get("iterations", 1) or 1),
                provider="openai_tools",
                executor=executor,
            )
        
        if executor == "codex_cli_exec":
            out = ai.chat_codex_cli(
                message=msg,
                context=ctx,
                session_key=session_key,
                model=model,
                thread_id=thread_id,
                system_prompt=agent_mode_system_prompt_fn(mode),
            )
            tid = str(out.get("thread_id", "")).strip() or None
            hist = ai.history(session_key, tid)[-80:] if tid else []
            return 200, build_agent_chat_reply_payload_fn(
                agent=mode_state,
                reply=normalize_reply_for_prompt_fn(msg, out["answer"]),
                thread_id=tid,
                history=hist,
                threads=ai.list_threads(session_key),
                tool_calls=[],
                iterations=1,
                provider="codex_cli",
                executor=executor,
            )
        
        out = ai.chat(
            message=msg,
            context=ctx,
            session_key=session_key,
            api_key=api_key,
            model=model,
            thread_id=thread_id,
            system_prompt=agent_mode_system_prompt_fn(mode),
        )
    except RuntimeError as exc:
        return 500, {"ok": False, "error": str(exc)}
    
    tid = str(out.get("thread_id", "")).strip() or None
    hist = ai.history(session_key, tid)[-80:] if tid else []
    return 200, build_agent_chat_reply_payload_fn(
        agent=mode_state,
        reply=normalize_reply_for_prompt_fn(msg, out["answer"]),
        thread_id=tid,
        history=hist,
        threads=ai.list_threads(session_key),
        tool_calls=[],
        iterations=1,
        provider="openai",
        executor="openai_chat",
    )


def handle_clean_preflight_post(
    *,
    body: Dict[str, Any],
    ai: Any,
    firmware: Any,
    profiles: Any,
    repo_root: Any,
    codex_cli_login_status_fn: Callable,
    parse_clean_preflight_request_fn: Callable,
    clean_default_sketch_path_fn: Callable,
    resolve_manifest_gates_fn: Callable,
    runtime_manifest_profile_compatibility_fn: Callable,
    run_clean_preflight_fn: Callable,
    run_clean_auto_tools_fn: Callable,
    build_clean_agent_context_fn: Callable,
    clean_system_prompt_fn: Callable,
    normalize_reply_for_prompt_fn: Callable,
    validate_clean_preflight_response_fn: Callable,
    env_clean_model: str,
    env_clean_timeout: str,
) -> Tuple[int, Dict[str, Any]]:
    """Handle /agent/clean/preflight POST request."""
    import os
    codex_login = codex_cli_login_status_fn()
    err, req = parse_clean_preflight_request_fn(
        body=body,
        codex_login=codex_login,
        env_model=env_clean_model,
        env_timeout=env_clean_timeout,
        default_sketch=clean_default_sketch_path_fn(repo_root, firmware),
    )
    if err is not None:
        code, payload = err
        return code, payload
    assert req is not None
    manifest_gate, compat_gate, active_profile_id = resolve_manifest_gates_fn(
        firmware=firmware,
        profiles=profiles,
        compatibility_fn=runtime_manifest_profile_compatibility_fn,
        sketch=str(req["sketch"]),
    )
    payload = run_clean_preflight_fn(
        mode=str(req["mode"]),
        max_ms=int(req["max_ms"]),
        max_ms_tools=int(req["max_ms_tools"]),
        gate_only=bool(req["gate_only"]),
        with_compile=bool(req["with_compile"]),
        model=str(req["model"]),
        clean_timeout_s=int(req["clean_timeout_s"]),
        manifest_gate=manifest_gate,
        compat_gate=compat_gate,
        active_profile_id=active_profile_id,
        ai=ai,
        run_auto_tools=run_clean_auto_tools_fn,
        build_context=build_clean_agent_context_fn,
        system_prompt_for_mode=clean_system_prompt_fn,
        normalize_reply_for_prompt=normalize_reply_for_prompt_fn,
        validate_preflight_payload=validate_clean_preflight_response_fn,
    )
    return 200, payload


def handle_clean_chat_post(
    *,
    body: Dict[str, Any],
    ai: Any,
    codex_cli_login_status_fn: Callable,
    parse_clean_chat_request_fn: Callable,
    sanitize_agent_attachments_fn: Callable,
    run_clean_chat_fn: Callable,
    run_clean_auto_tools_fn: Callable,
    build_clean_agent_context_fn: Callable,
    clean_system_prompt_fn: Callable,
    normalize_reply_for_prompt_fn: Callable,
    env_clean_model: str,
    env_clean_timeout: str,
) -> Tuple[int, Dict[str, Any]]:
    """Handle /agent/clean/chat POST request."""
    codex_login = codex_cli_login_status_fn()
    err, req = parse_clean_chat_request_fn(
        body=body,
        codex_login=codex_login,
        env_model=env_clean_model,
        env_timeout=env_clean_timeout,
        sanitize_attachments_fn=sanitize_agent_attachments_fn,
    )
    if err is not None:
        code, payload = err
        return code, payload
    assert req is not None
    code, payload = run_clean_chat_fn(
        msg=str(req["msg"]),
        mode=str(req["mode"]),
        model=str(req["model"]),
        clean_timeout_s=int(req["clean_timeout_s"]),
        session_key=str(req["session_key"]),
        thread_id=req.get("thread_id"),
        attachments=list(req.get("attachments") or []),
        auto_tools=bool(req.get("auto_tools", False)),
        ai=ai,
        run_auto_tools=run_clean_auto_tools_fn,
        build_context=build_clean_agent_context_fn,
        system_prompt_for_mode=clean_system_prompt_fn,
        normalize_reply_for_prompt=normalize_reply_for_prompt_fn,
    )
    return code, payload


def apply_assistant_plan(
    gateway: Any,
    config_history: Any,
    firmware: Any,
    plan: Dict[str, Any],
    *,
    source: str,
    apply_tuning_plan_fn: Any,
) -> Dict[str, Any]:
    """Apply an assistant plan including tuning, unified sketch, or sketch content."""
    tuning_keys = {"pid", "motion", "setpoint", "limits"}
    tuning_plan = {k: plan[k] for k in tuning_keys if k in plan}
    applied: list[str] = []
    changed: Dict[str, Any] = {}
    artifacts: Dict[str, Any] = {}
    snapshot_id: Optional[str] = None
    status_after: Optional[Dict[str, Any]] = None

    if tuning_plan:
        t = apply_tuning_plan_fn(gateway, config_history, tuning_plan, source=source)
        if not bool(t.get("ok", False)):
            return t
        applied.extend(
            list(t.get("applied", [])) if isinstance(t.get("applied"), list) else []
        )
        if isinstance(t.get("changed"), dict):
            changed.update(t["changed"])
        sid = t.get("snapshot_id")
        if isinstance(sid, str) and sid:
            snapshot_id = sid
        if isinstance(t.get("status"), dict):
            status_after = t.get("status")

    unified = plan.get("unified")
    if isinstance(unified, dict):
        profile = unified.get("profile")
        if not isinstance(profile, dict):
            raise RuntimeError("apply_unified_profile_missing")
        sketch_name = unified.get("sketch_name")
        out = firmware.generate_unified(
            profile=profile,
            sketch_name=str(sketch_name) if isinstance(sketch_name, str) else None,
        )
        applied.append("unified")
        artifacts["unified_folder"] = out.get("sketch_folder")
        artifacts["unified_archive"] = out.get("archive")
        artifacts["unified_main_file"] = out.get("main_file")

    sketch = plan.get("sketch")
    if isinstance(sketch, dict):
        content = sketch.get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("apply_sketch_content_missing")
        path = sketch.get("path")
        profile = sketch.get("profile")
        out = firmware.write_sketch_with_backup(
            content=content,
            path=str(path) if isinstance(path, str) and path.strip() else None,
            source="assistant",
            profile=profile if isinstance(profile, dict) else None,
        )
        applied.append("sketch")
        artifacts["sketch_path"] = out.get("path")
        artifacts["sketch_backup"] = out.get("backup_path")
        artifacts["sketch_bytes"] = out.get("bytes")

    if not status_after:
        try:
            status_after = gateway.get_status()
        except Exception:
            status_after = None
    return {
        "ok": True,
        "snapshot_id": snapshot_id,
        "applied": applied,
        "changed": changed,
        "artifacts": artifacts,
        "status": status_after,
    }


def agent_upload_from_body(
    repo_root: Any, body: Dict[str, Any], *, safe_filename_fn: Any, attachment_kind_fn: Any
) -> Dict[str, Any]:
    """Process a file upload from agent request body."""
    import base64
    import secrets
    import time

    name = safe_filename_fn(str(body.get("name", "")))
    mime = (
        str(body.get("mime", "application/octet-stream")).strip()
        or "application/octet-stream"
    )
    payload_b64 = str(body.get("content_base64", "")).strip()
    if not payload_b64:
        raise RuntimeError("missing_content_base64")
    try:
        raw = base64.b64decode(payload_b64, validate=True)
    except Exception as exc:
        raise RuntimeError(f"invalid_base64:{exc}") from exc
    if not raw:
        raise RuntimeError("empty_file")
    if len(raw) > (5 * 1024 * 1024):
        raise RuntimeError("file_too_large_max_5mb")

    up_dir = repo_root / "app" / "bridge" / "agent_uploads"
    up_dir.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time())
    token = secrets.token_hex(4)
    final_name = f"{stamp}_{token}_{name}"
    target = up_dir / final_name
    target.write_bytes(raw)

    kind = attachment_kind_fn(mime, name)
    text_excerpt = ""
    if kind in {"text", "csv"}:
        try:
            text_excerpt = raw.decode("utf-8", errors="replace")[:16000]
        except Exception:
            text_excerpt = ""

    return {
        "id": f"att_{stamp}_{token}",
        "name": name,
        "mime": mime,
        "kind": kind,
        "size": len(raw),
        "path": str(target),
        "text_excerpt": text_excerpt,
    }


def assistant_capabilities_context(*, allow_apply: bool) -> Dict[str, Any]:
    """Build assistant capabilities context for AI responses."""
    return {
        "can_read": [
            "cached_status",
            "control_state",
            "serial_health",
            "burst_status",
            "host_capture_latest_csv_tail",
            "commissioning_artifacts",
            "assistant_knowledge_pack",
            "config_snapshots",
        ],
        "can_apply_now": bool(allow_apply),
        "can_write": [
            "pid",
            "motion",
            "setpoint",
            "limits",
            "generate_unified_firmware_scaffold",
            "write_sketch_with_backup",
        ]
        if allow_apply
        else [],
        "confirm_first_for": [
            "arm/disarm",
            "cal_zero",
            "firmware_upload_or_flash",
            "power_state_changes",
        ],
    }


def hardware_context_board_label(hardware_context: Any) -> str:
    """Extract board label from hardware context."""
    if not isinstance(hardware_context, dict):
        return "unknown board"
    board = hardware_context.get("board")
    if not isinstance(board, dict):
        return "unknown board"
    resolved = board.get("resolved_profile")
    if isinstance(resolved, dict):
        label = str(resolved.get("label", "")).strip()
        model = str(resolved.get("id", "")).strip()
        if label:
            return label
        if model:
            return model
    selected = str(board.get("selected_fqbn", "")).strip()
    return selected or "unknown board"


def format_hardware_context_notice(
    hardware_context: Any, update_info: Any, *, board_label_fn: Any = None
) -> str:
    """Format a notice about hardware context changes."""
    if not isinstance(update_info, dict):
        return ""
    if not bool(update_info.get("accepted")):
        return ""
    if not bool(update_info.get("changed")):
        return ""
    if board_label_fn is None:
        board_label_fn = hardware_context_board_label
    board_label = board_label_fn(hardware_context)
    changed_keys = update_info.get("changed_keys")
    changed_txt = ""
    if isinstance(changed_keys, list):
        clean_keys = [str(k).strip() for k in changed_keys if str(k).strip()]
        if clean_keys:
            changed_txt = ", ".join(clean_keys[:5])
    if bool(update_info.get("initial")):
        return f"Hardware context synced: {board_label}. I will use this as the active build baseline."
    if changed_txt:
        return f"Hardware context updated ({board_label}). Changed fields: {changed_txt}. I will adapt guidance to the new parts map."
    return f"Hardware context updated ({board_label}). I will adapt guidance to the new parts map."


def attachment_kind(mime: str, name: str) -> str:
    """Determine attachment kind from mime type and filename."""
    m = str(mime or "").strip().lower()
    n = str(name or "").strip().lower()
    if m.startswith("image/"):
        return "image"
    if "csv" in m or n.endswith(".csv"):
        return "csv"
    if (
        m.startswith("text/")
        or "json" in m
        or "yaml" in m
        or "toml" in m
        or n.endswith((".txt", ".md", ".json", ".yaml", ".yml", ".toml", ".log"))
    ):
        return "text"
    return "binary"

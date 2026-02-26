from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple


def _clean_mode(raw: Any) -> str:
    return str(raw or "").strip() or "app_dev"


def _clean_model(raw_model: Any, env_model: str) -> str:
    return str(raw_model or "").strip() or str(env_model or "").strip() or "gpt-5-codex"


def _clean_timeout_s(env_timeout: str) -> int:
    return int(env_timeout)


def parse_clean_chat_request(
    *,
    body: Dict[str, Any],
    codex_login: Dict[str, Any],
    env_model: str,
    env_timeout: str,
    sanitize_attachments_fn: Callable[[Any], list[Dict[str, Any]]],
) -> Tuple[Optional[Tuple[int, Dict[str, Any]]], Optional[Dict[str, Any]]]:
    msg = str(body.get("message", "")).strip()
    if not msg:
        return (400, {"ok": False, "error": "missing_message"}), None

    if not bool(codex_login.get("logged_in", False)):
        return (
            403,
            {
                "ok": False,
                "error": "codex_login_required",
                "executor": "blocked",
                "can_execute": False,
            },
        ), None

    mode = _clean_mode(body.get("mode", ""))
    model = _clean_model(body.get("model", ""), env_model)
    clean_timeout_s = _clean_timeout_s(env_timeout)
    attachments = sanitize_attachments_fn(body.get("attachments"))
    thread_id = str(body.get("thread_id", "")).strip() or None
    auto_tools = bool(body.get("auto_tools", False))
    session_key = f"local:clean:{mode}"
    return None, {
        "msg": msg,
        "mode": mode,
        "model": model,
        "clean_timeout_s": clean_timeout_s,
        "attachments": attachments,
        "thread_id": thread_id,
        "auto_tools": auto_tools,
        "session_key": session_key,
    }


def parse_clean_preflight_request(
    *,
    body: Dict[str, Any],
    codex_login: Dict[str, Any],
    env_model: str,
    env_timeout: str,
    default_sketch: str,
) -> Tuple[Optional[Tuple[int, Dict[str, Any]]], Optional[Dict[str, Any]]]:
    mode = _clean_mode(body.get("mode", ""))
    max_ms = max(1000, int(body.get("max_ms", 45000) or 45000))
    max_ms_tools = max(max_ms, int(body.get("max_ms_tools", 120000) or 120000))
    gate_only = bool(body.get("gate_only", False))
    with_compile = bool(body.get("with_compile", False))
    if not bool(codex_login.get("logged_in", False)):
        return (
            403,
            {
                "ok": False,
                "error": "codex_login_required",
                "results": [],
            },
        ), None

    model = _clean_model(body.get("model", ""), env_model)
    sketch = str(body.get("sketch", "")).strip() or default_sketch
    clean_timeout_s = _clean_timeout_s(env_timeout)
    return None, {
        "mode": mode,
        "max_ms": max_ms,
        "max_ms_tools": max_ms_tools,
        "gate_only": gate_only,
        "with_compile": with_compile,
        "model": model,
        "sketch": sketch,
        "clean_timeout_s": clean_timeout_s,
    }

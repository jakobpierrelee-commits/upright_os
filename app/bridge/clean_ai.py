from __future__ import annotations

from typing import Any, Dict, List


def build_ai_status_payload(
    *,
    ai_status: Dict[str, Any],
    history: List[Dict[str, Any]],
    threads: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {"ok": True, "ai": ai_status, "history": history, "threads": threads}


def build_ai_threads_payload(*, threads: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"ok": True, "threads": threads}


def build_ai_profiles_payload(*, profiles: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"ok": True, "profiles": profiles}


def build_ai_knowledge_payload(*, knowledge: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "knowledge": knowledge}


def build_auth_user_payload(*, user: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "user": user}


def build_auth_openai_status_payload(*, openai: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "openai": openai}


def build_session_heartbeat_payload(*, control: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "control": control}


def build_ai_thread_payload(
    *,
    thread: Dict[str, Any],
    threads: List[Dict[str, Any]],
    ai_status: Dict[str, Any],
    history: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "ok": True,
        "thread": thread,
        "threads": threads,
        "ai": ai_status,
        "history": history,
    }


def build_auth_session_payload(
    *, session_token: str, user: Dict[str, Any]
) -> Dict[str, Any]:
    return {"ok": True, "session_token": session_token, "user": user}


def build_agent_thread_state_payload(
    *,
    agent: Dict[str, Any],
    thread: Dict[str, Any],
    threads: List[Dict[str, Any]],
    history: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "ok": True,
        "agent": agent,
        "thread": thread,
        "threads": threads,
        "history": history,
    }

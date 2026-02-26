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


def build_agent_chat_reply_payload(
    *,
    agent: Dict[str, Any],
    reply: str,
    thread_id: Optional[str],
    history: List[Dict[str, Any]],
    threads: List[Dict[str, Any]],
    tool_calls: List[Dict[str, Any]],
    iterations: int,
    provider: str,
    executor: str,
) -> Dict[str, Any]:
    return {
        "ok": True,
        "agent": agent,
        "reply": reply,
        "thread_id": thread_id,
        "history": history,
        "threads": threads,
        "tool_calls": tool_calls,
        "iterations": iterations,
        "provider": provider,
        "executor": executor,
    }


def build_agent_status_payload(
    *,
    agent: Dict[str, Any],
    threads: List[Dict[str, Any]],
    ai: Dict[str, Any],
) -> Dict[str, Any]:
    return {"ok": True, "agent": agent, "threads": threads, "ai": ai}


def build_disambiguation_reply_payload(
    *,
    reply: str,
    ai: Dict[str, Any],
    history: List[Dict[str, Any]],
    threads: List[Dict[str, Any]],
    thread_id: str,
) -> Dict[str, Any]:
    return {
        "ok": True,
        "reply": reply,
        "tool_calls": [],
        "iterations": 0,
        "ai": ai,
        "history": history,
        "threads": threads,
        "thread_id": thread_id,
    }


def build_chat_with_tools_payload(
    *,
    reply: str,
    tool_calls: List[Dict[str, Any]],
    iterations: int,
    ai: Dict[str, Any],
    history: List[Dict[str, Any]],
    threads: List[Dict[str, Any]],
    thread_id: str,
) -> Dict[str, Any]:
    return {
        "ok": True,
        "reply": reply,
        "tool_calls": tool_calls,
        "iterations": iterations,
        "ai": ai,
        "history": history,
        "threads": threads,
        "thread_id": thread_id,
    }


def build_rag_index_payload(
    *,
    docs: Dict[str, Any],
    sketches: Dict[str, Any],
    elapsed_ms: float,
    ts: float,
) -> Dict[str, Any]:
    return {
        "ok": True,
        "docs": docs,
        "sketches": sketches,
        "elapsed_ms": elapsed_ms,
        "ts": ts,
    }


def build_ai_threads_status_payload(
    *, threads: List[Dict[str, Any]], ai: Dict[str, Any]
) -> Dict[str, Any]:
    return {"ok": True, "threads": threads, "ai": ai}


def build_ai_chat_response_payload(
    *,
    reply: str,
    ai: Dict[str, Any],
    history: List[Dict[str, Any]],
    threads: List[Dict[str, Any]],
    thread_id: Optional[str],
    apply: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "ok": True,
        "reply": reply,
        "ai": ai,
        "history": history,
        "threads": threads,
        "thread_id": thread_id,
        "apply": apply,
    }


def build_openai_config_payload(
    *,
    configured: bool,
    model: Optional[str],
    runtime_has_key: bool,
    runtime_key_source: Optional[str],
) -> Dict[str, Any]:
    return {
        "ok": True,
        "openai": {
            "configured": configured,
            "model": model,
            "runtime_has_key": runtime_has_key,
            "runtime_key_source": runtime_key_source,
        },
    }

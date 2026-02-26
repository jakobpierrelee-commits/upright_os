import pathlib
import sys
import threading
from typing import Any

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from clean_codex_chat import run_clean_chat, run_clean_chat_stream


class _AIStub:
    def __init__(self) -> None:
        self.last_stream_cancel = None

    def chat_codex_cli(self, **kwargs: Any) -> dict[str, str]:
        return {"thread_id": "t-chat", "answer": "ok"}

    def chat_codex_cli_stream(self, **kwargs: Any) -> dict[str, str]:
        kwargs["on_progress"]("running")
        kwargs["on_delta"]("partial")
        self.last_stream_cancel = kwargs.get("cancel_event")
        return {"thread_id": "t-chat", "answer": "stream ok"}

    def history(self, session_key: str, thread_id: str) -> list[dict[str, str]]:
        return [{"role": "assistant", "text": "x"}]

    def list_threads(self, session_key: str) -> list[dict[str, str]]:
        return [{"id": "t-chat", "title": "Clean Chat"}]


class _AIErrorStub(_AIStub):
    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def chat_codex_cli(self, **kwargs: Any) -> dict[str, str]:
        raise RuntimeError(self.message)


class _AIStreamErrorStub(_AIStub):
    def chat_codex_cli_stream(self, **kwargs: Any) -> dict[str, str]:
        raise RuntimeError("stream failed")


def _run_auto_tools(**kwargs: Any) -> list[dict[str, Any]]:
    return [{"name": "connect_probe", "result": {"ok": True}}]


def _build_context(**kwargs: Any) -> dict[str, str]:
    return {"ctx": "ok"}


def _system_prompt_for_mode(mode: str) -> str:
    return f"mode={mode}"


def _normalize_reply(user_msg: str, reply: str) -> str:
    return reply


def test_run_clean_chat_success() -> None:
    code, payload = run_clean_chat(
        msg="hello",
        mode="app_dev",
        model="gpt-5-codex",
        clean_timeout_s=120,
        session_key="local:clean:app_dev",
        thread_id=None,
        attachments=[],
        auto_tools=True,
        ai=_AIStub(),
        run_auto_tools=_run_auto_tools,
        build_context=_build_context,
        system_prompt_for_mode=_system_prompt_for_mode,
        normalize_reply_for_prompt=_normalize_reply,
    )
    assert code == 200
    assert payload["ok"] is True
    assert payload["reply"] == "ok"
    assert len(payload["tool_calls"]) == 1


def test_run_clean_chat_timeout_mapping() -> None:
    code, payload = run_clean_chat(
        msg="hello",
        mode="app_dev",
        model="gpt-5-codex",
        clean_timeout_s=120,
        session_key="local:clean:app_dev",
        thread_id=None,
        attachments=[],
        auto_tools=False,
        ai=_AIErrorStub("codex_cli_timeout:120s"),
        run_auto_tools=_run_auto_tools,
        build_context=_build_context,
        system_prompt_for_mode=_system_prompt_for_mode,
        normalize_reply_for_prompt=_normalize_reply,
    )
    assert code == 504
    assert payload["error_kind"] == "timeout"


def test_run_clean_chat_quota_mapping() -> None:
    code, payload = run_clean_chat(
        msg="hello",
        mode="app_dev",
        model="gpt-5-codex",
        clean_timeout_s=120,
        session_key="local:clean:app_dev",
        thread_id=None,
        attachments=[],
        auto_tools=False,
        ai=_AIErrorStub("Purchase more credits to continue"),
        run_auto_tools=_run_auto_tools,
        build_context=_build_context,
        system_prompt_for_mode=_system_prompt_for_mode,
        normalize_reply_for_prompt=_normalize_reply,
    )
    assert code == 429
    assert payload["error"] == "codex_usage_limited"
    assert payload["error_kind"] == "quota"


def test_run_clean_chat_upstream_mapping() -> None:
    code, payload = run_clean_chat(
        msg="hello",
        mode="app_dev",
        model="gpt-5-codex",
        clean_timeout_s=120,
        session_key="local:clean:app_dev",
        thread_id=None,
        attachments=[],
        auto_tools=False,
        ai=_AIErrorStub("bridge exploded"),
        run_auto_tools=_run_auto_tools,
        build_context=_build_context,
        system_prompt_for_mode=_system_prompt_for_mode,
        normalize_reply_for_prompt=_normalize_reply,
    )
    assert code == 502
    assert payload["error_kind"] == "upstream"


def test_run_clean_chat_stream_success_events() -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    cancelled = threading.Event()
    ai = _AIStub()
    run_clean_chat_stream(
        msg="hello",
        mode="app_dev",
        model="gpt-5-codex",
        clean_timeout_s=120,
        session_key="local:clean:app_dev",
        thread_id=None,
        attachments=[],
        auto_tools=True,
        ai=ai,
        run_auto_tools=_run_auto_tools,
        build_context=_build_context,
        system_prompt_for_mode=_system_prompt_for_mode,
        normalize_reply_for_prompt=_normalize_reply,
        emit=lambda name, payload: events.append((name, payload)),
        is_disconnected=lambda: False,
        cancel_event=cancelled,
    )
    names = [name for (name, _) in events]
    assert "progress" in names
    assert "delta" in names
    assert names[-1] == "done"
    assert ai.last_stream_cancel is cancelled


def test_run_clean_chat_stream_error_event() -> None:
    events: list[tuple[str, dict[str, Any]]] = []
    run_clean_chat_stream(
        msg="hello",
        mode="app_dev",
        model="gpt-5-codex",
        clean_timeout_s=120,
        session_key="local:clean:app_dev",
        thread_id=None,
        attachments=[],
        auto_tools=False,
        ai=_AIStreamErrorStub(),
        run_auto_tools=_run_auto_tools,
        build_context=_build_context,
        system_prompt_for_mode=_system_prompt_for_mode,
        normalize_reply_for_prompt=_normalize_reply,
        emit=lambda name, payload: events.append((name, payload)),
        is_disconnected=lambda: False,
        cancel_event=threading.Event(),
    )
    assert events[-1][0] == "error"

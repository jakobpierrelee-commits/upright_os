import pathlib
import sys
from typing import Any

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from clean_threads import (
    clean_session_key,
    handle_clean_thread_new,
    handle_clean_thread_select,
    handle_clean_threads_get,
)


class _AI:
    def list_threads(self, session_key: str) -> list[dict[str, Any]]:
        return [{"id": "t1", "title": "one"}]

    def status(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "configured": bool(kwargs.get("configured")),
            "model": kwargs.get("model"),
        }

    def create_thread(self, session_key: str, title: str | None) -> dict[str, Any]:
        return {"id": "t2", "title": title or "New Chat"}

    def history(self, session_key: str, thread_id: str) -> list[dict[str, Any]]:
        return [{"role": "assistant", "text": "x"}]

    def select_thread(self, session_key: str, thread_id: str) -> dict[str, Any]:
        if thread_id == "missing":
            raise RuntimeError("thread_not_found")
        return {"id": thread_id, "title": "selected"}


def test_clean_session_key_default() -> None:
    assert clean_session_key("") == "local:clean:app_dev"


def test_handle_clean_threads_get() -> None:
    payload = handle_clean_threads_get(
        mode="app_dev",
        ai=_AI(),
        codex_logged_in=True,
        model="gpt-5-codex",
    )
    assert payload["ok"] is True
    assert payload["threads"][0]["id"] == "t1"
    assert payload["ai"]["configured"] is True


def test_handle_clean_thread_new() -> None:
    payload = handle_clean_thread_new(mode="app_dev", title="hello", ai=_AI())
    assert payload["ok"] is True
    assert payload["thread"]["id"] == "t2"
    assert len(payload["history"]) == 1


def test_handle_clean_thread_select_missing_id() -> None:
    code, payload = handle_clean_thread_select(mode="app_dev", thread_id="", ai=_AI())
    assert code == 400
    assert payload["error"] == "thread_id_required"


def test_handle_clean_thread_select_not_found() -> None:
    code, payload = handle_clean_thread_select(
        mode="app_dev", thread_id="missing", ai=_AI()
    )
    assert code == 404
    assert payload["error"] == "thread_not_found"


def test_handle_clean_thread_select_success() -> None:
    code, payload = handle_clean_thread_select(mode="app_dev", thread_id="t1", ai=_AI())
    assert code == 200
    assert payload["thread"]["id"] == "t1"

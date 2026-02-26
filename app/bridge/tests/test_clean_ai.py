import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from clean_ai import (
    build_ai_knowledge_payload,
    build_ai_profiles_payload,
    build_ai_status_payload,
    build_ai_thread_payload,
    build_ai_threads_payload,
    build_auth_openai_status_payload,
    build_auth_user_payload,
    build_session_heartbeat_payload,
)


def test_build_ai_status_payload_shape() -> None:
    payload = build_ai_status_payload(
        ai_status={"configured": True, "model": "gpt-5"},
        history=[{"role": "user", "content": "hello"}],
        threads=[{"id": "t1", "title": "Test"}],
    )
    assert payload["ok"] is True
    assert payload["ai"]["configured"] is True
    assert len(payload["history"]) == 1
    assert payload["threads"][0]["id"] == "t1"


def test_build_ai_threads_payload_shape() -> None:
    payload = build_ai_threads_payload(threads=[{"id": "t1"}, {"id": "t2"}])
    assert payload["ok"] is True
    assert len(payload["threads"]) == 2


def test_build_ai_profiles_payload_shape() -> None:
    payload = build_ai_profiles_payload(profiles=[{"id": "p1", "name": "Default"}])
    assert payload["ok"] is True
    assert payload["profiles"][0]["name"] == "Default"


def test_build_ai_knowledge_payload_shape() -> None:
    payload = build_ai_knowledge_payload(
        knowledge={"facts": ["fact1"], "version": "1.0"}
    )
    assert payload["ok"] is True
    assert payload["knowledge"]["version"] == "1.0"


def test_build_auth_user_payload_shape() -> None:
    payload = build_auth_user_payload(user={"id": 1, "email": "test@example.com"})
    assert payload["ok"] is True
    assert payload["user"]["email"] == "test@example.com"


def test_build_auth_openai_status_payload_shape() -> None:
    payload = build_auth_openai_status_payload(
        openai={"configured": True, "model": "gpt-5"}
    )
    assert payload["ok"] is True
    assert payload["openai"]["configured"] is True


def test_build_session_heartbeat_payload_shape() -> None:
    payload = build_session_heartbeat_payload(
        control={"arm_prepared": False, "session_fresh": True}
    )
    assert payload["ok"] is True
    assert payload["control"]["session_fresh"] is True


def test_build_ai_thread_payload_shape() -> None:
    payload = build_ai_thread_payload(
        thread={"id": "t1", "title": "Test Thread"},
        threads=[{"id": "t1"}, {"id": "t2"}],
        ai_status={"configured": True, "model": "gpt-5"},
        history=[{"role": "user", "content": "hello"}],
    )
    assert payload["ok"] is True
    assert payload["thread"]["id"] == "t1"
    assert len(payload["threads"]) == 2
    assert payload["ai"]["configured"] is True
    assert len(payload["history"]) == 1

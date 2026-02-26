import pathlib
import sys
from typing import Any

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from clean_request_parsers import (
    parse_clean_chat_request,
    parse_clean_preflight_request,
)


def _sanitize(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return raw
    return []


def test_parse_clean_chat_request_missing_message() -> None:
    err, req = parse_clean_chat_request(
        body={},
        codex_login={"logged_in": True},
        env_model="gpt-5-codex",
        env_timeout="120",
        sanitize_attachments_fn=_sanitize,
    )
    assert req is None
    assert err is not None
    assert err[0] == 400
    assert err[1]["error"] == "missing_message"


def test_parse_clean_chat_request_requires_login() -> None:
    err, req = parse_clean_chat_request(
        body={"message": "hi"},
        codex_login={"logged_in": False},
        env_model="gpt-5-codex",
        env_timeout="120",
        sanitize_attachments_fn=_sanitize,
    )
    assert req is None
    assert err is not None
    assert err[0] == 403
    assert err[1]["error"] == "codex_login_required"


def test_parse_clean_chat_request_success() -> None:
    err, req = parse_clean_chat_request(
        body={
            "message": "hello",
            "mode": "robot_dev",
            "model": "",
            "thread_id": "t1",
            "auto_tools": True,
            "attachments": [{"name": "a.txt"}],
        },
        codex_login={"logged_in": True},
        env_model="gpt-5-codex",
        env_timeout="120",
        sanitize_attachments_fn=_sanitize,
    )
    assert err is None
    assert req is not None
    assert req["mode"] == "robot_dev"
    assert req["session_key"] == "local:clean:robot_dev"
    assert req["model"] == "gpt-5-codex"
    assert req["thread_id"] == "t1"
    assert req["auto_tools"] is True


def test_parse_clean_preflight_request_requires_login() -> None:
    err, req = parse_clean_preflight_request(
        body={},
        codex_login={"logged_in": False},
        env_model="gpt-5-codex",
        env_timeout="120",
        default_sketch="app/bridge/firmware.ino",
    )
    assert req is None
    assert err is not None
    assert err[0] == 403
    assert err[1]["error"] == "codex_login_required"


def test_parse_clean_preflight_request_success() -> None:
    err, req = parse_clean_preflight_request(
        body={
            "mode": "app_dev",
            "max_ms": 45000,
            "max_ms_tools": 120000,
            "with_compile": True,
        },
        codex_login={"logged_in": True},
        env_model="gpt-5-codex",
        env_timeout="120",
        default_sketch="app/bridge/firmware.ino",
    )
    assert err is None
    assert req is not None
    assert req["mode"] == "app_dev"
    assert req["with_compile"] is True
    assert req["sketch"] == "app/bridge/firmware.ino"
    assert req["clean_timeout_s"] == 120

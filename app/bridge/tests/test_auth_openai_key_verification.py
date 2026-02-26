from __future__ import annotations

from io import BytesIO
from urllib.error import HTTPError

import pytest

from app.bridge import server
from app.bridge.server import AuthManager


class _DummyResponse:
    def __init__(self, payload: bytes = b'{"data":[{"id":"gpt-5-mini"}]}') -> None:
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self._payload


def _register_user(auth: AuthManager) -> int:
    out = auth.register("verify@example.com", "Passw0rd!")
    me = auth.me(out["session_token"])
    assert me is not None
    return int(me["id"])


def test_set_openai_key_rejects_invalid_prefix(tmp_path):
    auth = AuthManager(tmp_path)
    user_id = _register_user(auth)
    with pytest.raises(RuntimeError, match="invalid_openai_key"):
        auth.set_openai_key(user_id, "not-a-key", "gpt-5-mini")


def test_set_openai_key_rejects_on_live_unauthorized(tmp_path, monkeypatch):
    auth = AuthManager(tmp_path)
    user_id = _register_user(auth)

    def _fake_urlopen(req, timeout=None, context=None):
        raise HTTPError(
            req.full_url,  # type: ignore[arg-type]
            401,
            "Unauthorized",
            hdrs=None,
            fp=BytesIO(b'{"error":{"message":"invalid_api_key"}}'),
        )

    monkeypatch.setattr(server.urlrequest, "urlopen", _fake_urlopen)

    with pytest.raises(RuntimeError, match="invalid_openai_key"):
        auth.set_openai_key(user_id, "sk-invalid-for-test", "gpt-5-mini")
    assert auth.get_openai_key(user_id) is None


def test_set_openai_key_saves_only_after_live_verification(tmp_path, monkeypatch):
    auth = AuthManager(tmp_path)
    user_id = _register_user(auth)

    def _fake_urlopen(req, timeout=None, context=None):
        return _DummyResponse()

    monkeypatch.setattr(server.urlrequest, "urlopen", _fake_urlopen)

    out = auth.set_openai_key(user_id, "sk-live-verified-test", "gpt-5-mini")
    assert out["configured"] is True
    creds = auth.get_openai_key(user_id)
    assert creds is not None
    assert creds["api_key"] == "sk-live-verified-test"
    assert creds["model"] == "gpt-5-mini"


def test_set_openai_key_returns_verification_error_on_upstream_failure(
    tmp_path, monkeypatch
):
    auth = AuthManager(tmp_path)
    user_id = _register_user(auth)

    def _fake_urlopen(req, timeout=None, context=None):
        raise HTTPError(
            req.full_url,  # type: ignore[arg-type]
            500,
            "Server Error",
            hdrs=None,
            fp=BytesIO(b"{}"),
        )

    monkeypatch.setattr(server.urlrequest, "urlopen", _fake_urlopen)

    with pytest.raises(RuntimeError, match=r"openai_key_verification_failed:500"):
        auth.set_openai_key(user_id, "sk-upstream-fail-test", "gpt-5-mini")
    assert auth.get_openai_key(user_id) is None

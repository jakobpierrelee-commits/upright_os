import pathlib
import sys
from types import SimpleNamespace
from typing import Any

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

import clean_auth_helpers as auth_helpers


def _reset_login_cache() -> None:
    auth_helpers._codex_login_cache["checked_at_monotonic"] = 0.0
    auth_helpers._codex_login_cache["status"] = {
        "available": False,
        "logged_in": False,
        "detail": "not_checked",
    }
    auth_helpers._codex_login_cache["last_good_at_monotonic"] = 0.0


def test_sanitize_agent_attachments_filters_and_normalizes() -> None:
    out = auth_helpers.sanitize_agent_attachments(
        raw=[
            {"name": " report.csv ", "mime": "text/csv", "text_excerpt": "a,b,c"},
            {"name": "", "mime": "text/plain", "text_excerpt": "ignored"},
            {"name": "image.png", "mime": "image/png", "path": "/tmp/image.png"},
        ],
        safe_upload_filename_fn=lambda s: s.strip(),
        attachment_kind_fn=lambda mime, name: "csv" if "csv" in mime else "binary",
    )
    assert len(out) == 2
    assert out[0]["name"] == "report.csv"
    assert out[0]["kind"] == "csv"
    assert out[1]["name"] == "image.png"


def test_codex_cli_login_status_not_installed(monkeypatch: Any) -> None:
    _reset_login_cache()

    def _raise_file_not_found(*args: Any, **kwargs: Any) -> Any:
        raise FileNotFoundError()

    monkeypatch.setattr(auth_helpers.subprocess, "run", _raise_file_not_found)
    status = auth_helpers.codex_cli_login_status()
    assert status["available"] is False
    assert status["logged_in"] is False
    assert status["detail"] == "codex_not_installed"


def test_codex_cli_login_status_logged_in(monkeypatch: Any) -> None:
    _reset_login_cache()
    monkeypatch.setattr(auth_helpers.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(
        auth_helpers.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout="Logged in using token", stderr=""
        ),
    )
    status = auth_helpers.codex_cli_login_status()
    assert status["available"] is True
    assert status["logged_in"] is True


def test_codex_cli_login_status_uses_stale_cache_for_transient_errors(
    monkeypatch: Any,
) -> None:
    _reset_login_cache()
    auth_helpers._codex_login_cache["status"] = {
        "available": True,
        "logged_in": True,
        "detail": "Logged in using token",
    }
    auth_helpers._codex_login_cache["last_good_at_monotonic"] = 50.0
    auth_helpers._codex_login_cache["checked_at_monotonic"] = 0.0
    monkeypatch.setattr(auth_helpers.time, "monotonic", lambda: 200.0)

    def _raise_runtime(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("probe timeout")

    monkeypatch.setattr(auth_helpers.subprocess, "run", _raise_runtime)
    status = auth_helpers.codex_cli_login_status()
    assert status["logged_in"] is True
    assert status.get("stale") is True
    assert str(status.get("detail", "")).startswith("stale_login_cache:")


def test_codex_cli_login_status_does_not_stale_on_explicit_logout(
    monkeypatch: Any,
) -> None:
    _reset_login_cache()
    auth_helpers._codex_login_cache["status"] = {
        "available": True,
        "logged_in": True,
        "detail": "Logged in using token",
    }
    auth_helpers._codex_login_cache["last_good_at_monotonic"] = 50.0
    auth_helpers._codex_login_cache["checked_at_monotonic"] = 0.0
    monkeypatch.setattr(auth_helpers.time, "monotonic", lambda: 300.0)
    monkeypatch.setattr(
        auth_helpers.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1, stdout="Not logged in", stderr=""
        ),
    )
    status = auth_helpers.codex_cli_login_status()
    assert status["logged_in"] is False
    assert status.get("stale") is not True

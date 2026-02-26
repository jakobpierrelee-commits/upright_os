"""
Authentication route handlers extracted from server.py (Phase B, Slice 5).

These handlers manage user registration, login, logout, and API key operations.
"""
from typing import Any, Dict, Tuple

try:
    from app.bridge.clean_ai import (
        build_auth_openai_status_payload,
        build_auth_session_payload,
        build_auth_user_payload,
    )
    from app.bridge.clean_misc import (
        build_reset_payload,
        build_result_payload,
    )
except ImportError:
    from clean_ai import (  # type: ignore
        build_auth_openai_status_payload,
        build_auth_session_payload,
        build_auth_user_payload,
    )
    from clean_misc import (  # type: ignore
        build_reset_payload,
        build_result_payload,
    )


def handle_auth_register(
    *,
    body: Dict[str, Any],
    auth: Any,
) -> Tuple[int, Dict[str, Any]]:
    """Handle /auth/register POST request."""
    email = str(body.get("email", ""))
    password = str(body.get("password", ""))
    out = auth.register(email, password)
    return 200, build_auth_session_payload(
        session=out,
        user=out.get("user"),
    )


def handle_auth_login(
    *,
    body: Dict[str, Any],
    auth: Any,
) -> Tuple[int, Dict[str, Any]]:
    """Handle /auth/login POST request."""
    email = str(body.get("email", ""))
    password = str(body.get("password", ""))
    out = auth.login(email, password)
    return 200, build_auth_session_payload(
        session=out,
        user=out.get("user"),
    )


def handle_auth_logout(
    *,
    tok: str,
    auth: Any,
) -> Tuple[int, Dict[str, Any]]:
    """Handle /auth/logout POST request."""
    auth.logout(tok)
    return 200, {"ok": True}


def handle_auth_password_reset_request(
    *,
    body: Dict[str, Any],
    auth: Any,
) -> Tuple[int, Dict[str, Any]]:
    """Handle /auth/password-reset/request POST request."""
    email = str(body.get("email", ""))
    out = auth.request_password_reset(email)
    return 200, build_reset_payload(reset=out)


def handle_auth_password_reset_confirm(
    *,
    body: Dict[str, Any],
    auth: Any,
) -> Tuple[int, Dict[str, Any]]:
    """Handle /auth/password-reset/confirm POST request."""
    email = str(body.get("email", ""))
    token = str(body.get("token", ""))
    new_password = str(body.get("new_password", ""))
    auth.confirm_password_reset(email, token, new_password)
    return 200, build_result_payload(result="password_reset")


def handle_auth_openai_key_set(
    *,
    body: Dict[str, Any],
    me: Dict[str, Any],
    auth: Any,
) -> Tuple[int, Dict[str, Any]]:
    """Handle /auth/openai-key POST request."""
    api_key = str(body.get("api_key", ""))
    model = str(body.get("model", "gpt-5-codex"))
    out = auth.set_openai_key(int(me["id"]), api_key, model)
    return 200, build_auth_openai_status_payload(openai=out)


def handle_auth_openai_key_delete(
    *,
    me: Dict[str, Any],
    auth: Any,
) -> Tuple[int, Dict[str, Any]]:
    """Handle /auth/openai-key/delete POST request."""
    out = auth.clear_openai_key(int(me["id"]))
    return 200, build_auth_openai_status_payload(openai=out)


def handle_auth_me_get(
    *,
    me: Dict[str, Any],
) -> Tuple[int, Dict[str, Any]]:
    """Handle /auth/me GET request."""
    return 200, build_auth_user_payload(user=me)

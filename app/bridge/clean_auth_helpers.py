from __future__ import annotations

import subprocess
import threading
import time
from typing import Any, Callable, Dict


_codex_login_cache_lock = threading.Lock()
_codex_login_cache: Dict[str, Any] = {
    "checked_at_monotonic": 0.0,
    "status": {"available": False, "logged_in": False, "detail": "not_checked"},
    "last_good_at_monotonic": 0.0,
}


def sanitize_agent_attachments(
    *,
    raw: Any,
    safe_upload_filename_fn: Callable[[str], str],
    attachment_kind_fn: Callable[[str, str], str],
) -> list[Dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[Dict[str, Any]] = []
    for item in raw[:8]:
        if not isinstance(item, dict):
            continue
        name = safe_upload_filename_fn(str(item.get("name", "")))
        mime = str(item.get("mime", "")).strip() or "application/octet-stream"
        kind = str(item.get("kind", "")).strip().lower() or attachment_kind_fn(
            mime, name
        )
        path = str(item.get("path", "")).strip()
        text_excerpt = str(item.get("text_excerpt", ""))[:16000]
        size = int(item.get("size", 0) or 0)
        if not name or (not path and not text_excerpt):
            continue
        out.append(
            {
                "name": name,
                "mime": mime,
                "kind": kind,
                "path": path,
                "size": size,
                "text_excerpt": text_excerpt,
            }
        )
    return out


def codex_cli_login_status() -> Dict[str, Any]:
    now = time.monotonic()
    with _codex_login_cache_lock:
        checked_at = float(_codex_login_cache.get("checked_at_monotonic", 0.0) or 0.0)
        cached = _codex_login_cache.get("status")
        if isinstance(cached, dict) and (now - checked_at) < 20.0:
            return dict(cached)

    prior_status: Dict[str, Any] = {}
    prior_good_at = 0.0
    with _codex_login_cache_lock:
        if isinstance(_codex_login_cache.get("status"), dict):
            prior_status = dict(_codex_login_cache["status"])
        prior_good_at = float(
            _codex_login_cache.get("last_good_at_monotonic", 0.0) or 0.0
        )

    status: Dict[str, Any]
    try:
        proc = subprocess.run(
            ["codex", "login", "status"],
            capture_output=True,
            text=True,
            timeout=4,
        )
    except FileNotFoundError:
        status = {
            "available": False,
            "logged_in": False,
            "detail": "codex_not_installed",
        }
    except Exception as exc:
        status = {
            "available": True,
            "logged_in": False,
            "detail": f"codex_status_error:{exc}",
        }
    else:
        txt = f"{proc.stdout}\n{proc.stderr}".strip()
        logged_in = proc.returncode == 0 and "logged in" in txt.lower()
        status = {
            "available": True,
            "logged_in": bool(logged_in),
            "detail": txt[:240],
        }

    detail_norm = str(status.get("detail", "")).strip().lower()
    explicitly_logged_out = ("not logged in" in detail_norm) or (
        "login required" in detail_norm
    )
    transient_probe_failure = detail_norm.startswith("codex_status_error:")
    if (
        not bool(status.get("logged_in"))
        and not explicitly_logged_out
        and transient_probe_failure
        and bool(prior_status.get("logged_in"))
        and (prior_good_at > 0.0)
    ):
        status = {
            "available": True,
            "logged_in": True,
            "detail": f"stale_login_cache:{str(status.get('detail', 'status_probe_failed'))[:180]}",
            "stale": True,
        }

    with _codex_login_cache_lock:
        _codex_login_cache["checked_at_monotonic"] = now
        _codex_login_cache["status"] = dict(status)
        if bool(status.get("logged_in")):
            _codex_login_cache["last_good_at_monotonic"] = now

    return dict(status)

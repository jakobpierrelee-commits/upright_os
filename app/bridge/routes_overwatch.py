"""
Overwatch route handlers extracted from server.py (Phase B+).

These handlers manage system-wide status and health monitoring.
"""

from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from app.bridge.clean_misc import build_overwatch_payload
except ImportError:
    from clean_misc import build_overwatch_payload  # type: ignore


def handle_overwatch_status_get(
    *,
    query: Dict[str, List[str]],
    cached_probe_fn: Callable[[str], Optional[Dict[str, Any]]],
    store_probe_fn: Callable[[str, Dict[str, Any]], None],
    gateway: Any,
    firmware: Any,
    run_compat_probe_fn: Callable[..., Dict[str, Any]],
    run_connect_probe_fn: Callable[..., Dict[str, Any]],
    build_overwatch_report_fn: Callable[..., Dict[str, Any]],
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /overwatch/status GET request.

    Returns (status_code, payload).
    """
    force_refresh = str((query.get("refresh", ["0"]) or ["0"])[0]).strip().lower() in {
        "1",
        "true",
        "yes",
    }

    if not force_refresh:
        cached = cached_probe_fn("overwatch")
        if cached is not None:
            return 200, build_overwatch_payload(overwatch=cached)

    compat = cached_probe_fn("compat")
    if compat is None:
        if int(gateway.health().get("queue_depth", 0) or 0) <= 2:
            try:
                compat = run_compat_probe_fn(gateway)
                store_probe_fn("compat", compat)
            except Exception:
                compat = {
                    "ok": False,
                    "missing_commands": [],
                    "missing_fields": [],
                }
        else:
            compat = {
                "ok": False,
                "missing_commands": [],
                "missing_fields": [],
            }

    connect = cached_probe_fn("connect")
    if connect is None:
        if int(gateway.health().get("queue_depth", 0) or 0) <= 2:
            try:
                connect = run_connect_probe_fn(gateway)
                store_probe_fn("connect", connect)
            except Exception:
                connect = {"ok": False, "confidence_pct": 0}
        else:
            connect = {"ok": False, "confidence_pct": 0}

    report = build_overwatch_report_fn(
        gateway=gateway,
        firmware=firmware,
        compat=compat if isinstance(compat, dict) else None,
        connect=connect if isinstance(connect, dict) else None,
    )
    store_probe_fn("overwatch", report)
    return 200, build_overwatch_payload(overwatch=report)

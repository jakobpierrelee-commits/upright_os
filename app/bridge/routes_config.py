"""
Config route handlers extracted from server.py (Phase B+).

These handlers manage configuration snapshots and history.
"""
from typing import Any, Callable, Dict, List, Tuple

try:
    from app.bridge.clean_misc import build_snapshots_payload
except ImportError:
    from clean_misc import build_snapshots_payload  # type: ignore


def handle_config_snapshots_get(
    *,
    query: Dict[str, List[str]],
    config_history: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /config/snapshots GET request.

    Returns (status_code, payload).
    """
    limit = int((query.get("limit", ["30"]) or ["30"])[0] or 30)
    return 200, build_snapshots_payload(
        snapshots=config_history.list_snapshots(limit=limit)
    )

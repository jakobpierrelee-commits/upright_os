"""
Design memory route handlers extracted from server.py (Phase B+).

These handlers manage design memory operations including rating and reporting.
"""
from typing import Any, Callable, Dict, Tuple

try:
    from app.bridge.clean_probe import (
        build_design_memory_best_payload,
        build_design_memory_payload,
    )
    from app.bridge.clean_misc import build_design_payload
except ImportError:
    from clean_probe import (  # type: ignore
        build_design_memory_best_payload,
        build_design_memory_payload,
    )
    from clean_misc import build_design_payload  # type: ignore


def handle_design_memory_rate(
    *,
    body: Dict[str, Any],
    design_memory: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /design-memory/rate POST request.

    Returns (status_code, payload).
    """
    session_key = str(body.get("session_key", "")).strip() or "local:app_dev"
    design_id = str(body.get("design_id", "")).strip()
    rating = str(body.get("rating", "")).strip().lower()
    note = str(body.get("note", "")).strip()
    try:
        row = design_memory.rate(
            design_id=design_id,
            rating=rating,
            note=note,
            source="user_rating",
            session_key=session_key,
        )
    except RuntimeError as exc:
        err = str(exc)
        if err == "design_not_found":
            return 404, {"ok": False, "error": err}
        return 400, {"ok": False, "error": err}
    return 200, build_design_payload(design=row)

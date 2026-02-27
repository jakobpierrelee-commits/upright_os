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


def handle_design_memory_list_get(
    *,
    query: Dict[str, Any],
    design_memory: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /design-memory GET request.

    Returns (status_code, payload).
    """
    n_raw = str((query.get("limit") or ["30"])[0]).strip()
    session_key = str((query.get("session_key") or [""])[0]).strip()
    profile_id = str((query.get("profile_id") or [""])[0]).strip()
    try:
        n = int(n_raw)
    except Exception:
        n = 30
    rows = design_memory.list_recent(limit=n)
    if session_key:
        rows = [
            r
            for r in rows
            if str(r.get("last_session_key", "")).strip() == session_key
        ]
    if profile_id:
        rows = [
            r
            for r in rows
            if str(r.get("profile_id", "")).strip() == profile_id
        ]
    return 200, build_design_memory_payload(design_memory=rows)


def handle_design_memory_best_get(
    *,
    query: Dict[str, Any],
    design_memory: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /design-memory/best GET request.

    Returns (status_code, payload).
    """
    session_key = str((query.get("session_key") or [""])[0]).strip()
    profile_id = str((query.get("profile_id") or [""])[0]).strip()
    return 200, build_design_memory_best_payload(
        best_design=design_memory.best(
            session_key=session_key,
            profile_id=profile_id,
        )
    )


def handle_design_memory_report_success(
    *,
    body: Dict[str, Any],
    firmware: Any,
    design_memory: Any,
    current_runtime_identity_fn: Callable[[], Dict[str, Any]],
    current_sketch_hash_fn: Callable[[], str],
    design_evidence_snapshot_fn: Callable[[], Dict[str, Any]],
) -> Tuple[int, Dict[str, Any]]:
    """Handle /design-memory/report-success POST request."""
    session_key = str(body.get("session_key", "")).strip() or "local:app_dev"
    source = str(body.get("source", "user_report")).strip() or "user_report"
    note = str(body.get("note", "")).strip()
    success = bool(body.get("success", True))
    profile_id = str(body.get("profile_id", "")).strip()
    profile_label = str(body.get("profile_label", "")).strip()
    sketch_revision = str(body.get("sketch_revision", "")).strip()
    sketch_hash = str(body.get("sketch_hash", "")).strip()
    test_type = str(body.get("test_type", "")).strip()
    observation = body.get("observation") if isinstance(body.get("observation"), dict) else {}
    
    if not observation:
        fw_status = firmware.status()
        fw_defaults = fw_status.get("defaults", {}) if isinstance(fw_status, dict) else {}
        runtime = current_runtime_identity_fn()
        observation = {
            "runtime_version": runtime.get("runtime_version", ""),
            "tune_version": runtime.get("tune_version", ""),
            "ident": runtime.get("ident", ""),
            "hash": runtime.get("hash", ""),
            "profile_id": profile_id,
            "profile_label": profile_label,
            "sketch_revision": sketch_revision,
            "sketch_hash": sketch_hash or current_sketch_hash_fn(),
            "test_type": test_type,
            "fqbn": str(fw_defaults.get("fqbn", "") or "").strip(),
            "port": str(fw_defaults.get("port", "") or "").strip(),
            "evidence": design_evidence_snapshot_fn(),
        }
    elif not isinstance(observation.get("evidence"), dict):
        observation["evidence"] = design_evidence_snapshot_fn()
    
    row = design_memory.report(
        session_key=session_key,
        observation=observation,
        success=success,
        source=source,
        note=note,
    )
    return 200, build_design_payload(design=row)

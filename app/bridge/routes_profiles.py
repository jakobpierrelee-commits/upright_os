"""
Profiles route handlers extracted from server.py (Phase B/C).

These handlers manage profile list, save, activate, delete, validate, and hardware registry.
"""
from typing import Any, Dict, List, Tuple

try:
    from app.bridge.clean_misc import (
        build_active_profiles_payload,
        build_profiles_list_payload,
        build_saved_profiles_payload,
        build_validation_payload,
    )
except ImportError:
    from clean_misc import (  # type: ignore
        build_active_profiles_payload,
        build_profiles_list_payload,
        build_saved_profiles_payload,
        build_validation_payload,
    )

try:
    from app.bridge.clean_profiles import (
        build_profiles_payload,
        build_profiles_hardware_payload,
    )
except ImportError:
    from clean_profiles import (  # type: ignore
        build_profiles_payload,
        build_profiles_hardware_payload,
    )


def handle_profiles_list(
    *,
    profiles: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /profiles GET request.

    Returns (status_code, payload).
    """
    return 200, build_profiles_payload(profiles_state=profiles.list())


def handle_profiles_hardware(
    *,
    firmware: Any,
    build_hardware_registry_fn: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /profiles/hardware GET request.

    Returns (status_code, payload).
    """
    targets = firmware.list_targets()
    registry = build_hardware_registry_fn(targets)
    return 200, build_profiles_hardware_payload(registry=registry)


def handle_profiles_save(
    *,
    body: Dict[str, Any],
    profiles: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /profiles/save POST request.

    Returns (status_code, payload).
    """
    prof = body.get("profile")
    if not isinstance(prof, dict):
        return 400, {"ok": False, "error": "profile_object_required"}
    saved = profiles.save(prof)
    return 200, build_saved_profiles_payload(saved=saved, profiles=profiles.list())


def handle_profiles_activate(
    *,
    body: Dict[str, Any],
    profiles: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /profiles/activate POST request.

    Returns (status_code, payload).
    """
    profile_id = str(body.get("profile_id", "")).strip()
    if not profile_id:
        return 400, {"ok": False, "error": "profile_id_required"}
    validation = body.get("validation")
    if not isinstance(validation, dict) or not bool(validation.get("ok", False)):
        return 409, {"ok": False, "error": "validation_required_before_activation"}
    out = profiles.activate(profile_id)
    return 200, build_active_profiles_payload(active=out, profiles=profiles.list())


def handle_profiles_delete(
    *,
    body: Dict[str, Any],
    profiles: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /profiles/delete POST request.

    Returns (status_code, payload).
    """
    profile_id = str(body.get("profile_id", "")).strip()
    if not profile_id:
        return 400, {"ok": False, "error": "profile_id_required"}
    out = profiles.delete(profile_id)
    return 200, build_profiles_list_payload(profiles=out)


def handle_profiles_validate(
    *,
    body: Dict[str, Any],
    profiles: Any,
    gateway: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /profiles/validate POST request.

    Returns (status_code, payload).
    """
    duration_s = float(body.get("duration_s", 12.0))
    sample_interval_s = float(body.get("sample_interval_s", 0.25))
    report = profiles.validate(
        gateway,
        duration_s=duration_s,
        sample_interval_s=sample_interval_s,
    )
    return 200, build_validation_payload(validation=report)

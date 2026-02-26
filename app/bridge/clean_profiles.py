from __future__ import annotations

from typing import Any, Callable, Dict, Optional


CompatFn = Callable[..., Dict[str, Any]]


def _active_profile_from_state(
    profiles_state: Dict[str, Any],
) -> tuple[str, Optional[Dict[str, Any]]]:
    active_id = str(profiles_state.get("active_profile_id") or "").strip()
    active_profile = next(
        (
            p
            for p in list(profiles_state.get("profiles") or [])
            if isinstance(p, dict) and str(p.get("profile_id", "")).strip() == active_id
        ),
        None,
    )
    return active_id, active_profile if isinstance(active_profile, dict) else None


def build_profiles_payload(*, profiles_state: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "profiles": profiles_state}


def build_profiles_hardware_payload(*, registry: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "registry": registry}


def build_runtime_manifest_compat_payload(
    *,
    manifest_check: Dict[str, Any],
    profiles_state: Dict[str, Any],
    targets: Dict[str, Any],
    compatibility_fn: CompatFn,
) -> Dict[str, Any]:
    active_id, active_profile = _active_profile_from_state(profiles_state)
    compat = compatibility_fn(
        manifest_validation=manifest_check,
        active_profile=active_profile,
        targets=targets,
    )
    return {
        "ok": bool(compat.get("ok", False)),
        "compatibility": compat,
        "active_profile_id": active_id or None,
        "manifest_validation": manifest_check,
    }

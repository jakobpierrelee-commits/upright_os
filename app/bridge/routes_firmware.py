"""
Firmware route handlers extracted from server.py (Phase B/C).

These handlers manage firmware status, compilation, upload, and generation operations.
"""
from typing import Any, Callable, Dict, List, Tuple
from urllib.parse import parse_qs

try:
    from app.bridge.clean_misc import (
        build_boards_payload,
        build_docs_pack_payload,
        build_firmware_result_payload,
        build_picked_payload,
        build_sketch_payload,
        build_sketch_write_payload,
        build_targets_payload,
        build_unified_payload,
    )
except ImportError:
    from clean_misc import (  # type: ignore
        build_boards_payload,
        build_docs_pack_payload,
        build_firmware_result_payload,
        build_picked_payload,
        build_sketch_payload,
        build_sketch_write_payload,
        build_targets_payload,
        build_unified_payload,
    )

try:
    from app.bridge.clean_firmware import (
        build_firmware_artifacts_payload,
        build_firmware_sketch_folders_payload,
        build_firmware_status_payload,
        build_runtime_manifest_validate_payload,
    )
except ImportError:
    from clean_firmware import (  # type: ignore
        build_firmware_artifacts_payload,
        build_firmware_sketch_folders_payload,
        build_firmware_status_payload,
        build_runtime_manifest_validate_payload,
    )

try:
    from app.bridge.clean_serial import build_unified_schema_payload
except ImportError:
    from clean_serial import build_unified_schema_payload  # type: ignore

try:
    from app.bridge.clean_profiles import build_runtime_manifest_compat_payload
except ImportError:
    from clean_profiles import build_runtime_manifest_compat_payload  # type: ignore

try:
    from app.bridge.clean_contracts import validate_firmware_targets_response
except ImportError:
    from clean_contracts import validate_firmware_targets_response  # type: ignore


# --- GET Handlers ---


def handle_firmware_status_get(
    *,
    firmware: Any,
) -> Tuple[int, Dict[str, Any]]:
    """Handle /firmware/status GET request."""
    return 200, build_firmware_status_payload(firmware_status=firmware.status())


def handle_firmware_artifacts_get(
    *,
    firmware: Any,
    query: Dict[str, List[str]],
) -> Tuple[int, Dict[str, Any]]:
    """Handle /firmware/artifacts GET request."""
    n_raw = str((query.get("limit") or ["20"])[0]).strip()
    try:
        n = int(n_raw)
    except Exception:
        n = 20
    return 200, build_firmware_artifacts_payload(
        firmware_artifacts=firmware.list_run_artifacts(limit=n)
    )


def handle_firmware_unified_schema_get(
    *,
    firmware: Any,
) -> Tuple[int, Dict[str, Any]]:
    """Handle /firmware/unified-schema GET request."""
    return 200, build_unified_schema_payload(schema=firmware.unified_schema())


def handle_firmware_sketch_get(
    *,
    firmware: Any,
    query: Dict[str, List[str]],
) -> Tuple[int, Dict[str, Any]]:
    """Handle /firmware/sketch GET request (read sketch)."""
    path = query.get("path", [None])[0]
    return 200, build_sketch_payload(sketch=firmware.read_sketch(path=path))


def handle_firmware_boards_get(
    *,
    firmware: Any,
) -> Tuple[int, Dict[str, Any]]:
    """Handle /firmware/boards GET request."""
    return 200, build_boards_payload(boards=firmware.list_boards())


def handle_firmware_targets_get(
    *,
    firmware: Any,
) -> Tuple[int, Dict[str, Any]]:
    """Handle /firmware/targets GET request."""
    payload = build_targets_payload(targets=firmware.list_targets())
    validate_firmware_targets_response(payload)
    return 200, payload


def handle_firmware_runtime_manifest_validate_get(
    *,
    firmware: Any,
    query: Dict[str, List[str]],
) -> Tuple[int, Dict[str, Any]]:
    """Handle /firmware/runtime-manifest/validate GET request."""
    sketch = str((query.get("sketch", [""]) or [""])[0] or "").strip() or None
    check = firmware.validate_runtime_manifest(sketch=sketch, require_exists=True)
    return 200, build_runtime_manifest_validate_payload(check=check)


def handle_firmware_runtime_manifest_compat_get(
    *,
    firmware: Any,
    profiles: Any,
    query: Dict[str, List[str]],
    compatibility_fn: Callable[..., Any],
) -> Tuple[int, Dict[str, Any]]:
    """Handle /firmware/runtime-manifest/compat GET request."""
    sketch = str((query.get("sketch", [""]) or [""])[0] or "").strip() or None
    manifest_check = firmware.validate_runtime_manifest(sketch=sketch, require_exists=True)
    return 200, build_runtime_manifest_compat_payload(
        manifest_check=manifest_check,
        profiles_state=profiles.list(),
        targets=firmware.list_targets(),
        compatibility_fn=compatibility_fn,
    )


def handle_firmware_sketch_folders_get(
    *,
    firmware: Any,
) -> Tuple[int, Dict[str, Any]]:
    """Handle /firmware/sketch-folders GET request."""
    return 200, build_firmware_sketch_folders_payload(
        sketch_folders=firmware.list_sketch_folders()
    )


def handle_firmware_check_post(
    *,
    firmware: Any,
) -> Tuple[int, Dict[str, Any]]:
    """Handle /firmware/check POST request."""
    try:
        from app.bridge.clean_misc import build_firmware_check_payload
    except ImportError:
        from clean_misc import build_firmware_check_payload  # type: ignore
    return 200, build_firmware_check_payload(firmware_check=firmware.check())


# --- POST Handlers (existing) ---


def handle_firmware_compile(
    *,
    body: Dict[str, Any],
    firmware: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /firmware/compile POST request.

    Returns (status_code, payload).
    """
    st = firmware.compile(
        sketch=body.get("sketch"),
        fqbn=body.get("fqbn"),
    )
    return 200, build_firmware_result_payload(firmware=st)


def handle_firmware_upload(
    *,
    body: Dict[str, Any],
    firmware: Any,
    prearm_safety: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /firmware/upload POST request.

    Returns (status_code, payload).
    """
    st = firmware.upload(
        sketch=body.get("sketch"),
        fqbn=body.get("fqbn"),
        port=body.get("port"),
    )
    prearm_safety.require("firmware_upload")
    return 200, build_firmware_result_payload(firmware=st)


def handle_firmware_upload_guarded(
    *,
    body: Dict[str, Any],
    firmware: Any,
    gateway: Any,
    prearm_safety: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /firmware/upload-guarded POST request.

    Returns (status_code, payload).
    """
    st = firmware.upload_guarded(
        gateway=gateway,
        sketch=body.get("sketch"),
        fqbn=body.get("fqbn"),
        port=body.get("port"),
    )
    prearm_safety.require("firmware_upload_guarded")
    return 200, build_firmware_result_payload(firmware=st)


def handle_firmware_install_cli(
    *,
    firmware: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /firmware/install-cli POST request.

    Returns (status_code, payload).
    """
    st = firmware.install_cli()
    return 200, build_firmware_result_payload(firmware=st)


def handle_firmware_sketch_write(
    *,
    body: Dict[str, Any],
    firmware: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /firmware/sketch POST request (write sketch).

    Returns (status_code, payload).
    """
    content = str(body.get("content", ""))
    path = body.get("path")
    profile = body.get("profile")
    sk = firmware.write_sketch(
        content=content,
        path=path,
        profile=profile if isinstance(profile, dict) else None,
    )
    return 200, build_sketch_write_payload(sketch=sk)


def handle_firmware_sketch_folder_pick(
    *,
    firmware: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /firmware/sketch-folder/pick POST request.

    Returns (status_code, payload).
    """
    picked = firmware.pick_sketch_folder()
    return 200, build_picked_payload(picked=picked)


def handle_firmware_generate_unified(
    *,
    body: Dict[str, Any],
    firmware: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /firmware/generate-unified POST request.

    Returns (status_code, payload).
    """
    profile = body.get("profile")
    if not isinstance(profile, dict):
        return 400, {"ok": False, "error": "profile_object_required"}
    sketch_name = body.get("sketch_name")
    out = firmware.generate_unified(
        profile=profile,
        sketch_name=str(sketch_name) if sketch_name else None,
    )
    return 200, build_unified_payload(unified=out)


def handle_firmware_generate_docs_pack(
    *,
    body: Dict[str, Any],
    firmware: Any,
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /firmware/generate-docs-pack POST request.

    Returns (status_code, payload).
    """
    profile = body.get("profile")
    if not isinstance(profile, dict):
        return 400, {"ok": False, "error": "profile_object_required"}
    sketch_name = body.get("sketch_name")
    sketch_content = body.get("sketch_content")
    sketch_path = body.get("sketch_path")
    force_regenerate = bool(body.get("force_regenerate", False))
    out = firmware.generate_docs_pack(
        profile=profile,
        sketch_name=str(sketch_name) if sketch_name else None,
        sketch_content=str(sketch_content) if isinstance(sketch_content, str) else None,
        sketch_path=str(sketch_path) if isinstance(sketch_path, str) else None,
        force_regenerate=force_regenerate,
    )
    return 200, build_docs_pack_payload(docs_pack=out)

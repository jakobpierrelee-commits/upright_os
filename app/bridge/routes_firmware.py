"""
Firmware route handlers extracted from server.py (Phase C).

These handlers manage firmware compilation, upload, and generation operations.
"""
from typing import Any, Dict, Tuple

try:
    from app.bridge.clean_misc import (
        build_docs_pack_payload,
        build_firmware_result_payload,
        build_picked_payload,
        build_sketch_write_payload,
        build_unified_payload,
    )
except ImportError:
    from clean_misc import (  # type: ignore
        build_docs_pack_payload,
        build_firmware_result_payload,
        build_picked_payload,
        build_sketch_write_payload,
        build_unified_payload,
    )


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

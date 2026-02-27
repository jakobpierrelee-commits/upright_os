"""
Route dispatch helpers for server.py.

Consolidates repetitive route handling patterns to reduce Handler class size.
"""

from typing import Any, Callable, Dict, Optional, Tuple

# Type aliases
RouteHandler = Callable[..., Tuple[int, Dict[str, Any]]]
DepsBuilder = Callable[[], Dict[str, Any]]


def dispatch_simple_post(
    path: str,
    body: Dict[str, Any],
    routes: Dict[str, Tuple[RouteHandler, DepsBuilder]],
) -> Optional[Tuple[int, Dict[str, Any]]]:
    """
    Dispatch a simple POST route that returns (code, payload).
    
    Returns None if path not found in routes.
    Returns (code, payload) if handled.
    """
    if path not in routes:
        return None
    handler, deps_builder = routes[path]
    deps = deps_builder()
    return handler(body=body, **deps)


def build_simple_post_routes(
    *,
    # Dependencies injected from server
    firmware: Any,
    profiles: Any,
    gateway: Any,
    control: Any,
    commissioning: Any,
    config_history: Any,
    host_capture: Any,
    design_memory: Any,
    # Handler functions
    handle_firmware_check_post: Any,
    handle_firmware_compile: Any,
    handle_firmware_upload: Any,
    handle_firmware_upload_guarded: Any,
    handle_firmware_install_cli: Any,
    handle_firmware_sketch_write: Any,
    handle_firmware_sketch_folder_pick: Any,
    handle_firmware_generate_unified: Any,
    handle_firmware_generate_docs_pack: Any,
    handle_profiles_validate: Any,
    handle_profiles_save: Any,
    handle_profiles_activate: Any,
    handle_profiles_delete: Any,
    handle_commissioning_run: Any,
    handle_commissioning_step: Any,
    handle_session_heartbeat: Any,
    handle_design_memory_rate: Any,
    # Payload builders
    build_session_heartbeat_payload: Any,
    prearm_safety: Any,
) -> Dict[str, Tuple[RouteHandler, DepsBuilder]]:
    """
    Build route dispatch table for simple POST routes.
    
    Returns dict mapping path -> (handler, deps_builder).
    """
    return {
        "/firmware/check": (
            handle_firmware_check_post,
            lambda: {"firmware": firmware},
        ),
        "/firmware/compile": (
            handle_firmware_compile,
            lambda: {"firmware": firmware},
        ),
        "/firmware/upload": (
            handle_firmware_upload,
            lambda: {"firmware": firmware, "prearm_safety": prearm_safety},
        ),
        "/firmware/upload-guarded": (
            handle_firmware_upload_guarded,
            lambda: {
                "firmware": firmware,
                "gateway": gateway,
                "prearm_safety": prearm_safety,
            },
        ),
        "/firmware/install-cli": (
            handle_firmware_install_cli,
            lambda: {"firmware": firmware},
        ),
        "/firmware/sketch": (
            handle_firmware_sketch_write,
            lambda: {"firmware": firmware},
        ),
        "/firmware/sketch-folder/pick": (
            handle_firmware_sketch_folder_pick,
            lambda: {"firmware": firmware},
        ),
        "/firmware/generate-unified": (
            handle_firmware_generate_unified,
            lambda: {"firmware": firmware},
        ),
        "/firmware/generate-docs-pack": (
            handle_firmware_generate_docs_pack,
            lambda: {"firmware": firmware},
        ),
        "/profiles/validate": (
            handle_profiles_validate,
            lambda: {"profiles": profiles, "gateway": gateway},
        ),
        "/profiles/save": (
            handle_profiles_save,
            lambda: {"profiles": profiles},
        ),
        "/profiles/activate": (
            handle_profiles_activate,
            lambda: {"profiles": profiles},
        ),
        "/profiles/delete": (
            handle_profiles_delete,
            lambda: {"profiles": profiles},
        ),
        "/commissioning/run": (
            handle_commissioning_run,
            lambda: {"gateway": gateway, "commissioning": commissioning},
        ),
        "/commissioning/step": (
            handle_commissioning_step,
            lambda: {},
        ),
        "/session/heartbeat": (
            handle_session_heartbeat,
            lambda: {
                "control": control,
                "build_session_heartbeat_payload_fn": build_session_heartbeat_payload,
            },
        ),
        "/design-memory/rate": (
            handle_design_memory_rate,
            lambda: {"design_memory": design_memory},
        ),
    }


def build_control_post_routes(
    *,
    gateway: Any,
    control: Any,
    config_history: Any,
    host_capture: Any,
    prearm_safety: Any,
    tuning_preflight: Any,
    # Handler functions
    handle_arm_prepare: Any,
    handle_arm_confirm: Any,
    handle_arm: Any,
    handle_disarm: Any,
    handle_estop_latch: Any,
    handle_estop_reset: Any,
    handle_cal_zero: Any,
    handle_savecfg: Any,
    handle_loadcfg: Any,
    handle_defaultcfg: Any,
    handle_command: Any,
    # Helper functions
    blocked_while_latched_fn: Any,
    require_action_allowed_fn: Any,
) -> Dict[str, Tuple[RouteHandler, DepsBuilder]]:
    """
    Build route dispatch table for control POST routes.
    """
    return {
        "/estop/latch": (
            handle_estop_latch,
            lambda: {"gateway": gateway, "control": control},
        ),
        "/estop/reset": (
            handle_estop_reset,
            lambda: {"gateway": gateway, "control": control},
        ),
        "/savecfg": (
            handle_savecfg,
            lambda: {"gateway": gateway, "control": control},
        ),
        "/loadcfg": (
            handle_loadcfg,
            lambda: {"gateway": gateway, "control": control},
        ),
        "/defaultcfg": (
            handle_defaultcfg,
            lambda: {"gateway": gateway, "control": control},
        ),
        "/command": (
            handle_command,
            lambda: {
                "gateway": gateway,
                "control": control,
                "blocked_while_latched_fn": blocked_while_latched_fn,
            },
        ),
    }

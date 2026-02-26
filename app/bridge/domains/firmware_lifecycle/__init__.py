"""
Firmware Lifecycle Domain

Handles firmware compilation, upload, recovery, and artifact management.

Note: FirmwareManager is currently defined inline in server.py.
This facade re-exports from clean_firmware_ops.py for the clean architecture handlers.
Full extraction of FirmwareManager planned for Phase D.
"""

# Re-export from existing modules (facade pattern)
try:
    from app.bridge.clean_firmware_ops import (
        handle_clean_firmware_compile,
        handle_clean_firmware_upload,
        handle_clean_known_good_recovery,
        handle_clean_upload_precheck,
        resolve_clean_upload_inputs,
    )
except ImportError:
    from clean_firmware_ops import (  # type: ignore
        handle_clean_firmware_compile,
        handle_clean_firmware_upload,
        handle_clean_known_good_recovery,
        handle_clean_upload_precheck,
        resolve_clean_upload_inputs,
    )

__all__ = [
    "handle_clean_firmware_compile",
    "handle_clean_firmware_upload",
    "handle_clean_known_good_recovery",
    "handle_clean_upload_precheck",
    "resolve_clean_upload_inputs",
]

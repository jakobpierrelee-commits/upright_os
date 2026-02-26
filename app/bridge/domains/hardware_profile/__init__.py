"""
Hardware Profile Domain

Handles robot profiles, manifests, and compatibility gates.

Note: RobotProfilesManager is currently defined inline in server.py.
This facade re-exports from clean_contracts.py for validation functions.
Full extraction planned for Phase D.
"""

# Re-export from existing modules (facade pattern)
try:
    from app.bridge.clean_contracts import (
        validate_clean_preflight_response,
        validate_firmware_targets_response,
        validate_prearm_precheck_response,
    )
except ImportError:
    from clean_contracts import (  # type: ignore
        validate_clean_preflight_response,
        validate_firmware_targets_response,
        validate_prearm_precheck_response,
    )

__all__ = [
    "validate_clean_preflight_response",
    "validate_firmware_targets_response",
    "validate_prearm_precheck_response",
]

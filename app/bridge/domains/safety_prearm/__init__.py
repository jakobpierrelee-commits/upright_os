"""
Safety Pre-Arm Domain

Handles preflight checks, pre-arm gates, and fail-closed behavior.
"""

# Re-export from existing modules (facade pattern)
try:
    from app.bridge.arm_safety import PreArmSafetyGate, run_prearm_hardware_check
except ImportError:
    from arm_safety import PreArmSafetyGate, run_prearm_hardware_check  # type: ignore

try:
    from app.bridge.clean_preflight import resolve_manifest_gates, run_clean_preflight
except ImportError:
    from clean_preflight import resolve_manifest_gates, run_clean_preflight  # type: ignore

__all__ = [
    "PreArmSafetyGate",
    "run_prearm_hardware_check",
    "resolve_manifest_gates",
    "run_clean_preflight",
]

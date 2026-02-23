import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from server import _runtime_manifest_profile_compatibility  # noqa: E402


def _targets() -> dict:
    return {
        "boards": [
            {
                "id": "nano",
                "family": "arduino_avr",
                "fqbn_base": "arduino:avr:nano",
                "bootloaders": [
                    {"id": "new", "fqbn_suffix": ""},
                    {"id": "old", "fqbn_suffix": ":cpu=atmega328old"},
                ],
            }
        ]
    }


def _manifest_validation_ok(fqbn: str) -> dict:
    return {
        "ok": True,
        "manifest": {
            "version": "runtime_manifest_v1",
            "board": {
                "id": "nano",
                "family": "arduino_avr",
                "fqbn": fqbn,
            },
            "interfaces": {
                "imu": {"protocol": "i2c"},
                "encoders": {"protocol": "quadrature"},
                "actuator": {"protocol": "gpio_dir_pwm"},
            },
            "telemetry_fields": [
                "mode",
                "ang",
                "raw",
                "gyro",
                "out",
                "fault",
                "estop",
                "set",
            ],
            "commands": ["GET", "ARM", "DISARM", "PID", "SETPOINT", "LIMITS"],
        },
    }


def test_manifest_profile_compat_passes_when_board_and_contract_match() -> None:
    active = {
        "board": {"fqbn": "arduino:avr:nano:cpu=atmega328old"},
        "probe": {
            "commands": ["GET", "ARM", "DISARM", "PID", "SETPOINT"],
            "compat": {
                "required_fields": ["mode", "ang", "raw", "gyro|gyr|gx", "out", "set"]
            },
        },
    }
    out = _runtime_manifest_profile_compatibility(
        manifest_validation=_manifest_validation_ok(
            "arduino:avr:nano:cpu=atmega328old"
        ),
        active_profile=active,
        targets=_targets(),
    )
    assert out["ok"] is True
    assert out["errors"] == []


def test_manifest_profile_compat_fails_on_board_mismatch() -> None:
    active = {"board": {"fqbn": "arduino:avr:uno"}, "probe": {}}
    out = _runtime_manifest_profile_compatibility(
        manifest_validation=_manifest_validation_ok("arduino:avr:nano"),
        active_profile=active,
        targets=_targets(),
    )
    assert out["ok"] is False
    assert "board_fqbn_mismatch" in out["errors"]


def test_manifest_profile_compat_warns_on_optional_profile_commands() -> None:
    active = {
        "board": {"fqbn": "arduino:avr:nano"},
        "probe": {"commands": ["GET", "ARM", "MOTION"]},
    }
    out = _runtime_manifest_profile_compatibility(
        manifest_validation=_manifest_validation_ok("arduino:avr:nano"),
        active_profile=active,
        targets=_targets(),
    )
    assert out["ok"] is True
    assert any(str(w).startswith("commands_optional_missing:") for w in out["warnings"])


def test_manifest_profile_compat_warns_on_protocol_mismatch() -> None:
    active = {
        "board": {"fqbn": "arduino:avr:nano"},
        "parts": {
            "imu": {"protocol": "spi"},
            "encoders": {"protocol": "quadrature"},
            "motor_driver": {"protocol": "gpio_dir_pwm"},
        },
        "pinmap": {
            "imu_bus": {"protocol": "spi"},
            "encoders": {"protocol": "quadrature"},
            "motor": {"protocol": "gpio_dir_pwm"},
        },
        "probe": {"commands": ["GET", "ARM", "DISARM", "PID", "SETPOINT"]},
    }
    out = _runtime_manifest_profile_compatibility(
        manifest_validation=_manifest_validation_ok("arduino:avr:nano"),
        active_profile=active,
        targets=_targets(),
    )
    assert out["ok"] is True
    assert any(str(w).startswith("protocol_mismatch:") for w in out["warnings"])
    assert out["checks"]["protocols"]["ok"] is False

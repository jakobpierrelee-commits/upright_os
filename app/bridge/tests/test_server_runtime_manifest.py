import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from server import _validate_runtime_manifest_v1  # noqa: E402


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


def test_runtime_manifest_v1_accepts_valid_manifest() -> None:
    manifest = {
        "version": "runtime_manifest_v1",
        "board": {
            "id": "nano",
            "family": "arduino_avr",
            "fqbn": "arduino:avr:nano:cpu=atmega328old",
        },
        "interfaces": {
            "imu": {"pins": {"sda": 18, "scl": 19}},
            "encoders": {
                "pins": {"left_a": 2, "left_b": 4, "right_a": 3, "right_b": 5}
            },
            "actuator": {
                "pins": {"left_pwm": 9, "left_dir": 7, "right_pwm": 10, "right_dir": 8}
            },
        },
        "telemetry_fields": ["mode", "ang", "raw", "gyro", "out", "fault", "estop"],
        "commands": ["GET", "ARM", "DISARM", "PID", "SETPOINT", "LIMITS"],
    }
    out = _validate_runtime_manifest_v1(manifest, _targets())
    assert out["ok"] is True
    assert out["errors"] == []


def test_runtime_manifest_v1_rejects_missing_required_command() -> None:
    manifest = {
        "version": "runtime_manifest_v1",
        "board": {
            "id": "nano",
            "family": "arduino_avr",
            "fqbn": "arduino:avr:nano",
        },
        "interfaces": {
            "imu": {"pins": {"sda": 18, "scl": 19}},
            "encoders": {"pins": {"left_a": 2, "left_b": 4}},
            "actuator": {
                "pins": {"left_pwm": 9, "left_dir": 7, "right_pwm": 10, "right_dir": 8}
            },
        },
        "telemetry_fields": ["mode", "ang", "raw", "gyro", "out", "fault", "estop"],
        "commands": ["GET", "ARM", "DISARM", "PID"],
    }
    out = _validate_runtime_manifest_v1(manifest, _targets())
    assert out["ok"] is False
    assert any("commands.missing:SETPOINT" in e for e in out["errors"])


def test_runtime_manifest_v1_rejects_pin_conflicts_and_out_of_range() -> None:
    manifest = {
        "version": "runtime_manifest_v1",
        "board": {
            "id": "nano",
            "family": "arduino_avr",
            "fqbn": "arduino:avr:nano",
        },
        "interfaces": {
            "imu": {"pins": {"sda": 22, "scl": 22}},
            "encoders": {"pins": {"left_a": 2, "left_b": 2}},
            "actuator": {
                "pins": {"left_pwm": 9, "left_dir": 7, "right_pwm": 10, "right_dir": 8}
            },
        },
        "telemetry_fields": ["mode", "ang", "raw", "gyr", "out", "fault", "estop"],
        "commands": ["GET", "ARM", "DISARM", "PID", "SETPOINT", "LIMITS"],
    }
    out = _validate_runtime_manifest_v1(manifest, _targets())
    assert out["ok"] is False
    assert any("out_of_range" in e for e in out["errors"])
    assert any("pin_conflict" in e for e in out["errors"])


def test_runtime_manifest_v1_rejects_unsupported_protocol_for_family() -> None:
    manifest = {
        "version": "runtime_manifest_v1",
        "board": {
            "id": "nano",
            "family": "arduino_avr",
            "fqbn": "arduino:avr:nano",
        },
        "interfaces": {
            "imu": {
                "protocol": "spi",
                "pins": {"miso": 12, "mosi": 11, "sck": 13, "cs": 10},
            },
            "encoders": {"protocol": "quadrature", "pins": {"left_a": 2, "left_b": 4}},
            "actuator": {
                "protocol": "gpio_dir_pwm",
                "pins": {"left_pwm": 9, "left_dir": 7, "right_pwm": 10, "right_dir": 8},
            },
        },
        "telemetry_fields": ["mode", "ang", "raw", "gyro", "out", "fault", "estop"],
        "commands": ["GET", "ARM", "DISARM", "PID", "SETPOINT", "LIMITS"],
    }
    out = _validate_runtime_manifest_v1(manifest, _targets())
    assert out["ok"] is False
    assert any(
        "interfaces.imu.protocol_not_supported_for_family" in e for e in out["errors"]
    )


def test_runtime_manifest_v1_rejects_missing_protocol_required_pins() -> None:
    manifest = {
        "version": "runtime_manifest_v1",
        "board": {
            "id": "nano",
            "family": "arduino_avr",
            "fqbn": "arduino:avr:nano",
        },
        "interfaces": {
            "imu": {"protocol": "i2c", "pins": {"sda": 18, "scl": 19}},
            "encoders": {"protocol": "quadrature", "pins": {"left_a": 2}},
            "actuator": {
                "protocol": "gpio_dir_pwm",
                "pins": {"left_pwm": 9, "right_pwm": 10, "right_dir": 8},
            },
        },
        "telemetry_fields": ["mode", "ang", "raw", "gyro", "out", "fault", "estop"],
        "commands": ["GET", "ARM", "DISARM", "PID", "SETPOINT", "LIMITS"],
    }
    out = _validate_runtime_manifest_v1(manifest, _targets())
    assert out["ok"] is False
    assert any(
        "interfaces.encoders.protocol_pin_group_missing:quadrature" in e
        for e in out["errors"]
    )
    assert any(
        "interfaces.actuator.protocol_pin_missing:gpio_dir_pwm.left_dir" in e
        for e in out["errors"]
    )


def test_runtime_manifest_v1_accepts_optional_mcu_topology() -> None:
    manifest = {
        "version": "runtime_manifest_v1",
        "board": {
            "id": "nano",
            "family": "arduino_avr",
            "fqbn": "arduino:avr:nano:cpu=atmega328old",
        },
        "interfaces": {
            "imu": {"pins": {"sda": 18, "scl": 19}},
            "encoders": {
                "pins": {"left_a": 2, "left_b": 4, "right_a": 3, "right_b": 5}
            },
            "actuator": {
                "pins": {"left_pwm": 9, "left_dir": 7, "right_pwm": 10, "right_dir": 8}
            },
        },
        "telemetry_fields": ["mode", "ang", "raw", "gyro", "out", "fault", "estop"],
        "commands": ["GET", "ARM", "DISARM", "PID", "SETPOINT", "LIMITS"],
        "mcu_topology": {
            "control_mcu": {
                "id": "control-main",
                "role": "control",
                "fqbn": "arduino:avr:nano:cpu=atmega328old",
            },
            "io_mcu": {"id": "io-rc", "role": "io"},
            "link": {"transport": "uart"},
            "command_namespaces": {"remote_control": "RC_"},
        },
    }
    out = _validate_runtime_manifest_v1(manifest, _targets())
    assert out["ok"] is True


def test_runtime_manifest_v1_rejects_invalid_mcu_topology() -> None:
    manifest = {
        "version": "runtime_manifest_v1",
        "board": {
            "id": "nano",
            "family": "arduino_avr",
            "fqbn": "arduino:avr:nano:cpu=atmega328old",
        },
        "interfaces": {
            "imu": {"pins": {"sda": 18, "scl": 19}},
            "encoders": {
                "pins": {"left_a": 2, "left_b": 4, "right_a": 3, "right_b": 5}
            },
            "actuator": {
                "pins": {"left_pwm": 9, "left_dir": 7, "right_pwm": 10, "right_dir": 8}
            },
        },
        "telemetry_fields": ["mode", "ang", "raw", "gyro", "out", "fault", "estop"],
        "commands": ["GET", "ARM", "DISARM", "PID", "SETPOINT", "LIMITS"],
        "mcu_topology": {
            "control_mcu": {"id": "", "role": "io"},
            "io_mcu": {"id": "same-id", "role": "wrong"},
            "link": {"transport": "usb"},
            "command_namespaces": {"remote_control": "RC"},
        },
    }
    # Force conflict id by matching control id once fixed from empty.
    manifest["mcu_topology"]["control_mcu"]["id"] = "same-id"
    out = _validate_runtime_manifest_v1(manifest, _targets())
    assert out["ok"] is False
    assert any("mcu_topology.control_mcu.role_invalid" in e for e in out["errors"])
    assert any("mcu_topology.io_mcu.role_invalid" in e for e in out["errors"])
    assert any(
        "mcu_topology.io_mcu.id_conflicts_with_control" in e for e in out["errors"]
    )
    assert any("mcu_topology.link.transport_invalid" in e for e in out["errors"])

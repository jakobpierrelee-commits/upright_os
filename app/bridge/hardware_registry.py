"""
Hardware registry builder extracted from server.py.

Provides hardware capability lookup and profile schema generation.
"""

from typing import Any, Dict, List

try:
    from app.bridge.manifest_helpers import (
        _family_capabilities,
        _protocol_schema,
    )
except ImportError:
    from manifest_helpers import (  # type: ignore
        _family_capabilities,
        _protocol_schema,
    )


def build_hardware_registry(targets: Dict[str, Any]) -> Dict[str, Any]:
    """Build hardware capability registry from targets configuration."""
    family_capabilities = _family_capabilities()
    protocol_schema = _protocol_schema()
    telemetry_core_fields = [
        "mode",
        "ang",
        "raw",
        "gyro|gyr|gx",
        "out",
        "fault",
        "estop",
    ]
    board_rows = []
    for row in list(targets.get("boards") or []):
        if not isinstance(row, dict):
            continue
        family = str(row.get("family", "")).strip() or "unknown"
        caps = family_capabilities.get(family, {})
        board_rows.append(
            {
                "id": str(row.get("id", "")).strip(),
                "label": str(row.get("label", "")).strip(),
                "family": family,
                "fqbn_base": str(row.get("fqbn_base", "")).strip(),
                "default_bootloader": str(row.get("default_bootloader", "")).strip(),
                "bootloaders": list(row.get("bootloaders") or []),
                "capabilities": {
                    "default_telemetry_hz": int(caps.get("default_telemetry_hz", 200)),
                    "default_telemetry_mode": str(
                        caps.get("default_telemetry_mode", "ascii_lowrate")
                    ),
                    "telemetry_modes": list(
                        caps.get("telemetry_modes") or ["ascii_lowrate"]
                    ),
                    "imu_protocols": list(caps.get("imu_protocols") or []),
                    "encoder_protocols": list(caps.get("encoder_protocols") or []),
                    "actuator_protocols": list(caps.get("actuator_protocols") or []),
                    "actuator_classes": list(caps.get("actuator_classes") or []),
                },
                "required_runtime_fields": list(telemetry_core_fields),
            }
        )

    return {
        "ok": True,
        "version": 1,
        "families": list(targets.get("families") or []),
        "boards": board_rows,
        "sensors": [
            {
                "id": "imu_mpu6050",
                "label": "MPU6050 IMU",
                "class": "imu",
                "supported_protocols": ["i2c"],
                "required_signals": ["accel", "gyro"],
                "typical_output_fields": ["ang", "raw", "gyro"],
            },
            {
                "id": "imu_bno085",
                "label": "BNO085/BNO080 IMU",
                "class": "imu",
                "supported_protocols": ["i2c", "uart", "spi"],
                "required_signals": ["quat|euler", "gyro"],
                "typical_output_fields": ["ang", "gyro"],
            },
            {
                "id": "enc_quadrature",
                "label": "Quadrature Encoder",
                "class": "encoder",
                "supported_protocols": ["quadrature"],
                "required_signals": ["A", "B"],
                "typical_output_fields": ["encL", "encR", "wpos", "wspd"],
            },
            {
                "id": "enc_hall",
                "label": "Hall Encoder",
                "class": "encoder",
                "supported_protocols": ["hall"],
                "required_signals": ["pulse"],
                "typical_output_fields": ["encL", "encR", "wpos", "wspd"],
            },
            {
                "id": "enc_spi_abs",
                "label": "SPI Absolute Encoder",
                "class": "encoder",
                "supported_protocols": ["spi"],
                "required_signals": ["angle"],
                "typical_output_fields": ["wpos", "wspd"],
            },
        ],
        "actuators": [
            {
                "id": "dual_dc_hbridge_pwm",
                "label": "Dual DC H-Bridge (PWM)",
                "class": "motor_driver",
                "required_channels": ["left_pwm", "right_pwm"],
            },
            {
                "id": "dual_dc_hbridge_dir_pwm",
                "label": "Dual DC H-Bridge (DIR+PWM)",
                "class": "motor_driver",
                "required_channels": ["left_dir", "left_pwm", "right_dir", "right_pwm"],
            },
            {
                "id": "bldc_foc",
                "label": "BLDC FOC Driver",
                "class": "motor_driver",
                "required_channels": ["left_phase", "right_phase"],
            },
        ],
        "profile_schema": {
            "required_profile_fields": [
                "profile_id",
                "label",
                "board",
                "parts",
                "pinmap",
            ],
            "required_board_fields": ["fqbn", "port"],
            "required_parts_fields": ["imu", "encoders", "motor_driver"],
            "required_pinmap_fields": ["imu_bus", "motor", "encoders"],
            "required_runtime_commands": ["GET", "ARM", "DISARM", "PID", "SETPOINT"],
            "required_runtime_telemetry": list(telemetry_core_fields),
            "optional_profile_fields": ["mcu_topology", "firmware.telemetry_mode"],
            "mcu_topology_schema": {
                "required_when_present": ["control_mcu"],
                "control_mcu_required_fields": ["id"],
                "io_mcu_required_fields_when_present": ["id"],
                "optional_fields": ["io_mcu", "link", "command_namespaces"],
                "recommended_remote_control_namespace_suffix": "_",
            },
        },
        "protocol_schema": protocol_schema,
        "templates": [
            {
                "id": "nano_balancer_v1",
                "label": "Nano Balancer Baseline",
                "board_family": "arduino_avr",
                "sensor_ids": ["imu_mpu6050", "enc_quadrature"],
                "actuator_ids": ["dual_dc_hbridge_dir_pwm"],
            },
            {
                "id": "teensy_balancer_v1",
                "label": "Teensy Performance Balancer",
                "board_family": "teensy",
                "sensor_ids": ["imu_bno085", "enc_spi_abs"],
                "actuator_ids": ["bldc_foc"],
                "reference_firmware_template": "app/bridge/firmware_templates/teensy41_reference_v1/teensy41_reference_v1.ino",
                "reference_runtime_manifest": "app/bridge/firmware_templates/teensy41_reference_v1/runtime_manifest_v1.json",
            },
            {
                "id": "esp32_balancer_v1",
                "label": "ESP32 Balancer",
                "board_family": "esp32",
                "sensor_ids": ["imu_mpu6050", "enc_quadrature"],
                "actuator_ids": ["dual_dc_hbridge_pwm"],
            },
        ],
    }

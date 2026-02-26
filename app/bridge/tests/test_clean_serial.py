import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from clean_serial import (
    build_diag_serial_payload,
    build_telemetry_adapters_payload,
    build_unified_schema_payload,
)


def test_build_diag_serial_payload_shape() -> None:
    payload = build_diag_serial_payload(
        serial={"connected": True, "port": "/dev/ttyUSB0"},
        control={"arm_prepared": False},
    )
    assert payload["ok"] is True
    assert payload["serial"]["connected"] is True
    assert payload["control"]["arm_prepared"] is False


def test_build_telemetry_adapters_payload_shape() -> None:
    payload = build_telemetry_adapters_payload(
        adapter={"name": "balance_v1"},
        adapters={"balance_v1": {}, "control_lab": {}},
        canonical_fields=["pitch", "roll", "yaw"],
    )
    assert payload["ok"] is True
    assert payload["adapter"]["name"] == "balance_v1"
    assert len(payload["adapters"]) == 2
    assert "pitch" in payload["canonical_fields"]


def test_build_unified_schema_payload_shape() -> None:
    payload = build_unified_schema_payload(
        schema={"version": "1.0", "fields": ["kp", "ki", "kd"]}
    )
    assert payload["ok"] is True
    assert payload["schema"]["version"] == "1.0"

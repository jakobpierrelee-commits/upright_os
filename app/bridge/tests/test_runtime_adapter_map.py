import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from server import _normalize_status_for_hud


def test_normalize_status_maps_teensy_aliases_to_canonical_fields() -> None:
    raw = {
        "state": "BALANCING",
        "angle": "1.25",
        "accel_angle": "1.30",
        "gyro_rate": "0.07",
        "motor_out": "42",
        "fault_code": "0",
        "estop_latched": "0",
    }
    out = _normalize_status_for_hud(raw)
    status = out["status"]
    adapter = out["adapter"]
    assert status["mode"] == "BALANCING"
    assert status["ang"] == "1.25"
    assert status["raw"] == "1.30"
    assert status["gyro"] == "0.07"
    assert status["out"] == "42"
    assert status["fault"] == "0"
    assert status["estop"] == "0"
    assert adapter["id"] in {"teensy_balance_v1", "generic_v1"}


def test_normalize_status_keeps_existing_canonical_values() -> None:
    raw = {
        "mode": "SAFE_IDLE",
        "ang": "0.0",
        "raw": "0.0",
        "gyro": "0.0",
        "out": "0.0",
        "fault": "0",
        "estop": "0",
        "angle": "999.0",
    }
    out = _normalize_status_for_hud(raw)
    status = out["status"]
    assert status["ang"] == "0.0"
    assert status["gyro"] == "0.0"
    assert status["out"] == "0.0"
    assert status["fault"] == "0"
    assert status["estop"] == "0"

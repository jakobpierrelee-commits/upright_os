import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from server import (
    HardwareContextStore,
    MissionMemoryStore,
    _format_hardware_context_notice,
)  # noqa: E402


def test_mission_memory_upsert_get_and_persist(tmp_path: Path) -> None:
    store = MissionMemoryStore(tmp_path)
    key = "user:42"
    data = {
        "branch": "recover/uiux-restore-2026-02-19",
        "target": "embedded vectoring reliability",
    }
    out = store.upsert(key, data, source="test")
    assert out["branch"] == data["branch"]
    assert out["target"] == data["target"]
    assert store.get(key)["branch"] == data["branch"]

    # Re-instantiate to verify persistence.
    reloaded = MissionMemoryStore(tmp_path)
    out2 = reloaded.get(key)
    assert out2["branch"] == data["branch"]
    assert out2["target"] == data["target"]


def test_mission_memory_upsert_merges_fields(tmp_path: Path) -> None:
    store = MissionMemoryStore(tmp_path)
    key = "user:5"
    store.upsert(key, {"branch": "a"}, source="test")
    store.upsert(key, {"priority": "safety over speed"}, source="test")
    out = store.get(key)
    assert out["branch"] == "a"
    assert out["priority"] == "safety over speed"


def test_hardware_context_store_upsert_get_and_changed_keys(tmp_path: Path) -> None:
    store = HardwareContextStore(tmp_path)
    key = "user:99"
    first = {
        "board": {"resolved_profile": {"label": "Arduino Nano", "id": "nano"}},
        "hardware": {"imu_type": "mpu6050"},
        "pins": {"imu_sda": 18},
    }
    out1 = store.upsert(key, first)
    assert out1["accepted"] is True
    assert out1["changed"] is True
    assert out1["initial"] is True
    assert "board" in out1["changed_keys"]

    second = {
        "board": {"resolved_profile": {"label": "Arduino Nano", "id": "nano"}},
        "hardware": {"imu_type": "icm20948"},
        "pins": {"imu_sda": 18},
    }
    out2 = store.upsert(key, second)
    assert out2["accepted"] is True
    assert out2["changed"] is True
    assert out2["initial"] is False
    assert "hardware" in out2["changed_keys"]
    assert store.get(key)["hardware"]["imu_type"] == "icm20948"

    reloaded = HardwareContextStore(tmp_path)
    assert reloaded.get(key)["hardware"]["imu_type"] == "icm20948"


def test_format_hardware_context_notice_initial_and_update() -> None:
    ctx = {
        "board": {
            "resolved_profile": {"label": "ESP32 DevKitC V4", "id": "esp32_devkitc_v4"}
        }
    }
    initial_notice = _format_hardware_context_notice(
        ctx,
        {"accepted": True, "changed": True, "initial": True, "changed_keys": ["board"]},
    )
    assert "Hardware context synced: ESP32 DevKitC V4." in initial_notice

    update_notice = _format_hardware_context_notice(
        ctx,
        {
            "accepted": True,
            "changed": True,
            "initial": False,
            "changed_keys": ["board", "pins"],
        },
    )
    assert "Hardware context updated (ESP32 DevKitC V4)." in update_notice
    assert "Changed fields: board, pins." in update_notice

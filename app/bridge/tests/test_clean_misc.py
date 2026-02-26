import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from clean_misc import (
    build_boards_payload,
    build_capabilities_payload,
    build_design_payload,
    build_firmware_check_payload,
    build_firmware_result_payload,
    build_overwatch_payload,
    build_reset_payload,
    build_sketch_payload,
)


def test_build_sketch_payload_shape() -> None:
    payload = build_sketch_payload(sketch="void setup() {}")
    assert payload["ok"] is True
    assert "setup" in payload["sketch"]


def test_build_boards_payload_shape() -> None:
    payload = build_boards_payload(boards=[{"name": "nano"}, {"name": "esp32"}])
    assert payload["ok"] is True
    assert len(payload["boards"]) == 2


def test_build_firmware_check_payload_shape() -> None:
    payload = build_firmware_check_payload(
        firmware_check={"arduino_cli": True, "version": "0.35.0"}
    )
    assert payload["ok"] is True
    assert payload["firmware_check"]["arduino_cli"] is True


def test_build_firmware_result_payload_shape() -> None:
    payload = build_firmware_result_payload(
        firmware={"status": "compiled", "output": "Build complete"}
    )
    assert payload["ok"] is True
    assert payload["firmware"]["status"] == "compiled"


def test_build_overwatch_payload_shape() -> None:
    payload = build_overwatch_payload(
        overwatch={"health": "good", "warnings": []}
    )
    assert payload["ok"] is True
    assert payload["overwatch"]["health"] == "good"


def test_build_capabilities_payload_shape() -> None:
    payload = build_capabilities_payload(
        capabilities={"pid_tuning": True}, source="status_only"
    )
    assert payload["ok"] is True
    assert payload["capabilities"]["pid_tuning"] is True
    assert payload["source"] == "status_only"


def test_build_design_payload_shape() -> None:
    payload = build_design_payload(
        design={"id": "d1", "success": True, "params": {"kp": 1.0}}
    )
    assert payload["ok"] is True
    assert payload["design"]["id"] == "d1"


def test_build_reset_payload_shape() -> None:
    payload = build_reset_payload(reset={"sent": True, "token": "abc123"})
    assert payload["ok"] is True
    assert payload["reset"]["sent"] is True

import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from clean_firmware import (
    build_firmware_artifacts_payload,
    build_firmware_sketch_folders_payload,
    build_firmware_status_payload,
    build_runtime_manifest_validate_payload,
)


def test_build_firmware_status_payload_shape() -> None:
    payload = build_firmware_status_payload(
        firmware_status={"compile": {"ok": True}, "upload": {"ok": False}}
    )
    assert payload["ok"] is True
    assert payload["firmware"]["compile"]["ok"] is True


def test_build_firmware_artifacts_payload_shape() -> None:
    payload = build_firmware_artifacts_payload(
        firmware_artifacts=[{"run_id": "r1"}, {"run_id": "r2"}]
    )
    assert payload["ok"] is True
    assert len(payload["firmware_artifacts"]) == 2


def test_build_runtime_manifest_validate_payload_shape() -> None:
    payload_ok = build_runtime_manifest_validate_payload(
        check={"ok": True, "errors": []}
    )
    assert payload_ok["ok"] is True
    assert payload_ok["validation"]["errors"] == []

    payload_fail = build_runtime_manifest_validate_payload(
        check={"ok": False, "errors": ["runtime_manifest_missing"]}
    )
    assert payload_fail["ok"] is False
    assert payload_fail["validation"]["errors"][0] == "runtime_manifest_missing"


def test_build_firmware_sketch_folders_payload_shape() -> None:
    payload = build_firmware_sketch_folders_payload(
        sketch_folders=[{"name": "a"}, {"name": "b"}]
    )
    assert payload["ok"] is True
    assert payload["sketch_folders"][1]["name"] == "b"

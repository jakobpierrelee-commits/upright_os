import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from server import _clean_upload_precheck_payload  # noqa: E402


class _FakeGateway:
    def __init__(self, connected: bool = True) -> None:
        self._connected = connected

    def health(self):
        return {"connected": self._connected}


class _FakeFirmware:
    def status(self):
        return {"running": False}

    def list_boards(self):
        return {
            "ok": True,
            "ports": [{"address": "/dev/cu.usbserial-2210"}],
            "recommended_port": "/dev/cu.usbserial-2210",
        }

    def validate_runtime_manifest(self, sketch: str, require_exists: bool = True):  # noqa: ARG002
        return {"ok": True, "errors": [], "warnings": []}

    def list_targets(self):
        return {
            "boards": [
                {
                    "id": "nano",
                    "family": "arduino_avr",
                    "label": "Arduino Nano",
                    "fqbn_base": "arduino:avr:nano",
                }
            ]
        }


def test_clean_upload_precheck_flags_selected_port_not_detected() -> None:
    payload = _clean_upload_precheck_payload(
        gateway=_FakeGateway(),
        firmware=_FakeFirmware(),
        requested_port="/dev/cu.wrong",
        requested_fqbn="arduino:avr:nano:cpu=atmega328old",
        requested_sketch="/tmp/sketch",
    )
    assert payload["ok"] is True
    assert payload["ready"] is False
    assert "selected_port_not_detected" in payload["hard_fail_reasons"]

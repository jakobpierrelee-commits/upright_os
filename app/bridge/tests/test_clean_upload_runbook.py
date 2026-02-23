import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from server import _clean_upload_target_meta, _clean_upload_target_runbook  # noqa: E402


class _FirmwareStub:
    @staticmethod
    def list_targets() -> dict:
        return {
            "boards": [
                {
                    "id": "nano",
                    "family": "arduino_avr",
                    "label": "Arduino Nano",
                    "fqbn_base": "arduino:avr:nano",
                    "bootloaders": [
                        {"id": "new", "fqbn_suffix": ""},
                        {"id": "old", "fqbn_suffix": ":cpu=atmega328old"},
                    ],
                },
                {
                    "id": "teensy41",
                    "family": "teensy",
                    "label": "Teensy 4.1",
                    "fqbn_base": "teensy:avr:teensy41",
                    "bootloaders": [{"id": "default", "fqbn_suffix": ""}],
                },
            ]
        }


def test_clean_upload_target_meta_resolves_board_and_family() -> None:
    meta = _clean_upload_target_meta(
        fqbn="arduino:avr:nano:cpu=atmega328old", firmware=_FirmwareStub()
    )
    assert meta["board_id"] == "nano"
    assert meta["board_family"] == "arduino_avr"
    assert meta["board_label"] == "Arduino Nano"


def test_clean_upload_target_runbook_has_family_specific_boot_hint() -> None:
    runbook = _clean_upload_target_runbook(
        {
            "fqbn": "teensy:avr:teensy41",
            "board_id": "teensy41",
            "board_family": "teensy",
            "board_label": "Teensy 4.1",
        }
    )
    boot_steps = runbook["recovery"]["bootloader_sync"]
    assert any("Program button" in s for s in boot_steps)

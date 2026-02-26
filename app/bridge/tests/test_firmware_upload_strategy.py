import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from server import FirmwareManager  # noqa: E402


def test_targets_expose_upload_strategy_metadata() -> None:
    fm = FirmwareManager(repo_root=Path("."), default_port="/dev/null")
    targets = fm.list_targets()
    families = list(targets.get("families", []))
    avr = next(
        (row for row in families if isinstance(row, dict) and row.get("id") == "arduino_avr"),
        None,
    )
    assert isinstance(avr, dict)
    strategy = avr.get("upload_strategy")
    assert isinstance(strategy, dict)
    assert int(strategy.get("max_attempts", 0)) >= 1
    assert isinstance(strategy.get("retryable_classes"), list)


def test_resolve_upload_strategy_applies_board_override() -> None:
    fm = FirmwareManager(repo_root=Path("."), default_port="/dev/null")
    policy = fm._resolve_upload_strategy("arduino:avr:nano:cpu=atmega328old")
    assert int(policy.get("max_attempts", 0)) == 2
    retryable = set(str(x) for x in list(policy.get("retryable_classes", [])))
    assert "bootloader_sync" in retryable
    assert "port_missing" in retryable


def test_classify_upload_failure_bootloader_sync() -> None:
    out = FirmwareManager._classify_upload_failure(
        [
            "Error: protocol expects sync byte 0x14 but got 0x55",
            "Error: programmer is out of sync",
        ],
        returncode=1,
    )
    assert out == "bootloader_sync"


def test_classify_upload_failure_port_busy() -> None:
    out = FirmwareManager._classify_upload_failure(
        ["Error: resource busy: /dev/cu.usbserial-2210"], returncode=1
    )
    assert out == "port_busy"


def test_classify_upload_failure_prefers_port_missing_over_sync() -> None:
    out = FirmwareManager._classify_upload_failure(
        [
            "Error: programmer is out of sync",
            "Error: unable to open port /dev/cu.usbserial-2210 for programmer arduino",
        ],
        returncode=1,
    )
    assert out == "port_missing"


def test_nano_bootloader_fallback_cmd_new_to_old() -> None:
    cmd = [
        "arduino-cli",
        "upload",
        "-p",
        "/dev/cu.usbserial-2210",
        "--fqbn",
        "arduino:avr:nano",
        "sketch",
    ]
    out = FirmwareManager._nano_bootloader_fallback_cmd(cmd)
    assert out is not None
    idx = out.index("--fqbn")
    assert out[idx + 1] == "arduino:avr:nano:cpu=atmega328old"


def test_nano_bootloader_fallback_cmd_old_to_new() -> None:
    cmd = [
        "arduino-cli",
        "upload",
        "-p",
        "/dev/cu.usbserial-2210",
        "--fqbn",
        "arduino:avr:nano:cpu=atmega328old",
        "sketch",
    ]
    out = FirmwareManager._nano_bootloader_fallback_cmd(cmd)
    assert out is not None
    idx = out.index("--fqbn")
    assert out[idx + 1] == "arduino:avr:nano"


def test_nano_bootloader_fallback_cmd_non_nano_none() -> None:
    cmd = [
        "arduino-cli",
        "upload",
        "-p",
        "/dev/cu.usbserial-2210",
        "--fqbn",
        "arduino:avr:uno",
        "sketch",
    ]
    assert FirmwareManager._nano_bootloader_fallback_cmd(cmd) is None


def test_cmd_with_port_rewrites_port_arg() -> None:
    cmd = ["arduino-cli", "upload", "-p", "/dev/old", "--fqbn", "arduino:avr:nano", "sketch"]
    out = FirmwareManager._cmd_with_port(cmd, "/dev/new")
    assert out[out.index("-p") + 1] == "/dev/new"

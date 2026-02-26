import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from server import FirmwareManager  # noqa: E402


def test_firmware_run_artifact_is_persisted_and_listed(tmp_path: Path) -> None:
    fm = FirmwareManager(tmp_path, "/dev/null")
    fm._record_run_artifact(  # type: ignore[attr-defined]
        phase="compile",
        cmd=["arduino-cli", "compile", "--fqbn", "arduino:avr:nano", "sketch"],
        returncode=0,
        state="passed",
        started_at=1000.0,
        finished_at=1001.5,
        log_lines=["line1", "line2"],
    )

    st = fm.status()
    assert isinstance(st.get("last_artifact"), dict)
    assert st["last_artifact"]["phase"] == "compile"
    assert st["last_artifact"]["returncode"] == 0

    out = fm.list_run_artifacts(limit=5)
    assert out["ok"] is True
    assert len(out["artifacts"]) == 1
    art = out["artifacts"][0]
    assert art["phase"] == "compile"
    assert art["state"] == "passed"
    assert art["line_count"] == 2
    assert Path(art["log_path"]).exists()
    fingerprint = art.get("hardware_fingerprint") or {}
    assert fingerprint.get("selected_fqbn") == "arduino:avr:nano"
    assert fingerprint.get("selected_port") is None
    assert (fingerprint.get("runtime_identity") or {}).get("source") == "unavailable"


def test_firmware_run_artifact_captures_port_vid_pid_and_runtime_identity(
    tmp_path: Path,
) -> None:
    fm = FirmwareManager(tmp_path, "/dev/null")

    def _fake_list_boards():
        return {
            "ok": True,
            "raw": {
                "detected_ports": [
                    {
                        "port": {
                            "address": "/dev/cu.usbserial-2210",
                            "label": "usbserial-2210",
                            "protocol": "serial",
                            "properties": {
                                "vid": "0x2341",
                                "pid": "0x0043",
                                "serialNumber": "ABC123",
                            },
                        },
                        "matching_boards": [
                            {"fqbn": "arduino:avr:nano", "name": "Arduino Nano"}
                        ],
                    }
                ]
            },
        }

    fm.list_boards = _fake_list_boards  # type: ignore[method-assign]
    fm._record_run_artifact(  # type: ignore[attr-defined]
        phase="upload_guarded",
        cmd=[
            "arduino-cli",
            "upload",
            "-p",
            "/dev/cu.usbserial-2210",
            "--fqbn",
            "arduino:avr:nano:cpu=atmega328old",
            "sketch",
        ],
        returncode=0,
        state="passed",
        started_at=1000.0,
        finished_at=1003.0,
        log_lines=[
            "guarded flash: disarm -> close serial -> upload -> reconnect",
            "STATUS mode=SAFE_IDLE ident=prv1a hash=1a2b3c4d5e6f runtime=profiled_runtime_v1.1.0 tune=tune_v1 estop=1 fault=0 ang=0.002",
        ],
    )
    art = (fm.list_run_artifacts(limit=1).get("artifacts") or [])[0]
    fingerprint = art.get("hardware_fingerprint") or {}
    assert fingerprint.get("selected_port") == "/dev/cu.usbserial-2210"
    assert fingerprint.get("selected_fqbn") == "arduino:avr:nano:cpu=atmega328old"
    board = fingerprint.get("detected_board") or {}
    assert board.get("vid") == "0x2341"
    assert board.get("pid") == "0x0043"
    assert board.get("board_name") == "Arduino Nano"
    ident = fingerprint.get("runtime_identity") or {}
    assert ident.get("mode") == "SAFE_IDLE"
    assert ident.get("estop") == 1
    assert ident.get("fault") == 0
    assert ident.get("ident") == "prv1a"
    assert ident.get("hash") == "1a2b3c4d5e6f"
    assert ident.get("runtime_version") == "profiled_runtime_v1.1.0"
    assert ident.get("tune_version") == "tune_v1"


def test_runtime_identity_parses_reconnect_ident_hash_line(tmp_path: Path) -> None:
    fm = FirmwareManager(tmp_path, "/dev/null")

    fm._record_run_artifact(  # type: ignore[attr-defined]
        phase="upload_guarded",
        cmd=[
            "arduino-cli",
            "upload",
            "-p",
            "/dev/cu.usbserial-2210",
            "--fqbn",
            "arduino:avr:nano:cpu=atmega328old",
            "sketch",
        ],
        returncode=0,
        state="passed",
        started_at=1000.0,
        finished_at=1001.0,
        log_lines=[
            "guarded flash: disarm -> close serial -> upload -> reconnect",
            "bridge reconnected: mode=SAFE_IDLE ident=prv1a hash=1a2b3c4d5e6f runtime=profiled_runtime_v1.1.0 tune=tune_v1",
        ],
    )
    art = (fm.list_run_artifacts(limit=1).get("artifacts") or [])[0]
    ident = ((art.get("hardware_fingerprint") or {}).get("runtime_identity") or {})
    assert ident.get("source") == "reconnect_line"
    assert ident.get("mode") == "SAFE_IDLE"
    assert ident.get("ident") == "prv1a"
    assert ident.get("hash") == "1a2b3c4d5e6f"
    assert ident.get("runtime_version") == "profiled_runtime_v1.1.0"
    assert ident.get("tune_version") == "tune_v1"

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from server import FirmwareManager  # noqa: E402


def test_firmware_operation_lock_reuses_same_idempotency_key(tmp_path: Path) -> None:
    fm = FirmwareManager(tmp_path, "/dev/null")
    cmd = ["arduino-cli", "compile", "--fqbn", "arduino:avr:nano", "sketch"]

    started, snap, op_id = fm._begin_operation(  # type: ignore[attr-defined]
        phase="compile",
        cmd=cmd,
        idempotency_key="compile-key-1",
    )
    assert started is True
    assert isinstance(op_id, str) and op_id.startswith("fwop_")
    assert snap["running"] is True

    reused = fm._run_subprocess(  # type: ignore[attr-defined]
        cmd,
        phase="compile",
        idempotency_key="compile-key-1",
    )
    assert reused["running"] is True
    assert reused.get("idempotent_reused") is True

    try:
        fm._run_subprocess(  # type: ignore[attr-defined]
            cmd,
            phase="compile",
            idempotency_key="compile-key-2",
        )
        raise AssertionError("expected operation_in_progress")
    except RuntimeError as exc:
        assert str(exc) == "operation_in_progress"


def test_firmware_status_exposes_operation_metadata(tmp_path: Path) -> None:
    fm = FirmwareManager(tmp_path, "/dev/null")
    cmd = [
        "arduino-cli",
        "upload",
        "-p",
        "/dev/null",
        "--fqbn",
        "arduino:avr:nano",
        "sketch",
    ]
    started, _snap, op_id = fm._begin_operation(  # type: ignore[attr-defined]
        phase="upload_guarded",
        cmd=cmd,
        idempotency_key="upload-key-1",
    )
    assert started is True
    st = fm.status()
    op = st.get("operation") or {}
    active = op.get("active") or {}
    assert active.get("op_id") == op_id
    assert active.get("phase") == "upload_guarded"
    assert active.get("idempotency_key") == "upload-key-1"

    fm._set(  # type: ignore[attr-defined]
        _running=False,
        _state="passed",
        _finished_at=123.0,
        _returncode=0,
        _active_operation=None,
        _last_completed_operation={
            "op_id": op_id,
            "phase": "upload_guarded",
            "finished_at": 123.0,
            "state": "passed",
            "returncode": 0,
        },
    )
    st2 = fm.status()
    op2 = st2.get("operation") or {}
    assert op2.get("active") is None
    last = op2.get("last_completed") or {}
    assert last.get("op_id") == op_id
    assert last.get("phase") == "upload_guarded"
    assert last.get("state") == "passed"

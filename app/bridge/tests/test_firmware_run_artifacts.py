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

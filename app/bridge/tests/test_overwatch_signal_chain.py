import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from server import build_overwatch_report


class _FakeGateway:
    def __init__(self, status):
        self._status = status

    def health(self):
        return {
            "connected": True,
            "port": "COM_TEST",
            "last_status": self._status,
        }


class _FakeFirmware:
    def __init__(self, repo_root: Path):
        self._generated_root = repo_root / "generated_firmware"

    def status(self):
        return {
            "defaults": {
                "sketch": "",
            }
        }


def _check(report, check_id):
    for c in report.get("checks", []):
        if c.get("id") == check_id:
            return c
    raise AssertionError(f"missing check {check_id}")


def test_overwatch_signal_chain_passes_with_complete_fields(tmp_path: Path):
    status = {
        "mode": "BALANCING",
        "ang": 1.0,
        "raw": 1.4,
        "gyro": 0.2,
        "out": 12.0,
        "set": 1.5,
        "pid_err": 0.5,
        "pid_u_unsat": 12.2,
        "pid_u_sat": 12.0,
        "kal_innov": 0.4,
        "kp": 10.0,
        "ki": 0.1,
        "kd": 0.2,
    }
    report = build_overwatch_report(
        gateway=_FakeGateway(status),
        firmware=_FakeFirmware(tmp_path),
        compat={"missing_commands": []},
        connect={"confidence_pct": 70},
    )

    chain = _check(report, "control_signal_chain")
    innovation = _check(report, "kalman_innovation")
    clamp = _check(report, "output_clamp_visibility")

    assert chain["status"] == "pass"
    assert innovation["status"] == "pass"
    assert clamp["status"] in {"pass", "warn"}


def test_overwatch_signal_chain_warns_when_fields_missing(tmp_path: Path):
    status = {
        "mode": "BALANCING",
        "ang": 0.0,
        "raw": 0.0,
        "gyro": 0.0,
        "out": 0.0,
        "kp": 10.0,
        "ki": 0.1,
        "kd": 0.2,
    }
    report = build_overwatch_report(
        gateway=_FakeGateway(status),
        firmware=_FakeFirmware(tmp_path),
        compat={"missing_commands": []},
        connect={"confidence_pct": 70},
    )

    chain = _check(report, "control_signal_chain")
    innovation = _check(report, "kalman_innovation")

    assert chain["status"] == "warn"
    assert innovation["status"] == "pass"

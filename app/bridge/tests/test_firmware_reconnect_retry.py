import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from server import FirmwareManager  # noqa: E402


class _FlakyGateway:
    def __init__(self, fail_times: int) -> None:
        self.fail_times = fail_times
        self.connect_calls = 0
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1

    def connect(self) -> None:
        self.connect_calls += 1

    def wait_ready(self, timeout: float = 1.0):  # noqa: ARG002
        if self.connect_calls <= self.fail_times:
            raise RuntimeError(
                "read failed: device reports readiness to read but returned no data"
            )
        return {"mode": "SAFE_IDLE"}


def test_reconnect_retry_succeeds_after_transient_failures(tmp_path: Path) -> None:
    fm = FirmwareManager(tmp_path, "/dev/null")
    gw = _FlakyGateway(fail_times=2)
    local_log: list[str] = []
    ok, ready, err = fm._reconnect_gateway_after_flash(  # type: ignore[attr-defined]
        gateway=gw, local_log=local_log, attempts=5, ready_timeout_s=0.2, settle_s=0.0
    )
    assert ok is True
    assert isinstance(ready, dict)
    assert ready.get("mode") == "SAFE_IDLE"
    assert err is None
    assert gw.connect_calls == 3


def test_reconnect_retry_fails_after_all_attempts(tmp_path: Path) -> None:
    fm = FirmwareManager(tmp_path, "/dev/null")
    gw = _FlakyGateway(fail_times=99)
    local_log: list[str] = []
    ok, ready, err = fm._reconnect_gateway_after_flash(  # type: ignore[attr-defined]
        gateway=gw, local_log=local_log, attempts=3, ready_timeout_s=0.2, settle_s=0.0
    )
    assert ok is False
    assert ready is None
    assert isinstance(err, str) and "read failed" in err
    assert gw.connect_calls == 3

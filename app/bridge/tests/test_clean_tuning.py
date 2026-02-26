import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from clean_tuning import (
    build_burst_status_payload,
    build_commissioning_artifacts_payload,
    build_commissioning_status_payload,
    build_lines_payload,
)


def test_build_burst_status_payload_shape() -> None:
    payload = build_burst_status_payload(burst={"armed": False, "capture_count": 0})
    assert payload["ok"] is True
    assert payload["burst"]["armed"] is False
    assert payload["burst"]["capture_count"] == 0


def test_build_commissioning_status_payload_shape() -> None:
    payload = build_commissioning_status_payload(
        commissioning={"state": "idle", "progress": 0}
    )
    assert payload["ok"] is True
    assert payload["commissioning"]["state"] == "idle"


def test_build_commissioning_artifacts_payload_shape() -> None:
    payload = build_commissioning_artifacts_payload(
        artifacts=[{"run_id": "c1", "status": "pass"}]
    )
    assert payload["ok"] is True
    assert len(payload["artifacts"]) == 1
    assert payload["artifacts"][0]["run_id"] == "c1"


def test_build_lines_payload_shape() -> None:
    payload = build_lines_payload(lines=["STATUS mode=IDLE", "OK ARM"])
    assert payload["ok"] is True
    assert len(payload["lines"]) == 2
    assert "STATUS" in payload["lines"][0]

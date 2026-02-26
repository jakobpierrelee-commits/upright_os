import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from clean_safety import (
    build_arm_precheck_payload,
    build_status_control_payload,
)


def test_build_arm_precheck_payload_pass() -> None:
    payload = build_arm_precheck_payload(
        report={"ok": True, "checks": [], "summary": "all passed"},
        prearm_safety={"required": False, "passed": True},
        action_gates={"arm": {"ok": True, "reasons": []}},
    )
    assert payload["ok"] is True
    assert payload["prearm_check"]["summary"] == "all passed"
    assert payload["prearm_safety"]["passed"] is True
    assert payload["action_gates"]["arm"]["ok"] is True


def test_build_arm_precheck_payload_fail() -> None:
    payload = build_arm_precheck_payload(
        report={"ok": False, "checks": [], "summary": "wheel probe failed"},
        prearm_safety={"required": True, "passed": False},
        action_gates={
            "arm": {"ok": False, "reasons": ["prearm_safety_check_required"]}
        },
    )
    assert payload["ok"] is False
    assert payload["prearm_check"]["summary"] == "wheel probe failed"
    assert payload["prearm_safety"]["passed"] is False


def test_build_status_control_payload_shape() -> None:
    payload = build_status_control_payload(
        status={"mode": "SAFE_IDLE", "estop": "0"},
        control={"arm_prepared": False, "estop_latched": False},
    )
    assert payload["ok"] is True
    assert payload["status"]["mode"] == "SAFE_IDLE"
    assert payload["control"]["arm_prepared"] is False

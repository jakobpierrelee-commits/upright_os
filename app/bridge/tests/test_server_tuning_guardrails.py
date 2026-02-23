import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from server import (  # noqa: E402
    TuningPreflightStore,
    _build_tuning_apply_signature,
    _compute_action_gates,
    _detect_tuning_capabilities,
    _enforce_preflight_if_needed,
    _guard_limits_apply,
    _guard_pid_apply,
    _requires_preflight,
    _validate_tuning_recommendation_contract,
)


def test_detect_tuning_capabilities_from_help_tokens() -> None:
    caps = _detect_tuning_capabilities(
        {"kp": "31", "ki": "0.05", "kd": "1.0"},
        ["PID", "MOTION", "SETPOINT", "LIMITS"],
        ["LPF <hz>", "CONDINT <0|1>"],
    )
    assert caps["pid"]["runtime_apply_supported"] is True
    assert caps["limits"]["runtime_apply_supported"] is True
    assert caps["lowpass_cutoff_hz"]["runtime_apply_supported"] is True
    assert caps["conditional_integration"]["runtime_apply_supported"] is True


def test_guard_pid_apply_blocks_large_balancing_delta() -> None:
    with pytest.raises(RuntimeError, match="tuning_delta_too_large_while_balancing"):
        _guard_pid_apply(
            {"mode": "BALANCING", "kp": "31", "ki": "0.05", "kd": "1.05"},
            kp=35.0,
            ki=0.05,
            kd=1.05,
        )


def test_guard_limits_apply_rejects_invalid_range() -> None:
    with pytest.raises(RuntimeError, match="invalid_tuning_value:tip_deg"):
        _guard_limits_apply(
            {"mode": "SAFE_IDLE"}, out_max=180.0, tip_deg=120.0, i_max=70.0
        )


def test_validate_recommendation_contract_flags_missing_fields() -> None:
    errs = _validate_tuning_recommendation_contract({"ok": True})
    assert any(e.startswith("missing:") for e in errs)


def test_validate_recommendation_contract_accepts_expected_shape() -> None:
    errs = _validate_tuning_recommendation_contract(
        {
            "ok": True,
            "score_pct": 77,
            "readiness": "watch",
            "recommendations": [],
            "procedure": ["a", "b"],
            "variables_available": {},
        }
    )
    assert errs == []


def test_requires_preflight_for_high_impact_pid_change() -> None:
    assert _requires_preflight(
        family="pid",
        status_before={"mode": "SAFE_IDLE"},
        current={"kp": 31.0, "ki": 0.05, "kd": 1.05},
        target={"kp": 33.0, "ki": 0.05, "kd": 1.05},
    )


def test_preflight_store_validates_signature_and_mismatch() -> None:
    store = TuningPreflightStore(ttl_s=60.0, max_entries=8)
    sig = _build_tuning_apply_signature("pid", {"kp": 32.0, "ki": 0.05, "kd": 1.05})
    node = store.issue(family="pid", signature=sig, score_pct=80, notes=["ok"])
    assert "preflight_id" in node
    store.validate(node["preflight_id"], sig)
    with pytest.raises(RuntimeError, match="preflight_mismatch"):
        store.validate(
            node["preflight_id"],
            _build_tuning_apply_signature("pid", {"kp": 35.0, "ki": 0.05, "kd": 1.05}),
        )


def test_enforce_preflight_requires_id_when_high_impact() -> None:
    store = TuningPreflightStore(ttl_s=60.0, max_entries=8)
    with pytest.raises(RuntimeError, match="preflight_required"):
        _enforce_preflight_if_needed(
            preflight_store=store,
            body={},
            family="pid",
            status_before={"mode": "SAFE_IDLE"},
            current={"kp": 31.0, "ki": 0.05, "kd": 1.05},
            target={"kp": 33.0, "ki": 0.05, "kd": 1.05},
        )


def test_compute_action_gates_blocks_when_telemetry_contract_missing() -> None:
    gates = _compute_action_gates(
        connected=True,
        status={"mode": "SAFE_IDLE", "ang": "0.0"},
        control_snapshot={"arm_prepared": False, "estop_latched": False},
        session_fresh=True,
    )
    assert gates["arm_prepare"]["ok"] is False
    assert "telemetry_contract_incomplete" in gates["arm_prepare"]["reasons"]
    assert gates["pid"]["ok"] is False
    assert "telemetry_contract_incomplete" in gates["pid"]["reasons"]


def test_compute_action_gates_allows_nominal_arm_prepare() -> None:
    gates = _compute_action_gates(
        connected=True,
        status={
            "mode": "SAFE_IDLE",
            "ang": "0.0",
            "raw": "0.0",
            "gyro": "0.0",
            "out": "0.0",
            "kp": "31.0",
            "ki": "0.05",
            "kd": "1.05",
            "set": "0.0",
        },
        control_snapshot={"arm_prepared": False, "estop_latched": False},
        session_fresh=True,
    )
    assert gates["arm_prepare"]["ok"] is True
    assert gates["arm_prepare"]["reasons"] == []
    assert gates["pid"]["ok"] is True


def test_compute_action_gates_block_arm_confirm_until_prepared() -> None:
    gates = _compute_action_gates(
        connected=True,
        status={
            "mode": "SAFE_IDLE",
            "ang": "0.0",
            "raw": "0.0",
            "gyro": "0.0",
            "out": "0.0",
            "kp": "31.0",
            "ki": "0.05",
            "kd": "1.05",
            "set": "0.0",
        },
        control_snapshot={"arm_prepared": False, "estop_latched": False},
        session_fresh=True,
    )
    assert gates["arm_confirm"]["ok"] is False
    assert "arm_not_prepared" in gates["arm_confirm"]["reasons"]


def test_compute_action_gates_block_arm_when_prearm_safety_required() -> None:
    gates = _compute_action_gates(
        connected=True,
        status={
            "mode": "SAFE_IDLE",
            "ang": "0.0",
            "raw": "0.0",
            "gyro": "0.0",
            "out": "0.0",
            "kp": "31.0",
            "ki": "0.05",
            "kd": "1.05",
            "set": "0.0",
        },
        control_snapshot={"arm_prepared": False, "estop_latched": False},
        session_fresh=True,
        prearm_safety={"required": True, "passed": False},
    )
    assert gates["arm_prepare"]["ok"] is False
    assert "prearm_safety_check_required" in gates["arm_prepare"]["reasons"]
    assert gates["arm"]["ok"] is False
    assert "prearm_safety_check_required" in gates["arm"]["reasons"]


def test_compute_action_gates_allow_arm_when_prearm_safety_passed() -> None:
    gates = _compute_action_gates(
        connected=True,
        status={
            "mode": "SAFE_IDLE",
            "ang": "0.0",
            "raw": "0.0",
            "gyro": "0.0",
            "out": "0.0",
            "kp": "31.0",
            "ki": "0.05",
            "kd": "1.05",
            "set": "0.0",
        },
        control_snapshot={"arm_prepared": False, "estop_latched": False},
        session_fresh=True,
        prearm_safety={"required": False, "passed": True},
    )
    assert gates["arm_prepare"]["ok"] is True
    assert gates["arm"]["ok"] is True

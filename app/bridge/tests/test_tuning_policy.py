import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tuning_policy import evaluate_tuning_plan  # noqa: E402


def test_tuning_policy_marks_risky_on_faceplant_and_replay_fail() -> None:
    out = evaluate_tuning_plan(
        current={
            "kp": 40,
            "ki": 0.3,
            "kd": 0.1,
            "out_max": 180,
            "i_max": 70,
            "lowpass_cutoff_hz": 8,
            "conditional_integration": False,
        },
        telemetry={"output_saturation_pct": 95, "oscillation_detected": True, "oscillation_freq_hz": 1.2},
        surrogate={
            "ok": True,
            "model": {"distance_from_known": 0.8, "confidence": 0.25},
            "simulation": {"metrics": {"faceplant": True, "overshoot": 22, "settle_s": None, "max_out_pct": 99}},
        },
        replay_results=[{"result": {"pass": False}}],
    )

    assert out["ok"] is True
    assert out["readiness"] == "risky"
    assert out["score_pct"] < 60
    assert any("rollback" in r["action"].lower() for r in out["recommendations"])


def test_tuning_policy_prefers_conditional_integration_for_low_freq_hunt() -> None:
    out = evaluate_tuning_plan(
        current={"kp": 31, "ki": 0.12, "kd": 1.0, "i_max": 70, "conditional_integration": False},
        telemetry={"oscillation_detected": True, "oscillation_freq_hz": 1.0, "output_saturation_pct": 50},
    )

    assert out["ok"] is True
    assert any("conditional integration" in r["action"].lower() for r in out["recommendations"])
    assert out["variables_available"]["conditional_integration"]["runtime_apply_supported"] is False


def test_tuning_policy_returns_procedure_and_runtime_variable_contract() -> None:
    out = evaluate_tuning_plan(current={"kp": 31, "ki": 0.05, "kd": 1.05})
    assert out["ok"] is True
    assert len(out["procedure"]) >= 4
    assert out["variables_available"]["limits"]["runtime_apply_supported"] is True
    assert out["variables_available"]["lowpass_cutoff_hz"]["runtime_apply_supported"] is False

import sys
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from tuning_policy import evaluate_tuning_plan  # noqa: E402


BASE_CURRENT: Dict[str, Any] = {
    "kp": 31.0,
    "ki": 0.05,
    "kd": 1.05,
    "out_max": 180.0,
    "i_max": 70.0,
    "lowpass_cutoff_hz": 8.0,
    "conditional_integration": False,
}


def _find_recommendation_with_change(
    out: Dict[str, Any], change_key: str
) -> Optional[Dict[str, Any]]:
    for rec in list(out.get("recommendations") or []):
        if not isinstance(rec, dict):
            continue
        changes = rec.get("changes")
        if isinstance(changes, dict) and change_key in changes:
            return rec
    return None


def test_tuning_acceptance_stable_scenario_holds_gains() -> None:
    out = evaluate_tuning_plan(
        current=dict(BASE_CURRENT),
        telemetry={
            "angle_variance": 1.1,
            "output_saturation_pct": 22.0,
            "oscillation_detected": False,
            "oscillation_freq_hz": 0.0,
        },
    )

    assert out["ok"] is True
    assert out["readiness"] == "good"
    assert int(out["score_pct"]) >= 80
    assert len(out["recommendations"]) >= 1

    top = out["recommendations"][0]
    assert "hold gains" in str(top.get("action", "")).lower()
    assert top.get("changes") == {}


def test_tuning_acceptance_oscillation_scenario_recommends_damping_with_bounded_delta() -> None:
    out = evaluate_tuning_plan(
        current=dict(BASE_CURRENT),
        telemetry={
            "angle_variance": 3.5,
            "output_saturation_pct": 62.0,
            "oscillation_detected": True,
            "oscillation_freq_hz": 3.2,
        },
    )

    assert out["ok"] is True
    assert out["readiness"] in {"watch", "good"}

    rec = _find_recommendation_with_change(out, "pid")
    assert rec is not None
    pid = (rec.get("changes") or {}).get("pid") or {}

    kd_next = float(pid["kd"])
    kd_prev = float(BASE_CURRENT["kd"])
    assert kd_next > kd_prev
    assert (kd_next - kd_prev) <= 0.2

    lpf = (rec.get("changes") or {}).get("lowpass_cutoff_hz")
    assert lpf is not None
    lpf_next = float(lpf)
    lpf_prev = float(BASE_CURRENT["lowpass_cutoff_hz"])
    assert lpf_next < lpf_prev
    assert (lpf_prev - lpf_next) <= 2.0


def test_tuning_acceptance_drift_scenario_recommends_small_stiffness_step() -> None:
    out = evaluate_tuning_plan(
        current=dict(BASE_CURRENT),
        telemetry={
            "angle_variance": 8.4,
            "output_saturation_pct": 35.0,
            "oscillation_detected": False,
            "oscillation_freq_hz": 0.0,
        },
    )

    assert out["ok"] is True
    assert out["readiness"] == "good"
    assert int(out["score_pct"]) >= 80

    rec = _find_recommendation_with_change(out, "pid")
    assert rec is not None
    pid = (rec.get("changes") or {}).get("pid") or {}

    kp_next = float(pid["kp"])
    kp_prev = float(BASE_CURRENT["kp"])
    assert kp_next > kp_prev
    assert (kp_next - kp_prev) <= (kp_prev * 0.1)

    ki_next = float(pid["ki"])
    kd_next = float(pid["kd"])
    assert ki_next == float(BASE_CURRENT["ki"])
    assert kd_next == float(BASE_CURRENT["kd"])

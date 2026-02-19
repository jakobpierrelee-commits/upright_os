"""
Tuning policy and scoring engine for operator-facing recommendations.

This module is deterministic and side-effect free so it can be tested directly
and reused by both UI and assistant workflows.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _clamp(v: float, lo: float, hi: float) -> float:
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def _f(data: Dict[str, Any], key: str, default: float) -> float:
    try:
        return float(data.get(key, default))
    except Exception:
        return default


def _b(data: Dict[str, Any], key: str, default: bool) -> bool:
    raw = data.get(key, default)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(raw)


def _append_rec(
    recs: List[Dict[str, Any]],
    *,
    priority: str,
    action: str,
    rationale: str,
    confidence: float,
    changes: Optional[Dict[str, Any]] = None,
    runtime_apply_supported: bool = True,
) -> None:
    recs.append(
        {
            "priority": priority,
            "action": action,
            "rationale": rationale,
            "confidence": round(_clamp(confidence, 0.05, 0.99), 2),
            "changes": changes or {},
            "runtime_apply_supported": runtime_apply_supported,
        }
    )


def evaluate_tuning_plan(
    *,
    current: Dict[str, Any],
    telemetry: Optional[Dict[str, Any]] = None,
    surrogate: Optional[Dict[str, Any]] = None,
    replay_results: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    telemetry = telemetry or {}
    replay_results = replay_results or []
    recs: List[Dict[str, Any]] = []

    kp = _f(current, "kp", 31.0)
    ki = _f(current, "ki", 0.05)
    kd = _f(current, "kd", 1.05)
    out_max = _f(current, "out_max", 180.0)
    i_max = _f(current, "i_max", 70.0)
    lowpass_cutoff_hz = _f(current, "lowpass_cutoff_hz", 8.0)
    conditional_integration = _b(current, "conditional_integration", False)

    angle_variance = _f(telemetry, "angle_variance", 0.0)
    output_saturation_pct = _f(telemetry, "output_saturation_pct", 0.0)
    oscillation_detected = _b(telemetry, "oscillation_detected", False)
    oscillation_freq_hz = _f(telemetry, "oscillation_freq_hz", 0.0)

    score = 100.0

    if output_saturation_pct >= 90.0:
        score -= 24.0
        new_kp = round(max(0.1, kp * 0.88), 3)
        _append_rec(
            recs,
            priority="high",
            action="Reduce proportional drive and widen headroom.",
            rationale=f"Output saturation is {output_saturation_pct:.0f}%; control authority is clipping.",
            confidence=0.87,
            changes={"pid": {"kp": new_kp, "ki": ki, "kd": kd}, "limits": {"out_max": out_max}},
        )
    elif output_saturation_pct >= 75.0:
        score -= 12.0
        _append_rec(
            recs,
            priority="medium",
            action="Slightly reduce Kp or increase out_max after safety check.",
            rationale=f"Saturation is elevated at {output_saturation_pct:.0f}%.",
            confidence=0.72,
            changes={"pid": {"kp": round(max(0.1, kp * 0.94), 3), "ki": ki, "kd": kd}},
        )

    if oscillation_detected and oscillation_freq_hz > 2.2:
        score -= 16.0
        _append_rec(
            recs,
            priority="high",
            action="Increase damping and lower measurement noise feedthrough.",
            rationale=f"High-frequency oscillation detected around {oscillation_freq_hz:.2f} Hz.",
            confidence=0.84,
            changes={
                "pid": {"kp": kp, "ki": ki, "kd": round(kd * 1.15, 3)},
                "lowpass_cutoff_hz": round(max(2.0, lowpass_cutoff_hz * 0.8), 2),
            },
            runtime_apply_supported=False,
        )
    elif oscillation_detected and 0.0 < oscillation_freq_hz <= 2.2:
        score -= 12.0
        _append_rec(
            recs,
            priority="high",
            action="Mitigate integral windup behavior.",
            rationale=f"Low-frequency oscillation at {oscillation_freq_hz:.2f} Hz suggests windup-driven hunting.",
            confidence=0.81,
            changes={
                "pid": {"kp": kp, "ki": round(ki * 0.55, 4), "kd": kd},
                "limits": {"i_max": round(max(2.0, i_max * 0.8), 3)},
                "conditional_integration": True,
            },
            runtime_apply_supported=False,
        )

    if (output_saturation_pct >= 65.0 or oscillation_detected) and not conditional_integration:
        score -= 8.0
        _append_rec(
            recs,
            priority="medium",
            action="Enable conditional integration in firmware control loop.",
            rationale="Only integrate when command is unsaturated or error drives output back from saturation.",
            confidence=0.78,
            changes={"conditional_integration": True},
            runtime_apply_supported=False,
        )

    if angle_variance >= 7.0 and not oscillation_detected:
        score -= 9.0
        _append_rec(
            recs,
            priority="medium",
            action="Increase proportional stiffness in small bounded step.",
            rationale=f"Angle variance is {angle_variance:.2f} deg without oscillation signature.",
            confidence=0.69,
            changes={"pid": {"kp": round(kp * 1.08, 3), "ki": ki, "kd": kd}},
        )

    sim = surrogate if isinstance(surrogate, dict) else None
    if sim and sim.get("ok"):
        model = sim.get("model", {}) if isinstance(sim.get("model"), dict) else {}
        metrics = sim.get("simulation", {}).get("metrics", {}) if isinstance(sim.get("simulation"), dict) else {}
        dist = _f(model, "distance_from_known", 0.0)
        conf = _f(model, "confidence", 0.0)
        overshoot = _f(metrics, "overshoot", 0.0)
        settle_s = metrics.get("settle_s")
        faceplant = bool(metrics.get("faceplant", False))
        max_out_pct = _f(metrics, "max_out_pct", 0.0)

        score -= min(20.0, dist * 18.0)
        if conf < 0.45:
            score -= 8.0
        if faceplant:
            score -= 35.0
            _append_rec(
                recs,
                priority="high",
                action="Reject candidate gains and rollback to known-safe checkpoint.",
                rationale="Surrogate predicts faceplant risk.",
                confidence=0.93,
                changes={},
            )
        if overshoot > 14.0:
            score -= 8.0
        if settle_s is None:
            score -= 6.0
        if max_out_pct > 90.0:
            score -= 8.0

    replay_fail_count = 0
    for rep in replay_results:
        result = rep.get("result", {}) if isinstance(rep, dict) else {}
        if not bool(result.get("pass", False)):
            replay_fail_count += 1
    if replay_fail_count > 0:
        score -= min(24.0, replay_fail_count * 8.0)
        _append_rec(
            recs,
            priority="high",
            action="Do not promote gains yet; replay parity checks are failing.",
            rationale=f"{replay_fail_count} replay validation run(s) exceeded command error thresholds.",
            confidence=0.86,
            changes={},
        )

    if not recs:
        _append_rec(
            recs,
            priority="low",
            action="Hold gains and capture a checkpoint.",
            rationale="No dominant instability signature detected.",
            confidence=0.64,
            changes={},
        )

    procedure = [
        "Capture baseline telemetry for 10-20s and snapshot current PID/MOTION/LIMITS.",
        "Apply one bounded change only, then run a repeatable observation window.",
        "Score result on variance, saturation, overshoot, settle, and replay parity.",
        "Promote only when score improves and safety checks remain green.",
        "If telemetry is insufficient, use Cohen-Coon only as a coarse seed, then refine from closed-loop evidence.",
    ]

    score = _clamp(score, 0.0, 100.0)
    readiness = "good" if score >= 80 else ("watch" if score >= 60 else "risky")

    variables = {
        "pid": {"runtime_apply_supported": True, "fields": ["kp", "ki", "kd"]},
        "motion": {"runtime_apply_supported": True, "fields": ["kv", "kx"]},
        "setpoint": {"runtime_apply_supported": True, "fields": ["setpoint"]},
        "limits": {"runtime_apply_supported": True, "fields": ["out_max", "tip_deg", "i_max"]},
        "lowpass_cutoff_hz": {"runtime_apply_supported": False, "fields": ["lowpass_cutoff_hz"]},
        "conditional_integration": {"runtime_apply_supported": False, "fields": ["conditional_integration"]},
    }

    recs.sort(key=lambda r: ({"high": 0, "medium": 1, "low": 2}.get(str(r.get("priority")), 3), -float(r.get("confidence", 0.0))))

    return {
        "ok": True,
        "score_pct": int(round(score)),
        "readiness": readiness,
        "recommendations": recs[:6],
        "procedure": procedure,
        "variables_available": variables,
    }


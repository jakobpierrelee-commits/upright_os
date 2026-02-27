"""Tuning guard utilities extracted from server.py."""

import hashlib
import json
import pathlib
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from app.bridge.domain import TuningPreflightStore

__all__ = [
    "TUNING_BAL_BOUNDS",
    "TUNING_PREFLIGHT_DELTA",
    "_status_float",
    "_require_tuning_range",
    "_guard_pid_apply",
    "_guard_motion_apply",
    "_guard_setpoint_apply",
    "_guard_limits_apply",
    "_detect_tuning_capabilities",
    "_validate_tuning_recommendation_contract",
    "_evaluate_tuning_recommendation_quality",
    "_build_tuning_apply_signature",
    "_requires_preflight",
    "_enforce_preflight_if_needed",
]


TUNING_BAL_BOUNDS = {
    "kp": 1.0,
    "ki": 0.05,
    "kd": 0.2,
    "kv": 0.05,
    "kx": 0.002,
    "setpoint": 0.5,
    "out_max": 20.0,
    "i_max": 20.0,
}

TUNING_PREFLIGHT_DELTA = {
    "pid": {"kp": 0.8, "ki": 0.03, "kd": 0.12},
    "motion": {"kv": 0.03, "kx": 0.001},
    "setpoint": {"deg": 0.35},
    "limits": {"out_max": 8.0, "tip_deg": 2.0, "i_max": 8.0},
}


def _status_float(status: Dict[str, Any], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        if key in status:
            try:
                return float(status[key])
            except Exception:
                continue
    return default


def _require_tuning_range(name: str, value: float, lo: float, hi: float) -> None:
    if not (lo <= value <= hi):
        raise RuntimeError(f"invalid_tuning_value:{name}:{value}")


def _guard_pid_apply(
    status_before: Dict[str, Any], kp: float, ki: float, kd: float
) -> None:
    _require_tuning_range("kp", kp, 0.0, 400.0)
    _require_tuning_range("ki", ki, 0.0, 5.0)
    _require_tuning_range("kd", kd, 0.0, 50.0)
    if str(status_before.get("mode", "")) == "BALANCING":
        curr_kp = _status_float(status_before, "kp", default=31.0)
        curr_ki = _status_float(status_before, "ki", default=0.05)
        curr_kd = _status_float(status_before, "kd", default=1.05)
        if (
            abs(kp - curr_kp) > TUNING_BAL_BOUNDS["kp"]
            or abs(ki - curr_ki) > TUNING_BAL_BOUNDS["ki"]
            or abs(kd - curr_kd) > TUNING_BAL_BOUNDS["kd"]
        ):
            raise RuntimeError("tuning_delta_too_large_while_balancing")


def _guard_motion_apply(status_before: Dict[str, Any], kv: float, kx: float) -> None:
    _require_tuning_range("kv", kv, -5.0, 5.0)
    _require_tuning_range("kx", kx, -1.0, 1.0)
    if str(status_before.get("mode", "")) == "BALANCING":
        curr_kv = _status_float(status_before, "kv", default=0.0)
        curr_kx = _status_float(status_before, "kx", default=0.0)
        if (
            abs(kv - curr_kv) > TUNING_BAL_BOUNDS["kv"]
            or abs(kx - curr_kx) > TUNING_BAL_BOUNDS["kx"]
        ):
            raise RuntimeError("tuning_delta_too_large_while_balancing")


def _guard_setpoint_apply(status_before: Dict[str, Any], deg: float) -> None:
    _require_tuning_range("setpoint", deg, -30.0, 30.0)
    if str(status_before.get("mode", "")) == "BALANCING":
        curr_set = _status_float(status_before, "set", default=0.0)
        if abs(deg - curr_set) > TUNING_BAL_BOUNDS["setpoint"]:
            raise RuntimeError("tuning_delta_too_large_while_balancing")


def _guard_limits_apply(
    status_before: Dict[str, Any], out_max: float, tip_deg: float, i_max: float
) -> None:
    _require_tuning_range("out_max", out_max, 1.0, 255.0)
    _require_tuning_range("tip_deg", tip_deg, 1.0, 85.0)
    _require_tuning_range("i_max", i_max, 0.0, 400.0)
    if str(status_before.get("mode", "")) == "BALANCING":
        curr_out = _status_float(status_before, "outMax", "out_max", default=180.0)
        curr_i = _status_float(status_before, "iMax", "i_max", default=70.0)
        if (
            abs(out_max - curr_out) > TUNING_BAL_BOUNDS["out_max"]
            or abs(i_max - curr_i) > TUNING_BAL_BOUNDS["i_max"]
        ):
            raise RuntimeError("tuning_delta_too_large_while_balancing")


def _detect_tuning_capabilities(
    status: Dict[str, Any], supported_commands: list[str], help_lines: list[str]
) -> Dict[str, Any]:
    cmds = set(supported_commands or [])
    blob = "\n".join(help_lines or []).upper()
    has_lpf_cmd = any(tok in blob for tok in ("LPF", "LOWPASS", "FILTER", "CUTOFF"))
    has_condint_cmd = any(
        tok in blob
        for tok in ("CONDINT", "ANTIWINDUP", "ANTI-WINDUP", "INTEGRATOR MODE")
    )

    capabilities = {
        "pid": {"runtime_apply_supported": "PID" in cmds, "source": "help"},
        "motion": {"runtime_apply_supported": "MOTION" in cmds, "source": "help"},
        "setpoint": {"runtime_apply_supported": "SETPOINT" in cmds, "source": "help"},
        "limits": {"runtime_apply_supported": "LIMITS" in cmds, "source": "help"},
        "lowpass_cutoff_hz": {
            "runtime_apply_supported": has_lpf_cmd,
            "source": "help",
            "command_candidates": ["LPF", "LOWPASS", "FILTER"],
        },
        "conditional_integration": {
            "runtime_apply_supported": has_condint_cmd,
            "source": "help",
            "command_candidates": ["CONDINT", "ANTIWINDUP"],
        },
    }
    capabilities["status_keys"] = sorted(
        [
            k
            for k in status.keys()
            if k in {"kp", "ki", "kd", "kv", "kx", "set", "outMax", "iMax", "tipDeg"}
        ]
    )
    return capabilities


def _validate_tuning_recommendation_contract(rec: Dict[str, Any]) -> list[str]:
    errs: list[str] = []
    if not isinstance(rec, dict):
        return ["recommendation_not_object"]
    required = {
        "ok",
        "score_pct",
        "readiness",
        "recommendations",
        "procedure",
        "variables_available",
    }
    missing = sorted(required - set(rec.keys()))
    if missing:
        errs.append(f"missing:{','.join(missing)}")
    if not isinstance(rec.get("recommendations", []), list):
        errs.append("recommendations_not_list")
    if not isinstance(rec.get("procedure", []), list):
        errs.append("procedure_not_list")
    if not isinstance(rec.get("variables_available", {}), dict):
        errs.append("variables_available_not_object")
    try:
        score = int(rec.get("score_pct", 0))
        if score < 0 or score > 100:
            errs.append("score_out_of_range")
    except Exception:
        errs.append("score_not_int")
    if rec.get("readiness") not in {"good", "watch", "risky"}:
        errs.append("readiness_invalid")
    return errs


def _evaluate_tuning_recommendation_quality(
    *,
    recommendation: Dict[str, Any],
    telemetry: Dict[str, Any],
    trace_paths: list[pathlib.Path],
    replay_reports: list[Dict[str, Any]],
    surrogate_report: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    telemetry_map = telemetry if isinstance(telemetry, dict) else {}
    rec_map = recommendation if isinstance(recommendation, dict) else {}
    replay_rows = replay_reports if isinstance(replay_reports, list) else []
    trace_rows = trace_paths if isinstance(trace_paths, list) else []
    surrogate_map = surrogate_report if isinstance(surrogate_report, dict) else {}

    dims: Dict[str, Dict[str, Any]] = {
        "completeness": {"ok": True, "reasons": []},
        "confidence": {"ok": True, "reasons": []},
        "actionability": {"ok": True, "reasons": []},
    }

    def add_reason(dim: str, reason: str) -> None:
        node = dims.get(dim)
        if not isinstance(node, dict):
            return
        bucket = node.get("reasons")
        if not isinstance(bucket, list):
            bucket = []
            node["reasons"] = bucket
        if reason not in bucket:
            bucket.append(reason)
        node["ok"] = False

    # Completeness: require core telemetry keys and at least one replay trace.
    required_telemetry = [
        "angle_variance",
        "output_saturation_pct",
        "oscillation_detected",
        "oscillation_freq_hz",
    ]
    missing_telemetry = [k for k in required_telemetry if k not in telemetry_map]
    if missing_telemetry:
        add_reason(
            "completeness",
            "telemetry_fields_missing:" + ",".join(missing_telemetry[:8]),
        )
    if not trace_rows:
        add_reason("completeness", "evidence_missing_trace_paths")

    # Confidence: ensure recommendation score and evidence quality are sufficient.
    try:
        rec_score = int(rec_map.get("score_pct", 0))
    except Exception:
        rec_score = 0
    if rec_score < 60:
        add_reason("confidence", "recommendation_score_low")

    replay_fail_count = sum(
        1
        for rep in replay_rows
        if not bool(
            ((rep.get("result") or {}) if isinstance(rep, dict) else {}).get(
                "pass", False
            )
        )
    )
    if replay_fail_count > 0:
        add_reason("confidence", f"replay_failures:{replay_fail_count}")

    if surrogate_map:
        if bool(surrogate_map.get("ok", False)):
            sim = (
                surrogate_map.get("simulation")
                if isinstance(surrogate_map.get("simulation"), dict)
                else {}
            )
            sim_metrics = (
                sim.get("metrics") if isinstance(sim.get("metrics"), dict) else {}
            )
            if bool(sim_metrics.get("faceplant", False)):
                add_reason("confidence", "surrogate_faceplant_risk")
            model = (
                surrogate_map.get("model")
                if isinstance(surrogate_map.get("model"), dict)
                else {}
            )
            try:
                model_conf = float(model.get("confidence", 0.0) or 0.0)
            except Exception:
                model_conf = 0.0
            if model_conf < 0.35:
                add_reason("confidence", "surrogate_confidence_low")
        else:
            if trace_rows:
                add_reason("confidence", "surrogate_unavailable")

    # Actionability: recommendation and procedure should be directly executable.
    rec_items = rec_map.get("recommendations")
    if not isinstance(rec_items, list) or not rec_items:
        add_reason("actionability", "recommendations_missing")
    else:
        actionable_count = 0
        for row in rec_items:
            if not isinstance(row, dict):
                continue
            action = str(row.get("action", "")).strip()
            rationale = str(row.get("rationale", "")).strip()
            if action and rationale:
                actionable_count += 1
        if actionable_count == 0:
            add_reason("actionability", "recommendations_not_actionable")

    procedure = rec_map.get("procedure")
    if not isinstance(procedure, list) or len(procedure) < 3:
        add_reason("actionability", "procedure_incomplete")

    variables = rec_map.get("variables_available")
    if not isinstance(variables, dict) or not variables:
        add_reason("actionability", "variables_available_missing")

    reasons: list[str] = []
    for dim in ("completeness", "confidence", "actionability"):
        node = dims.get(dim) or {}
        for reason in list(node.get("reasons") or []):
            s = str(reason).strip()
            if s and s not in reasons:
                reasons.append(s)

    gate_ok = len(reasons) == 0
    return {
        "gate_ok": gate_ok,
        "reasons": reasons,
        "dimensions": dims,
        "evidence": {
            "trace_count": len(trace_rows),
            "replay_count": len(replay_rows),
            "replay_fail_count": replay_fail_count,
            "surrogate_ok": bool(surrogate_map.get("ok", False))
            if surrogate_map
            else False,
            "recommendation_score_pct": rec_score,
        },
    }


def _build_tuning_apply_signature(family: str, target: Dict[str, Any]) -> str:
    canonical = json.dumps(
        {"family": family, "target": target},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# TuningPreflightStore moved to domain module
def _requires_preflight(
    *,
    family: str,
    status_before: Dict[str, Any],
    current: Dict[str, float],
    target: Dict[str, float],
) -> bool:
    mode = str(status_before.get("mode", ""))
    if mode in {"ARMED", "BALANCING"}:
        return True

    if family == "pid":
        d = TUNING_PREFLIGHT_DELTA["pid"]
        return (
            abs(target["kp"] - current["kp"]) > d["kp"]
            or abs(target["ki"] - current["ki"]) > d["ki"]
            or abs(target["kd"] - current["kd"]) > d["kd"]
        )
    if family == "motion":
        d = TUNING_PREFLIGHT_DELTA["motion"]
        return (
            abs(target["kv"] - current["kv"]) > d["kv"]
            or abs(target["kx"] - current["kx"]) > d["kx"]
        )
    if family == "setpoint":
        return (
            abs(target["deg"] - current["deg"])
            > TUNING_PREFLIGHT_DELTA["setpoint"]["deg"]
        )
    if family == "limits":
        d = TUNING_PREFLIGHT_DELTA["limits"]
        return (
            abs(target["out_max"] - current["out_max"]) > d["out_max"]
            or abs(target["tip_deg"] - current["tip_deg"]) > d["tip_deg"]
            or abs(target["i_max"] - current["i_max"]) > d["i_max"]
        )
    return False


def _enforce_preflight_if_needed(
    *,
    preflight_store: "TuningPreflightStore",
    body: Dict[str, Any],
    family: str,
    status_before: Dict[str, Any],
    current: Dict[str, float],
    target: Dict[str, float],
) -> Optional[str]:
    if not _requires_preflight(
        family=family, status_before=status_before, current=current, target=target
    ):
        return None
    preflight_id = str(body.get("preflight_id", "")).strip()
    if not preflight_id:
        raise RuntimeError("preflight_required")
    signature = _build_tuning_apply_signature(family, target)
    preflight_store.validate(preflight_id, signature)
    return preflight_id

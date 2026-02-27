"""
Tuning route handlers extracted from server.py (Phase B/C).

These handlers manage tuning capabilities, recommendations, and preflight checks.
"""
from typing import Any, Callable, Dict, List, Optional, Tuple
import pathlib

try:
    from app.bridge.clean_tuning import (
        build_tuning_preflight_payload,
        build_tuning_recommend_payload,
    )
    from app.bridge.clean_misc import build_capabilities_payload
except ImportError:
    from clean_tuning import (  # type: ignore
        build_tuning_preflight_payload,
        build_tuning_recommend_payload,
    )
    from clean_misc import build_capabilities_payload  # type: ignore


def _parse_current_params(
    current_raw: Dict[str, Any],
    status_now: Dict[str, Any],
    status_float_fn: Callable[..., float],
) -> Dict[str, Any]:
    """Parse current tuning parameters from request body with status fallbacks."""
    return {
        "kp": float(
            current_raw.get("kp", status_float_fn(status_now, "kp", default=31.0))
        ),
        "ki": float(
            current_raw.get("ki", status_float_fn(status_now, "ki", default=0.05))
        ),
        "kd": float(
            current_raw.get("kd", status_float_fn(status_now, "kd", default=1.05))
        ),
        "kv": float(
            current_raw.get("kv", status_float_fn(status_now, "kv", default=0.0))
        ),
        "kx": float(
            current_raw.get("kx", status_float_fn(status_now, "kx", default=0.0))
        ),
        "setpoint": float(
            current_raw.get(
                "setpoint", status_float_fn(status_now, "set", default=0.0)
            )
        ),
        "out_max": float(
            current_raw.get(
                "out_max",
                status_float_fn(status_now, "outMax", "out_max", default=180.0),
            )
        ),
        "tip_deg": float(
            current_raw.get(
                "tip_deg",
                status_float_fn(status_now, "tipDeg", "tip_deg", default=35.0),
            )
        ),
        "i_max": float(
            current_raw.get(
                "i_max", status_float_fn(status_now, "iMax", "i_max", default=70.0)
            )
        ),
        "lowpass_cutoff_hz": float(current_raw.get("lowpass_cutoff_hz", 8.0)),
        "conditional_integration": bool(
            current_raw.get("conditional_integration", False)
        ),
    }


def _parse_telemetry(
    telemetry_raw: Dict[str, Any], mode_fallback: str = ""
) -> Dict[str, Any]:
    """Parse telemetry parameters from request body."""
    return {
        "angle_variance": float(telemetry_raw.get("angle_variance", 0.0)),
        "output_saturation_pct": float(
            telemetry_raw.get("output_saturation_pct", 0.0)
        ),
        "oscillation_detected": bool(telemetry_raw.get("oscillation_detected", False)),
        "oscillation_freq_hz": float(telemetry_raw.get("oscillation_freq_hz", 0.0)),
        "mode": str(telemetry_raw.get("mode", mode_fallback)),
    }


def _clean_trace_paths(
    raw_paths: List[Any], repo_root: pathlib.Path
) -> Tuple[List[pathlib.Path], Optional[str]]:
    """Clean and validate trace paths, returning (cleaned_paths, error_or_none)."""
    cleaned: List[pathlib.Path] = []
    if not isinstance(raw_paths, list):
        return cleaned, None

    for raw in raw_paths[:8]:
        p = pathlib.Path(str(raw))
        if not p.is_absolute():
            p = (repo_root / p).resolve()
        try:
            p.relative_to(repo_root.resolve())
        except Exception:
            return [], "trace_path_outside_repo"
        if p.exists():
            cleaned.append(p)

    return cleaned, None


def _run_replay(
    cleaned: List[pathlib.Path],
    replay_file: Optional[Callable[..., Dict[str, Any]]],
    i_limit: float,
    out_limit: float,
) -> List[Dict[str, Any]]:
    """Run replay on trace files."""
    replay_reports: List[Dict[str, Any]] = []
    if not cleaned or replay_file is None:
        return replay_reports

    for p in cleaned:
        try:
            replay_reports.append(
                replay_file(p, i_limit=i_limit, out_limit=out_limit, cmd_vel=0.0)
            )
        except Exception as exc:
            replay_reports.append(
                {
                    "trace": str(p),
                    "result": {"ok": False, "pass": False, "error": str(exc)},
                }
            )
    return replay_reports


def _run_surrogate(
    cleaned: List[pathlib.Path],
    simulate_from_logs: Optional[Callable[..., Dict[str, Any]]],
    current: Dict[str, Any],
    duration_s: float,
) -> Optional[Dict[str, Any]]:
    """Run surrogate simulation on trace files."""
    if not cleaned or simulate_from_logs is None:
        return None

    try:
        return simulate_from_logs(
            cleaned,
            kp=float(current["kp"]),
            ki=float(current["ki"]),
            kd=float(current["kd"]),
            setpoint=float(current["setpoint"]),
            duration_s=duration_s,
            i_limit=float(current["i_max"]),
            out_limit=float(current["out_max"]),
        )
    except Exception as exc:
        return {"ok": False, "error": f"surrogate_error:{exc}"}


def handle_tuning_recommend(
    *,
    body: Dict[str, Any],
    repo_root: pathlib.Path,
    evaluate_tuning_plan: Optional[Callable[..., Dict[str, Any]]],
    replay_file: Optional[Callable[..., Dict[str, Any]]],
    simulate_from_logs: Optional[Callable[..., Dict[str, Any]]],
    validate_contract_fn: Callable[[Dict[str, Any]], List[str]],
    evaluate_quality_fn: Callable[..., Dict[str, Any]],
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /tooling/tuning/recommend POST request.

    Returns (status_code, payload).
    """
    if evaluate_tuning_plan is None:
        return 501, {"ok": False, "error": "tuning_policy_unavailable"}

    current_raw = body.get("current", {})
    telemetry_raw = body.get("telemetry", {})
    if not isinstance(current_raw, dict):
        return 400, {"ok": False, "error": "current_object_required"}
    if not isinstance(telemetry_raw, dict):
        telemetry_raw = {}

    current: Dict[str, Any] = {
        "kp": float(current_raw.get("kp", 31.0)),
        "ki": float(current_raw.get("ki", 0.05)),
        "kd": float(current_raw.get("kd", 1.05)),
        "kv": float(current_raw.get("kv", 0.0)),
        "kx": float(current_raw.get("kx", 0.0)),
        "setpoint": float(current_raw.get("setpoint", 0.0)),
        "out_max": float(current_raw.get("out_max", 180.0)),
        "tip_deg": float(current_raw.get("tip_deg", 35.0)),
        "i_max": float(current_raw.get("i_max", 70.0)),
        "lowpass_cutoff_hz": float(current_raw.get("lowpass_cutoff_hz", 8.0)),
        "conditional_integration": bool(
            current_raw.get("conditional_integration", False)
        ),
    }

    telemetry = _parse_telemetry(telemetry_raw)

    raw_paths = body.get("trace_paths", [])
    cleaned, err = _clean_trace_paths(raw_paths, repo_root)
    if err:
        return 400, {"ok": False, "error": err}

    replay_reports = _run_replay(
        cleaned, replay_file, float(current["i_max"]), float(current["out_max"])
    )
    surrogate_report = _run_surrogate(
        cleaned, simulate_from_logs, current, float(body.get("duration_s", 3.0))
    )

    recommendation = evaluate_tuning_plan(
        current=current,
        telemetry=telemetry,
        surrogate=surrogate_report,
        replay_results=replay_reports,
    )

    contract_errors = validate_contract_fn(recommendation)
    if contract_errors:
        return 500, {
            "ok": False,
            "error": "tuning_recommendation_contract_invalid",
            "contract_errors": contract_errors,
        }

    quality_gate = evaluate_quality_fn(
        recommendation=recommendation,
        telemetry=telemetry,
        trace_paths=cleaned,
        replay_reports=replay_reports,
        surrogate_report=surrogate_report,
    )

    return 200, build_tuning_recommend_payload(
        recommendation=recommendation,
        surrogate=surrogate_report,
        replay=replay_reports,
        quality_gate=quality_gate,
    )


def handle_tuning_preflight(
    *,
    body: Dict[str, Any],
    repo_root: pathlib.Path,
    status_now: Dict[str, Any],
    evaluate_tuning_plan: Optional[Callable[..., Dict[str, Any]]],
    replay_file: Optional[Callable[..., Dict[str, Any]]],
    simulate_from_logs: Optional[Callable[..., Dict[str, Any]]],
    validate_contract_fn: Callable[[Dict[str, Any]], List[str]],
    evaluate_quality_fn: Callable[..., Dict[str, Any]],
    build_signature_fn: Callable[[str, Dict[str, float]], str],
    preflight_issue_fn: Callable[..., Dict[str, Any]],
    status_float_fn: Callable[..., float],
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /tooling/tuning/preflight POST request.

    Returns (status_code, payload).
    """
    if evaluate_tuning_plan is None:
        return 501, {"ok": False, "error": "tuning_policy_unavailable"}

    family = str(body.get("family", "")).strip().lower()
    if family not in {"pid", "motion", "setpoint", "limits"}:
        return 400, {"ok": False, "error": "invalid_family"}

    current_raw = body.get("current", {})
    telemetry_raw = body.get("telemetry", {})
    if not isinstance(current_raw, dict):
        current_raw = {}
    if not isinstance(telemetry_raw, dict):
        telemetry_raw = {}

    current = _parse_current_params(current_raw, status_now, status_float_fn)

    target_raw = body.get("target", {})
    if not isinstance(target_raw, dict):
        return 400, {"ok": False, "error": "target_object_required"}

    target: Dict[str, float] = {}
    if family == "pid":
        target = {
            "kp": float(target_raw["kp"]),
            "ki": float(target_raw["ki"]),
            "kd": float(target_raw["kd"]),
        }
    elif family == "motion":
        target = {
            "kv": float(target_raw["kv"]),
            "kx": float(target_raw["kx"]),
        }
    elif family == "setpoint":
        target = {"deg": float(target_raw["deg"])}
    else:  # limits
        target = {
            "out_max": float(target_raw["out_max"]),
            "tip_deg": float(target_raw["tip_deg"]),
            "i_max": float(target_raw["i_max"]),
        }

    telemetry = _parse_telemetry(telemetry_raw, status_now.get("mode", ""))

    raw_paths = body.get("trace_paths", [])
    cleaned, err = _clean_trace_paths(raw_paths, repo_root)
    if err:
        return 400, {"ok": False, "error": err}

    replay_reports = _run_replay(
        cleaned, replay_file, float(current["i_max"]), float(current["out_max"])
    )

    # Apply target to current for simulation
    sim_current = dict(current)
    if family == "pid":
        sim_current["kp"] = target["kp"]
        sim_current["ki"] = target["ki"]
        sim_current["kd"] = target["kd"]
    elif family == "setpoint":
        sim_current["setpoint"] = target["deg"]
    elif family == "limits":
        sim_current["out_max"] = target["out_max"]
        sim_current["i_max"] = target["i_max"]

    surrogate_report = _run_surrogate(
        cleaned, simulate_from_logs, sim_current, float(body.get("duration_s", 3.0))
    )

    recommendation = evaluate_tuning_plan(
        current=sim_current,
        telemetry=telemetry,
        surrogate=surrogate_report,
        replay_results=replay_reports,
    )

    contract_errors = validate_contract_fn(recommendation)
    if contract_errors:
        return 500, {
            "ok": False,
            "error": "tuning_recommendation_contract_invalid",
            "contract_errors": contract_errors,
        }

    quality_gate = evaluate_quality_fn(
        recommendation=recommendation,
        telemetry=telemetry,
        trace_paths=cleaned,
        replay_reports=replay_reports,
        surrogate_report=surrogate_report,
    )

    reasons = list(quality_gate.get("reasons") or [])
    gate_ok = bool(quality_gate.get("gate_ok", False))
    preflight_node: Optional[Dict[str, Any]] = None
    signature = build_signature_fn(family, target)

    if gate_ok:
        preflight_node = preflight_issue_fn(
            family=family,
            signature=signature,
            score_pct=int(recommendation.get("score_pct", 0)),
            notes=["preflight_gate_ok"],
        )

    return 200, build_tuning_preflight_payload(
        gate_ok=gate_ok,
        family=family,
        reasons=reasons,
        recommendation_score_pct=int(recommendation.get("score_pct", 0)),
        signature=signature,
        quality_gate=quality_gate,
        preflight_node=preflight_node,
        recommendation=recommendation,
        surrogate=surrogate_report,
        replay=replay_reports,
    )


def handle_tuning_capabilities_get(
    *,
    gateway: Any,
    cached_probe_fn: Callable[[str], Optional[Dict[str, Any]]],
    detect_tuning_capabilities_fn: Callable[..., Dict[str, Any]],
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /tooling/tuning/capabilities GET request.

    Returns (status_code, payload).
    Checks cached probes first, falls back to status-based detection.
    """
    cached_connect = cached_probe_fn("connect")
    if isinstance(cached_connect, dict) and isinstance(
        cached_connect.get("tuning_capabilities"), dict
    ):
        return 200, build_capabilities_payload(
            capabilities=cached_connect.get("tuning_capabilities"),
            source="connect_probe_cache",
        )

    cached_compat = cached_probe_fn("compat")
    if isinstance(cached_compat, dict) and isinstance(
        cached_compat.get("tuning_capabilities"), dict
    ):
        return 200, build_capabilities_payload(
            capabilities=cached_compat.get("tuning_capabilities"),
            source="compat_probe_cache",
        )

    status = dict(gateway.health().get("last_status", {}))
    if not status:
        try:
            status = gateway.get_status()
        except Exception:
            status = {}

    caps = detect_tuning_capabilities_fn(status, [], [])
    return 200, build_capabilities_payload(capabilities=caps, source="status_only")


def handle_pid_post(
    *,
    body: Dict[str, Any],
    gateway: Any,
    control: Any,
    config_history: Any,
    tuning_preflight: Any,
    require_action_allowed_fn: Callable,
    status_float_fn: Callable,
    guard_pid_apply_fn: Callable,
    enforce_preflight_if_needed_fn: Callable,
    build_tuning_result_payload_fn: Callable,
) -> Tuple[int, Dict[str, Any]]:
    """Handle /pid POST request."""
    kp = float(body["kp"])
    ki = float(body["ki"])
    kd = float(body["kd"])
    status_before = gateway.get_status()
    require_action_allowed_fn("pid", gateway, control, status_override=status_before)
    current = {
        "kp": status_float_fn(status_before, "kp", default=31.0),
        "ki": status_float_fn(status_before, "ki", default=0.05),
        "kd": status_float_fn(status_before, "kd", default=1.05),
    }
    target = {"kp": kp, "ki": ki, "kd": kd}
    guard_pid_apply_fn(status_before, kp, ki, kd)
    preflight_used = enforce_preflight_if_needed_fn(
        preflight_store=tuning_preflight,
        body=body,
        family="pid",
        status_before=status_before,
        current=current,
        target=target,
    )
    snap = config_history.save_snapshot(source="/pid", status_before=status_before)
    res = gateway.command(f"PID {kp} {ki} {kd}", expect_contains="OK PID", timeout=2.0)
    return 200, build_tuning_result_payload_fn(
        result=res,
        snapshot=snap,
        status=gateway.get_status(),
        control=control.snapshot(),
        preflight_id=preflight_used,
    )


def handle_motion_post(
    *,
    body: Dict[str, Any],
    gateway: Any,
    control: Any,
    config_history: Any,
    tuning_preflight: Any,
    require_action_allowed_fn: Callable,
    status_float_fn: Callable,
    guard_motion_apply_fn: Callable,
    enforce_preflight_if_needed_fn: Callable,
    build_tuning_result_payload_fn: Callable,
) -> Tuple[int, Dict[str, Any]]:
    """Handle /motion POST request."""
    kv = float(body["kv"])
    kx = float(body["kx"])
    status_before = gateway.get_status()
    require_action_allowed_fn("motion", gateway, control, status_override=status_before)
    current = {
        "kv": status_float_fn(status_before, "kv", default=0.0),
        "kx": status_float_fn(status_before, "kx", default=0.0),
    }
    target = {"kv": kv, "kx": kx}
    guard_motion_apply_fn(status_before, kv, kx)
    preflight_used = enforce_preflight_if_needed_fn(
        preflight_store=tuning_preflight,
        body=body,
        family="motion",
        status_before=status_before,
        current=current,
        target=target,
    )
    snap = config_history.save_snapshot(source="/motion", status_before=status_before)
    res = gateway.command(f"MOTION {kv} {kx}", expect_contains="OK MOTION", timeout=2.0)
    return 200, build_tuning_result_payload_fn(
        result=res,
        snapshot=snap,
        status=gateway.get_status(),
        control=control.snapshot(),
        preflight_id=preflight_used,
    )


def handle_setpoint_post(
    *,
    body: Dict[str, Any],
    gateway: Any,
    control: Any,
    config_history: Any,
    tuning_preflight: Any,
    require_action_allowed_fn: Callable,
    status_float_fn: Callable,
    guard_setpoint_apply_fn: Callable,
    enforce_preflight_if_needed_fn: Callable,
    build_tuning_result_payload_fn: Callable,
) -> Tuple[int, Dict[str, Any]]:
    """Handle /setpoint POST request."""
    deg = float(body["deg"])
    status_before = gateway.get_status()
    require_action_allowed_fn("setpoint", gateway, control, status_override=status_before)
    current = {"deg": status_float_fn(status_before, "set", default=0.0)}
    target = {"deg": deg}
    guard_setpoint_apply_fn(status_before, deg)
    preflight_used = enforce_preflight_if_needed_fn(
        preflight_store=tuning_preflight,
        body=body,
        family="setpoint",
        status_before=status_before,
        current=current,
        target=target,
    )
    snap = config_history.save_snapshot(source="/setpoint", status_before=status_before)
    res = gateway.command(f"SETPOINT {deg}", expect_contains="OK SETPOINT", timeout=2.0)
    return 200, build_tuning_result_payload_fn(
        result=res,
        snapshot=snap,
        status=gateway.get_status(),
        control=control.snapshot(),
        preflight_id=preflight_used,
    )


def handle_limits_post(
    *,
    body: Dict[str, Any],
    gateway: Any,
    control: Any,
    config_history: Any,
    tuning_preflight: Any,
    require_action_allowed_fn: Callable,
    status_float_fn: Callable,
    guard_limits_apply_fn: Callable,
    enforce_preflight_if_needed_fn: Callable,
    build_tuning_result_payload_fn: Callable,
) -> Tuple[int, Dict[str, Any]]:
    """Handle /limits POST request."""
    out_max = float(body["out_max"])
    tip_deg = float(body["tip_deg"])
    i_max = float(body["i_max"])
    status_before = gateway.get_status()
    require_action_allowed_fn("limits", gateway, control, status_override=status_before)
    current = {
        "out_max": status_float_fn(status_before, "outMax", "out_max", default=180.0),
        "tip_deg": status_float_fn(status_before, "tipDeg", "tip_deg", default=35.0),
        "i_max": status_float_fn(status_before, "iMax", "i_max", default=70.0),
    }
    target = {"out_max": out_max, "tip_deg": tip_deg, "i_max": i_max}
    guard_limits_apply_fn(status_before, out_max, tip_deg, i_max)
    preflight_used = enforce_preflight_if_needed_fn(
        preflight_store=tuning_preflight,
        body=body,
        family="limits",
        status_before=status_before,
        current=current,
        target=target,
    )
    snap = config_history.save_snapshot(source="/limits", status_before=status_before)
    res = gateway.command(
        f"LIMITS {out_max} {tip_deg} {i_max}",
        expect_contains="OK LIMITS",
        timeout=2.0,
    )
    return 200, build_tuning_result_payload_fn(
        result=res,
        snapshot=snap,
        status=gateway.get_status(),
        control=control.snapshot(),
        preflight_id=preflight_used,
    )


def _first_float(status: Dict[str, Any], *keys: str) -> Optional[float]:
    for k in keys:
        val = status.get(k)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass
    return None


def _safe_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def apply_tuning_plan(
    gateway: Any,
    config_history: Any,
    plan: Dict[str, Any],
    *,
    source: str,
) -> Dict[str, Any]:
    """Apply a tuning plan (PID, motion, setpoint, limits) to the gateway."""
    status_before = gateway.get_status()
    curr_kp = _first_float(status_before, "kp")
    curr_ki = _first_float(status_before, "ki")
    curr_kd = _first_float(status_before, "kd")
    curr_kv = _first_float(status_before, "kv")
    curr_kx = _first_float(status_before, "kx")
    curr_set = _first_float(status_before, "set")
    curr_out_max = _first_float(status_before, "outMax", "out_max")
    curr_tip_deg = _first_float(status_before, "tipDeg", "tip_deg")
    curr_i_max = _first_float(status_before, "iMax", "i_max")
    snap = config_history.save_snapshot(
        source=source, status_before=status_before, note="auto-pre-apply"
    )
    actions: list[str] = []
    changed: Dict[str, Any] = {}
    if "pid" in plan:
        p = plan["pid"]
        kp = _safe_float(p.get("kp")) if isinstance(p, dict) else None
        ki = _safe_float(p.get("ki")) if isinstance(p, dict) else None
        kd = _safe_float(p.get("kd")) if isinstance(p, dict) else None
        if kp is None:
            kp = curr_kp
        if ki is None:
            ki = curr_ki
        if kd is None:
            kd = curr_kd
        if kp is None or ki is None or kd is None:
            raise RuntimeError("apply_pid_missing_current_values")
        gateway.command(f"PID {kp} {ki} {kd}", expect_contains="OK PID", timeout=2.0)
        actions.append("pid")
        changed["pid"] = {
            "before": {"kp": curr_kp, "ki": curr_ki, "kd": curr_kd},
            "target": {"kp": kp, "ki": ki, "kd": kd},
        }
    if "motion" in plan:
        m = plan["motion"]
        kv = _safe_float(m.get("kv")) if isinstance(m, dict) else None
        kx = _safe_float(m.get("kx")) if isinstance(m, dict) else None
        if kv is None:
            kv = curr_kv
        if kx is None:
            kx = curr_kx
        if kv is None or kx is None:
            raise RuntimeError("apply_motion_missing_current_values")
        gateway.command(f"MOTION {kv} {kx}", expect_contains="OK MOTION", timeout=2.0)
        actions.append("motion")
        changed["motion"] = {
            "before": {"kv": curr_kv, "kx": curr_kx},
            "target": {"kv": kv, "kx": kx},
        }
    if "setpoint" in plan:
        s = plan["setpoint"]
        deg = _safe_float(s.get("deg")) if isinstance(s, dict) else None
        if deg is None:
            deg = curr_set
        if deg is None:
            raise RuntimeError("apply_setpoint_missing_current_value")
        gateway.command(f"SETPOINT {deg}", expect_contains="OK SETPOINT", timeout=2.0)
        actions.append("setpoint")
        changed["setpoint"] = {"before": {"deg": curr_set}, "target": {"deg": deg}}
    if "limits" in plan:
        limits_cfg = plan["limits"]
        out_max = (
            _safe_float(limits_cfg.get("out_max"))
            if isinstance(limits_cfg, dict)
            else None
        )
        tip_deg = (
            _safe_float(limits_cfg.get("tip_deg"))
            if isinstance(limits_cfg, dict)
            else None
        )
        i_max = (
            _safe_float(limits_cfg.get("i_max"))
            if isinstance(limits_cfg, dict)
            else None
        )
        if out_max is None:
            out_max = curr_out_max
        if tip_deg is None:
            tip_deg = curr_tip_deg
        if i_max is None:
            i_max = curr_i_max
        if out_max is None or tip_deg is None or i_max is None:
            raise RuntimeError("apply_limits_missing_current_values")
        gateway.command(
            f"LIMITS {out_max} {tip_deg} {i_max}",
            expect_contains="OK LIMITS",
            timeout=2.0,
        )
        actions.append("limits")
        changed["limits"] = {
            "before": {
                "out_max": curr_out_max,
                "tip_deg": curr_tip_deg,
                "i_max": curr_i_max,
            },
            "target": {"out_max": out_max, "tip_deg": tip_deg, "i_max": i_max},
        }
    return {
        "ok": True,
        "snapshot_id": snap["snapshot_id"],
        "applied": actions,
        "changed": changed,
        "status": gateway.get_status(),
    }


def sanitize_apply_plan(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize and validate an apply plan for tuning operations."""
    out: Dict[str, Any] = {}
    pid = raw.get("pid")
    if isinstance(pid, dict):
        kp = _safe_float(pid.get("kp"))
        ki = _safe_float(pid.get("ki"))
        kd = _safe_float(pid.get("kd"))
        partial: Dict[str, float] = {}
        if kp is not None:
            partial["kp"] = kp
        if ki is not None:
            partial["ki"] = ki
        if kd is not None:
            partial["kd"] = kd
        if partial:
            out["pid"] = partial
    motion = raw.get("motion")
    if isinstance(motion, dict):
        kv = _safe_float(motion.get("kv"))
        kx = _safe_float(motion.get("kx"))
        partial_m: Dict[str, float] = {}
        if kv is not None:
            partial_m["kv"] = kv
        if kx is not None:
            partial_m["kx"] = kx
        if partial_m:
            out["motion"] = partial_m
    setpoint = raw.get("setpoint")
    if isinstance(setpoint, dict):
        deg = _safe_float(setpoint.get("deg"))
        if deg is not None:
            out["setpoint"] = {"deg": deg}
    else:
        deg = _safe_float(setpoint)
        if deg is not None:
            out["setpoint"] = {"deg": deg}
    limits = raw.get("limits")
    if isinstance(limits, dict):
        out_max = _safe_float(limits.get("out_max"))
        tip_deg = _safe_float(limits.get("tip_deg"))
        i_max = _safe_float(limits.get("i_max"))
        partial_l: Dict[str, float] = {}
        if out_max is not None:
            partial_l["out_max"] = out_max
        if tip_deg is not None:
            partial_l["tip_deg"] = tip_deg
        if i_max is not None:
            partial_l["i_max"] = i_max
        if partial_l:
            out["limits"] = partial_l
    unified = raw.get("unified")
    if isinstance(unified, dict):
        profile = unified.get("profile")
        sketch_name = unified.get("sketch_name")
        if isinstance(profile, dict):
            part_u: Dict[str, Any] = {"profile": profile}
            if isinstance(sketch_name, str) and sketch_name.strip():
                part_u["sketch_name"] = sketch_name.strip()
            out["unified"] = part_u
    sketch = raw.get("sketch")
    if isinstance(sketch, dict):
        content = sketch.get("content")
        path = sketch.get("path")
        if isinstance(content, str) and content.strip():
            part_s: Dict[str, Any] = {"content": content}
            if isinstance(path, str) and path.strip():
                part_s["path"] = path.strip()
            out["sketch"] = part_s
    return out


def revert_snapshot(
    gateway: Any,
    config_history: Any,
    *,
    snapshot_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Revert tuning parameters to a saved snapshot."""
    snap = config_history.get_snapshot(snapshot_id=snapshot_id)
    if not snap:
        raise RuntimeError("snapshot_not_found")
    vals = snap.get("values", {})
    pid = vals.get("pid", {}) if isinstance(vals, dict) else {}
    motion = vals.get("motion", {}) if isinstance(vals, dict) else {}
    setpoint = vals.get("setpoint", {}) if isinstance(vals, dict) else {}
    limits = vals.get("limits", {}) if isinstance(vals, dict) else {}
    actions: list[str] = []
    if all(_safe_float(pid.get(k)) is not None for k in ("kp", "ki", "kd")):
        gateway.command(
            f"PID {float(pid['kp'])} {float(pid['ki'])} {float(pid['kd'])}",
            expect_contains="OK PID",
            timeout=2.0,
        )
        actions.append("pid")
    if all(_safe_float(motion.get(k)) is not None for k in ("kv", "kx")):
        gateway.command(
            f"MOTION {float(motion['kv'])} {float(motion['kx'])}",
            expect_contains="OK MOTION",
            timeout=2.0,
        )
        actions.append("motion")
    if _safe_float(setpoint.get("deg")) is not None:
        gateway.command(
            f"SETPOINT {float(setpoint['deg'])}",
            expect_contains="OK SETPOINT",
            timeout=2.0,
        )
        actions.append("setpoint")
    if all(
        _safe_float(limits.get(k)) is not None for k in ("out_max", "tip_deg", "i_max")
    ):
        gateway.command(
            f"LIMITS {float(limits['out_max'])} {float(limits['tip_deg'])} {float(limits['i_max'])}",
            expect_contains="OK LIMITS",
            timeout=2.0,
        )
        actions.append("limits")
    return {
        "ok": True,
        "snapshot_id": snap.get("snapshot_id"),
        "reverted": actions,
        "status": gateway.get_status(),
    }

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

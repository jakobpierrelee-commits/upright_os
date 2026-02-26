"""
Tooling route handlers extracted from server.py (Phase C).

These handlers manage trace replay, parameter sweeps, and surrogate simulation.
"""
from typing import Any, Callable, Dict, List, Optional, Tuple
import pathlib

try:
    from app.bridge.clean_misc import (
        build_replay_payload,
        build_surrogate_simulate_payload,
        build_sweep_payload,
    )
except ImportError:
    from clean_misc import (  # type: ignore
        build_replay_payload,
        build_surrogate_simulate_payload,
        build_sweep_payload,
    )


def handle_trace_replay(
    *,
    body: Dict[str, Any],
    repo_root: pathlib.Path,
    replay_file: Optional[Callable[..., Dict[str, Any]]],
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /tooling/trace-replay POST request.

    Returns (status_code, payload).
    """
    if replay_file is None:
        return 501, {"ok": False, "error": "trace_replay_unavailable"}

    trace_path_raw = str(body.get("trace_path", "")).strip()
    if not trace_path_raw:
        return 400, {"ok": False, "error": "trace_path_required"}

    trace_path = pathlib.Path(trace_path_raw)
    if not trace_path.is_absolute():
        trace_path = (repo_root / trace_path).resolve()

    try:
        trace_path.relative_to(repo_root.resolve())
    except Exception:
        return 400, {"ok": False, "error": "trace_path_outside_repo"}

    if not trace_path.exists():
        return 404, {"ok": False, "error": "trace_not_found"}

    out = replay_file(
        trace_path,
        i_limit=float(body.get("i_limit", 70.0)),
        out_limit=float(body.get("out_limit", 180.0)),
        cmd_vel=float(body.get("cmd_vel", 0.0)),
        cmd_rmse_max=float(body.get("cmd_rmse_max", 6.0)),
        cmd_abs_max=float(body.get("cmd_abs_max", 20.0)),
    )
    return 200, build_replay_payload(replay=out)


def handle_param_sweep(
    *,
    body: Dict[str, Any],
    gateway: Any,
    ParameterSweepRunner: Optional[type],
    parse_range_spec: Optional[Callable[[str], List[float]]],
    SweepConfig: Optional[type],
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /tooling/param-sweep POST request.

    Returns (status_code, payload).
    """
    if ParameterSweepRunner is None or parse_range_spec is None or SweepConfig is None:
        return 501, {"ok": False, "error": "param_sweep_unavailable"}

    try:
        cfg = SweepConfig(
            kp_values=parse_range_spec(str(body.get("kp_spec", "31,32"))),
            ki_values=parse_range_spec(str(body.get("ki_spec", "0.05,0.06"))),
            kd_values=parse_range_spec(str(body.get("kd_spec", "1.0,1.2"))),
            settle_s=float(body.get("settle_s", 1.0)),
            observe_s=float(body.get("observe_s", 2.0)),
            sample_rate_hz=float(body.get("sample_rate_hz", 8.0)),
            max_angle_variance=float(body.get("max_angle_variance", 8.0)),
            max_output_saturation_pct=float(body.get("max_output_saturation_pct", 85.0)),
            require_no_oscillation=bool(body.get("require_no_oscillation", False)),
            max_candidates=int(body.get("max_candidates", 120)),
            rollback_on_fail=bool(body.get("rollback_on_fail", True)),
            restore_baseline_at_end=bool(body.get("restore_baseline_at_end", True)),
            dry_run=bool(body.get("dry_run", False)),
        )
        runner = ParameterSweepRunner(gateway)
        report = runner.run(cfg)
        return 200, build_sweep_payload(sweep=report)
    except Exception as exc:
        return 500, {"ok": False, "error": f"param_sweep_error:{exc}"}


def handle_surrogate_simulate(
    *,
    body: Dict[str, Any],
    repo_root: pathlib.Path,
    simulate_from_logs: Optional[Callable[..., Dict[str, Any]]],
) -> Tuple[int, Dict[str, Any]]:
    """
    Handle /tooling/surrogate/simulate POST request.

    Returns (status_code, payload).
    """
    if simulate_from_logs is None:
        return 501, {"ok": False, "error": "surrogate_unavailable"}

    raw_paths = body.get("trace_paths", [])
    if not isinstance(raw_paths, list) or not raw_paths:
        return 400, {"ok": False, "error": "trace_paths_required"}

    cleaned: List[pathlib.Path] = []
    for raw in raw_paths[:12]:
        p = pathlib.Path(str(raw))
        if not p.is_absolute():
            p = (repo_root / p).resolve()
        try:
            p.relative_to(repo_root.resolve())
        except Exception:
            return 400, {"ok": False, "error": "trace_path_outside_repo"}
        if p.exists():
            cleaned.append(p)

    if not cleaned:
        return 404, {"ok": False, "error": "no_valid_trace_paths"}

    try:
        report = simulate_from_logs(
            cleaned,
            kp=float(body.get("kp", 31.0)),
            ki=float(body.get("ki", 0.05)),
            kd=float(body.get("kd", 1.05)),
            setpoint=float(body.get("setpoint", 0.0)),
            duration_s=float(body.get("duration_s", 3.0)),
        )
        code = 200 if bool(report.get("ok")) else 422
        return code, build_surrogate_simulate_payload(
            ok=bool(report.get("ok")), surrogate=report
        )
    except Exception as exc:
        return 500, {"ok": False, "error": f"surrogate_error:{exc}"}

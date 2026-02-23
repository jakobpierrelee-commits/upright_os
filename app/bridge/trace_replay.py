"""
Trace replay utilities for control-law regression testing.

Replays recorded run CSV files through firmware-parity control math and
compares predicted control outputs to recorded telemetry.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from app.bridge.control_math import PidState, balance_control_step
except ImportError:
    from control_math import PidState, balance_control_step


@dataclass
class ReplaySample:
    t_s: float
    setpoint_deg: float
    angle_deg: float
    wheel_speed: float
    wheel_pos: float
    kp: float
    ki: float
    kd: float
    kv: float
    kx: float
    cmd_measured: float
    pid_measured: Optional[float] = None
    motion_measured: Optional[float] = None


def _rmse(values: List[float]) -> float:
    if not values:
        return 0.0
    return math.sqrt(sum(v * v for v in values) / len(values))


def _as_float(
    row: Dict[str, str], keys: List[str], default: Optional[float] = None
) -> float:
    for key in keys:
        if key in row and row[key] not in ("", None):
            return float(row[key])
    if default is not None:
        return default
    raise KeyError(f"missing required keys {keys}")


def load_trace_csv(path: Path) -> List[ReplaySample]:
    """
    Load commissioning/run CSV format into replay samples.
    """
    samples: List[ReplaySample] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                ms = _as_float(row, ["ms"], default=0.0)
                sample = ReplaySample(
                    t_s=ms / 1000.0,
                    setpoint_deg=_as_float(row, ["setpoint", "set"], default=0.0),
                    angle_deg=_as_float(row, ["angle", "ang"]),
                    wheel_speed=_as_float(row, ["wspd"], default=0.0),
                    wheel_pos=_as_float(row, ["wpos"], default=0.0),
                    kp=_as_float(row, ["kp"]),
                    ki=_as_float(row, ["ki"]),
                    kd=_as_float(row, ["kd"]),
                    kv=_as_float(row, ["kv"], default=0.0),
                    kx=_as_float(row, ["kx"], default=0.0),
                    cmd_measured=_as_float(row, ["cmdL", "out"]),
                    pid_measured=_as_float(row, ["pid"], default=0.0),
                    motion_measured=_as_float(row, ["motion", "mot"], default=0.0),
                )
                samples.append(sample)
            except Exception:
                continue
    return samples


def replay_trace(
    samples: List[ReplaySample],
    *,
    i_limit: float = 70.0,
    out_limit: float = 180.0,
    cmd_vel: float = 0.0,
) -> Dict[str, Any]:
    if len(samples) < 3:
        return {
            "ok": False,
            "error": "insufficient_samples",
            "sample_count": len(samples),
        }

    state = PidState(integrator=0.0, prev_angle=samples[0].angle_deg)
    pos_ref = samples[0].wheel_pos

    cmd_errors: List[float] = []
    pid_errors: List[float] = []
    motion_errors: List[float] = []

    predicted_rows: List[Dict[str, float]] = []
    for idx in range(1, len(samples)):
        curr = samples[idx]
        prev = samples[idx - 1]
        dt = curr.t_s - prev.t_s
        if dt <= 0.0:
            continue

        pred = balance_control_step(
            state,
            setpoint_deg=curr.setpoint_deg,
            angle_deg=curr.angle_deg,
            wheel_speed=curr.wheel_speed,
            cmd_vel=cmd_vel,
            pos_ref=pos_ref,
            wheel_pos=curr.wheel_pos,
            kp=curr.kp,
            ki=curr.ki,
            kd=curr.kd,
            kv=curr.kv,
            kx=curr.kx,
            i_limit=i_limit,
            out_limit=out_limit,
            dt=dt,
        )

        cmd_err = pred.command - curr.cmd_measured
        pid_err = pred.angle_out - (
            curr.pid_measured if curr.pid_measured is not None else 0.0
        )
        mot_err = pred.motion_out - (
            curr.motion_measured if curr.motion_measured is not None else 0.0
        )

        cmd_errors.append(cmd_err)
        pid_errors.append(pid_err)
        motion_errors.append(mot_err)

        predicted_rows.append(
            {
                "t_s": curr.t_s,
                "command_pred": pred.command,
                "command_measured": curr.cmd_measured,
                "command_error": cmd_err,
                "pid_pred": pred.angle_out,
                "pid_measured": curr.pid_measured
                if curr.pid_measured is not None
                else 0.0,
                "motion_pred": pred.motion_out,
                "motion_measured": curr.motion_measured
                if curr.motion_measured is not None
                else 0.0,
            }
        )

    if not cmd_errors:
        return {
            "ok": False,
            "error": "no_replayable_rows",
            "sample_count": len(samples),
        }

    summary = {
        "sample_count": len(cmd_errors),
        "rmse_command": _rmse(cmd_errors),
        "max_abs_command_error": max(abs(v) for v in cmd_errors),
        "rmse_pid": _rmse(pid_errors),
        "rmse_motion": _rmse(motion_errors),
    }

    return {
        "ok": True,
        "summary": summary,
        "rows": predicted_rows,
    }


def evaluate_replay(
    report: Dict[str, Any],
    *,
    cmd_rmse_max: float = 6.0,
    cmd_abs_max: float = 20.0,
) -> Dict[str, Any]:
    if not report.get("ok"):
        return {
            "ok": False,
            "pass": False,
            "error": report.get("error", "replay_failed"),
        }

    summary = report["summary"]
    checks = [
        {
            "id": "cmd_rmse",
            "ok": summary["rmse_command"] <= cmd_rmse_max,
            "value": summary["rmse_command"],
            "threshold": cmd_rmse_max,
        },
        {
            "id": "cmd_abs_max",
            "ok": summary["max_abs_command_error"] <= cmd_abs_max,
            "value": summary["max_abs_command_error"],
            "threshold": cmd_abs_max,
        },
    ]
    return {
        "ok": True,
        "pass": all(c["ok"] for c in checks),
        "checks": checks,
        "summary": summary,
    }


def replay_file(
    trace_path: Path,
    *,
    i_limit: float = 70.0,
    out_limit: float = 180.0,
    cmd_vel: float = 0.0,
    cmd_rmse_max: float = 6.0,
    cmd_abs_max: float = 20.0,
) -> Dict[str, Any]:
    samples = load_trace_csv(trace_path)
    replay = replay_trace(
        samples, i_limit=i_limit, out_limit=out_limit, cmd_vel=cmd_vel
    )
    verdict = evaluate_replay(
        replay, cmd_rmse_max=cmd_rmse_max, cmd_abs_max=cmd_abs_max
    )
    return {
        "trace": str(trace_path),
        "result": verdict,
        "replay": replay,
    }


def to_json(data: Dict[str, Any]) -> str:
    return json.dumps(data, indent=2, sort_keys=True)

"""
Log-calibrated surrogate simulator for quick gain what-if predictions.

This is intentionally lightweight: fit first-order local dynamics from CSV logs,
then roll forward a synthetic closed-loop run with candidate gains.
"""

from __future__ import annotations

import csv
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


@dataclass
class Row:
    t_s: float
    ang: float
    gyro: float
    out: float
    setpoint: float
    kp: float
    ki: float
    kd: float


def _f(row: Dict[str, str], keys: Sequence[str], default: Optional[float] = None) -> float:
    for k in keys:
        v = row.get(k)
        if v in (None, ""):
            continue
        try:
            return float(v)
        except Exception:
            continue
    if default is not None:
        return default
    raise KeyError(f"missing keys {keys}")


def _t_s(row: Dict[str, str]) -> float:
    if "ms" in row and row.get("ms") not in (None, ""):
        return float(row["ms"]) / 1000.0
    if "host_ts" in row and row.get("host_ts") not in (None, ""):
        return float(row["host_ts"])
    raise KeyError("missing time column")


def load_rows(path: Path) -> List[Row]:
    out: List[Row] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                out.append(
                    Row(
                        t_s=_t_s(row),
                        ang=_f(row, ["angle", "ang"]),
                        gyro=_f(row, ["gyro", "gyr", "gx"], default=0.0),
                        out=_f(row, ["cmdL", "out"], default=0.0),
                        setpoint=_f(row, ["setpoint", "set"], default=0.0),
                        kp=_f(row, ["kp"], default=0.0),
                        ki=_f(row, ["ki"], default=0.0),
                        kd=_f(row, ["kd"], default=0.0),
                    )
                )
            except Exception:
                continue
    return out


def _solve_linear(a: List[List[float]], b: List[float]) -> List[float]:
    n = len(a)
    aug = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        pivot = col
        best = abs(aug[col][col])
        for r in range(col + 1, n):
            cand = abs(aug[r][col])
            if cand > best:
                best = cand
                pivot = r
        if best < 1e-12:
            continue
        if pivot != col:
            aug[col], aug[pivot] = aug[pivot], aug[col]

        div = aug[col][col]
        for j in range(col, n + 1):
            aug[col][j] /= div

        for r in range(n):
            if r == col:
                continue
            fac = aug[r][col]
            if abs(fac) < 1e-18:
                continue
            for j in range(col, n + 1):
                aug[r][j] -= fac * aug[col][j]

    return [aug[i][n] for i in range(n)]


def _fit_linear(xs: Iterable[List[float]], ys: Iterable[float], l2: float = 1e-6) -> List[float]:
    x_list = list(xs)
    y_list = list(ys)
    if not x_list:
        raise ValueError("no_training_rows")
    m = len(x_list[0])
    xtx = [[0.0 for _ in range(m)] for _ in range(m)]
    xty = [0.0 for _ in range(m)]

    for x, y in zip(x_list, y_list):
        for i in range(m):
            xty[i] += x[i] * y
            for j in range(m):
                xtx[i][j] += x[i] * x[j]

    for i in range(m):
        xtx[i][i] += l2

    return _solve_linear(xtx, xty)


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _overshoot(samples: Sequence[Dict[str, float]], setpoint: float) -> float:
    return max((abs(s["ang"] - setpoint) for s in samples), default=0.0)


def _rmse(samples: Sequence[Dict[str, float]], setpoint: float) -> float:
    if not samples:
        return 0.0
    errs = [(s["ang"] - setpoint) for s in samples]
    return math.sqrt(sum(e * e for e in errs) / len(errs))


def _settle_s(samples: Sequence[Dict[str, float]], setpoint: float, band: float = 1.1) -> Optional[float]:
    for i, s in enumerate(samples):
        if all(abs(n["ang"] - setpoint) <= band for n in samples[i:]):
            return s["t_s"]
    return None


def _distance_from_range(v: float, lo: float, hi: float) -> float:
    span = max(1e-6, hi - lo)
    if lo <= v <= hi:
        return 0.0
    if v < lo:
        return (lo - v) / span
    return (v - hi) / span


def simulate_from_logs(
    trace_paths: Sequence[Path],
    *,
    kp: float,
    ki: float,
    kd: float,
    setpoint: float,
    duration_s: float = 3.0,
    i_limit: float = 70.0,
    out_limit: float = 180.0,
) -> Dict[str, Any]:
    rows_by_log: List[List[Row]] = [load_rows(p) for p in trace_paths]
    rows_by_log = [rows for rows in rows_by_log if len(rows) >= 5]
    if not rows_by_log:
        return {"ok": False, "error": "insufficient_log_rows"}

    xs: List[List[float]] = []
    y_ang: List[float] = []
    y_gyro: List[float] = []
    dts: List[float] = []

    kp_vals: List[float] = []
    ki_vals: List[float] = []
    kd_vals: List[float] = []
    init_angs: List[float] = []
    init_gyros: List[float] = []

    for rows in rows_by_log:
        init_angs.append(rows[0].ang)
        init_gyros.append(rows[0].gyro)
        for i in range(1, len(rows)):
            a = rows[i - 1]
            b = rows[i]
            dt = b.t_s - a.t_s
            if dt <= 0 or dt > 0.5:
                continue
            dts.append(dt)
            xs.append([1.0, a.ang, a.gyro, a.out, a.setpoint])
            y_ang.append((b.ang - a.ang) / dt)
            y_gyro.append((b.gyro - a.gyro) / dt)
            kp_vals.append(a.kp)
            ki_vals.append(a.ki)
            kd_vals.append(a.kd)

    if len(xs) < 8:
        return {"ok": False, "error": "insufficient_training_pairs", "sample_count": len(xs)}

    beta_ang = _fit_linear(xs, y_ang)
    beta_gyro = _fit_linear(xs, y_gyro)

    dt = statistics.median(dts) if dts else 0.05
    dt = clamp(dt, 0.01, 0.12)

    ang = statistics.median(init_angs) if init_angs else 0.0
    gyro = statistics.median(init_gyros) if init_gyros else 0.0
    integ = 0.0
    prev_err = setpoint - ang

    steps = max(20, int(duration_s / dt))
    samples: List[Dict[str, float]] = []

    for step in range(steps):
        t_s = step * dt
        err = setpoint - ang
        integ = clamp(integ + err * dt, -i_limit, i_limit)
        deriv = (err - prev_err) / max(1e-6, dt)
        prev_err = err

        out = (kp * err) + (ki * integ) + (kd * deriv)
        if abs(out) < 3.0:
            out = 0.0
        out = clamp(out, -out_limit, out_limit)

        f = [1.0, ang, gyro, out, setpoint]
        d_ang = sum(c * x for c, x in zip(beta_ang, f))
        d_gyro = sum(c * x for c, x in zip(beta_gyro, f))

        ang = clamp(ang + (d_ang * dt), -90.0, 90.0)
        gyro = clamp(gyro + (d_gyro * dt), -1200.0, 1200.0)

        samples.append({"t_s": t_s, "ang": ang, "gyro": gyro, "out": out, "set": setpoint})
        if abs(ang) >= 75.0:
            break

    gain_ranges = {
        "kp": {"min": min(kp_vals), "max": max(kp_vals)} if kp_vals else {"min": 0.0, "max": 0.0},
        "ki": {"min": min(ki_vals), "max": max(ki_vals)} if ki_vals else {"min": 0.0, "max": 0.0},
        "kd": {"min": min(kd_vals), "max": max(kd_vals)} if kd_vals else {"min": 0.0, "max": 0.0},
    }

    dist = max(
        _distance_from_range(kp, gain_ranges["kp"]["min"], gain_ranges["kp"]["max"]),
        _distance_from_range(ki, gain_ranges["ki"]["min"], gain_ranges["ki"]["max"]),
        _distance_from_range(kd, gain_ranges["kd"]["min"], gain_ranges["kd"]["max"]),
    )

    log_count = len(rows_by_log)
    sample_count = len(xs)
    confidence = clamp(0.2 + (0.1 * min(6, log_count)) + min(0.45, sample_count / 4000.0) - (0.35 * dist), 0.05, 0.98)

    max_out_pct = max((abs(s["out"]) / max(1e-6, out_limit) for s in samples), default=0.0) * 100.0
    metrics = {
        "rmse": _rmse(samples, setpoint),
        "overshoot": _overshoot(samples, setpoint),
        "settle_s": _settle_s(samples, setpoint),
        "max_out_pct": max_out_pct,
        "faceplant": any(abs(s["ang"]) >= 70.0 for s in samples),
    }

    warning: Optional[str] = None
    if log_count < 2:
        warning = "low_log_count"
    elif dist > 0.35:
        warning = "gain_outside_training_distribution"

    return {
        "ok": True,
        "model": {
            "log_count": log_count,
            "sample_count": sample_count,
            "dt_s": dt,
            "gain_ranges": gain_ranges,
            "distance_from_known": dist,
            "confidence": confidence,
            "warning": warning,
        },
        "simulation": {
            "params": {
                "kp": kp,
                "ki": ki,
                "kd": kd,
                "setpoint": setpoint,
                "duration_s": duration_s,
            },
            "metrics": metrics,
            "sample_count": len(samples),
            "samples": samples[:400],
        },
    }

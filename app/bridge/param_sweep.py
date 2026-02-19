"""
Automated parameter sweep for hardware-in-the-loop tuning.
"""

from __future__ import annotations

import itertools
import statistics
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class PidCandidate:
    kp: float
    ki: float
    kd: float


@dataclass
class SweepConfig:
    kp_values: Sequence[float]
    ki_values: Sequence[float]
    kd_values: Sequence[float]
    settle_s: float = 1.0
    observe_s: float = 3.0
    sample_rate_hz: float = 8.0
    max_angle_variance: float = 8.0
    max_output_saturation_pct: float = 85.0
    require_no_oscillation: bool = False
    max_candidates: int = 200
    rollback_on_fail: bool = True
    restore_baseline_at_end: bool = True
    dry_run: bool = False


def parse_range_spec(spec: str) -> List[float]:
    """
    Parse either:
    - comma list: "30,31,32"
    - range triplet: "30:34:0.5" (inclusive upper if step lands exactly)
    """
    s = spec.strip()
    if not s:
        raise ValueError("empty range spec")
    if ":" in s:
        parts = s.split(":")
        if len(parts) != 3:
            raise ValueError(f"invalid range spec: {spec}")
        start, stop, step = (float(p) for p in parts)
        if step <= 0:
            raise ValueError("step must be > 0")
        out: List[float] = []
        x = start
        eps = step / 1_000_000
        while x <= stop + eps:
            out.append(round(x, 6))
            x += step
        return out
    return [float(p.strip()) for p in s.split(",") if p.strip()]


def build_candidates(config: SweepConfig) -> List[PidCandidate]:
    out = [
        PidCandidate(kp=float(kp), ki=float(ki), kd=float(kd))
        for kp, ki, kd in itertools.product(config.kp_values, config.ki_values, config.kd_values)
    ]
    if len(out) > config.max_candidates:
        raise ValueError(f"candidate_count {len(out)} exceeds max_candidates {config.max_candidates}")
    return out


def _detect_oscillation(angles: List[float]) -> bool:
    if len(angles) < 10:
        return False
    mean_ang = statistics.mean(angles)
    deviations = [a - mean_ang for a in angles]
    sign_changes = 0
    for i in range(1, len(deviations)):
        if deviations[i] * deviations[i - 1] < 0:
            sign_changes += 1
    return sign_changes > len(angles) * 0.2


def compute_metrics(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not samples:
        return {
            "sample_count": 0,
            "angle_variance": 0.0,
            "angle_peak": 0.0,
            "output_saturation_pct": 0.0,
            "oscillation_detected": False,
        }
    angles = [float(s.get("ang", 0.0)) for s in samples]
    outputs = [float(s.get("out", 0.0)) for s in samples]
    sat = sum(1 for o in outputs if abs(o) > 242.0)
    return {
        "sample_count": len(samples),
        "angle_variance": statistics.variance(angles) if len(angles) > 1 else 0.0,
        "angle_peak": max(abs(a) for a in angles),
        "output_saturation_pct": (100.0 * sat / len(outputs)) if outputs else 0.0,
        "oscillation_detected": _detect_oscillation(angles),
    }


def score_metrics(metrics: Dict[str, Any]) -> float:
    # Higher is better.
    variance = float(metrics.get("angle_variance", 0.0))
    peak = float(metrics.get("angle_peak", 0.0))
    sat = float(metrics.get("output_saturation_pct", 0.0))
    osc = bool(metrics.get("oscillation_detected", False))
    score = 100.0
    score -= min(60.0, variance * 6.0)
    score -= min(25.0, peak * 4.0)
    score -= min(25.0, sat * 0.3)
    if osc:
        score -= 20.0
    return max(0.0, round(score, 3))


def evaluate_candidate(metrics: Dict[str, Any], config: SweepConfig) -> Tuple[bool, List[str]]:
    failures: List[str] = []
    if float(metrics.get("angle_variance", 0.0)) > config.max_angle_variance:
        failures.append("angle_variance")
    if float(metrics.get("output_saturation_pct", 0.0)) > config.max_output_saturation_pct:
        failures.append("output_saturation_pct")
    if config.require_no_oscillation and bool(metrics.get("oscillation_detected", False)):
        failures.append("oscillation_detected")
    return len(failures) == 0, failures


class ParameterSweepRunner:
    """
    Gateway contract:
    - health() -> {"connected": bool}
    - is_busy() -> bool
    - get_status() -> dict with kp/ki/kd and telemetry fields
    - command(str) -> {"ok": bool}
    """

    def __init__(
        self,
        gateway: Any,
        *,
        observe_fn: Optional[Callable[[PidCandidate, SweepConfig], Dict[str, Any]]] = None,
    ) -> None:
        self.gateway = gateway
        self.observe_fn = observe_fn

    def _check_ready(self) -> None:
        if self.gateway is None:
            raise RuntimeError("gateway_not_configured")
        health = self.gateway.health()
        if not health.get("connected"):
            raise RuntimeError("serial_not_connected")
        if hasattr(self.gateway, "is_busy") and self.gateway.is_busy():
            raise RuntimeError("serial_busy")

    def _read_pid(self) -> PidCandidate:
        status = self.gateway.get_status()
        return PidCandidate(
            kp=float(status.get("kp", 0.0)),
            ki=float(status.get("ki", 0.0)),
            kd=float(status.get("kd", 0.0)),
        )

    def _apply_pid(self, c: PidCandidate) -> None:
        result = self.gateway.command(f"PID {c.kp} {c.ki} {c.kd}")
        if isinstance(result, dict) and not result.get("ok", True):
            raise RuntimeError(f"pid_apply_failed:{result}")

    def _observe_live(self, config: SweepConfig) -> Dict[str, Any]:
        sample_interval = 1.0 / max(1e-6, config.sample_rate_hz)
        end_t = time.time() + max(0.1, config.observe_s)
        samples: List[Dict[str, Any]] = []
        last_t = 0.0
        while time.time() < end_t:
            now = time.time()
            if now - last_t >= sample_interval:
                try:
                    s = self.gateway.get_status()
                    samples.append(
                        {
                            "ang": float(s.get("ang", 0.0)),
                            "out": float(s.get("out", 0.0)),
                        }
                    )
                except Exception:
                    pass
                last_t = now
            time.sleep(0.01)
        return compute_metrics(samples)

    def run(self, config: SweepConfig) -> Dict[str, Any]:
        self._check_ready()
        candidates = build_candidates(config)
        baseline = self._read_pid()

        rows: List[Dict[str, Any]] = []
        for idx, candidate in enumerate(candidates, start=1):
            row: Dict[str, Any] = {
                "index": idx,
                "kp": candidate.kp,
                "ki": candidate.ki,
                "kd": candidate.kd,
                "applied": False,
                "ok": False,
            }
            try:
                if not config.dry_run:
                    self._apply_pid(candidate)
                    row["applied"] = True
                    time.sleep(max(0.0, config.settle_s))

                if self.observe_fn is not None:
                    metrics = self.observe_fn(candidate, config)
                else:
                    metrics = self._observe_live(config)

                passed, failures = evaluate_candidate(metrics, config)
                row["metrics"] = metrics
                row["score"] = score_metrics(metrics)
                row["ok"] = passed
                row["failures"] = failures

                if not passed and config.rollback_on_fail and not config.dry_run:
                    self._apply_pid(baseline)
                    row["rolled_back"] = True
                else:
                    row["rolled_back"] = False
            except Exception as exc:
                row["error"] = str(exc)
                row["metrics"] = {}
                row["score"] = 0.0
                row["failures"] = ["exception"]
                if config.rollback_on_fail and not config.dry_run:
                    try:
                        self._apply_pid(baseline)
                        row["rolled_back"] = True
                    except Exception:
                        row["rolled_back"] = False
            rows.append(row)

        if config.restore_baseline_at_end and not config.dry_run:
            self._apply_pid(baseline)

        ranked = sorted(rows, key=lambda r: (float(r.get("score", 0.0)), bool(r.get("ok"))), reverse=True)
        top = ranked[: min(10, len(ranked))]
        return {
            "ok": True,
            "baseline": {"kp": baseline.kp, "ki": baseline.ki, "kd": baseline.kd},
            "candidate_count": len(candidates),
            "rows": rows,
            "ranked_top": top,
            "pass_count": sum(1 for r in rows if r.get("ok")),
        }

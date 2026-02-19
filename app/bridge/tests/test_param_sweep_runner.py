"""
Phase 3 parameter sweep tests.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from param_sweep import (  # noqa: E402
    ParameterSweepRunner,
    SweepConfig,
    best_candidate_summary,
    build_candidates,
    parse_range_spec,
    write_sweep_csv,
)


class FakeGateway:
    def __init__(self) -> None:
        self.current = {"kp": 31.0, "ki": 0.05, "kd": 1.05}
        self.commands = []

    def health(self) -> Dict[str, Any]:
        return {"connected": True}

    def is_busy(self) -> bool:
        return False

    def get_status(self) -> Dict[str, Any]:
        return dict(self.current)

    def command(self, cmd: str) -> Dict[str, Any]:
        self.commands.append(cmd)
        if cmd.startswith("PID "):
            _, kp, ki, kd = cmd.split()
            self.current = {"kp": float(kp), "ki": float(ki), "kd": float(kd)}
        return {"ok": True}


def _observe_fn(candidate, _config):
    # Best point near kp=32, ki=0.06, kd=1.2
    err = abs(candidate.kp - 32.0) + 80.0 * abs(candidate.ki - 0.06) + 8.0 * abs(candidate.kd - 1.2)
    variance = 0.3 + err * 0.5
    sat = min(100.0, err * 5.0)
    return {
        "sample_count": 20,
        "angle_variance": variance,
        "angle_peak": 0.5 + err * 0.1,
        "output_saturation_pct": sat,
        "oscillation_detected": err > 3.0,
    }


def test_parse_range_spec_triplet_and_list() -> None:
    assert parse_range_spec("1:2:0.5") == [1.0, 1.5, 2.0]
    assert parse_range_spec("30,31,32") == [30.0, 31.0, 32.0]


def test_build_candidates_respects_max() -> None:
    cfg = SweepConfig(kp_values=[1, 2, 3], ki_values=[0.1, 0.2], kd_values=[0.3], max_candidates=5)
    with pytest.raises(ValueError, match="candidate_count"):
        build_candidates(cfg)


def test_parameter_sweep_ranks_and_restores_baseline() -> None:
    gateway = FakeGateway()
    cfg = SweepConfig(
        kp_values=[31.0, 32.0],
        ki_values=[0.05, 0.06],
        kd_values=[1.0, 1.2],
        settle_s=0.0,
        observe_s=0.1,
        max_candidates=20,
        rollback_on_fail=True,
        restore_baseline_at_end=True,
    )
    runner = ParameterSweepRunner(gateway, observe_fn=_observe_fn)
    report = runner.run(cfg)

    assert report["ok"] is True
    assert report["candidate_count"] == 8
    assert len(report["rows"]) == 8
    assert len(report["ranked_top"]) >= 1

    top = report["ranked_top"][0]
    assert top["kp"] == 32.0
    assert top["ki"] == 0.06
    assert top["kd"] == 1.2
    assert top["ok"] is True

    # Baseline restored at end.
    assert gateway.current == {"kp": 31.0, "ki": 0.05, "kd": 1.05}


def test_parameter_sweep_rolls_back_on_failure() -> None:
    gateway = FakeGateway()

    def failing_observe(candidate, _config):
        if candidate.kp == 40.0:
            return {
                "sample_count": 20,
                "angle_variance": 50.0,
                "angle_peak": 8.0,
                "output_saturation_pct": 95.0,
                "oscillation_detected": True,
            }
        return {
            "sample_count": 20,
            "angle_variance": 1.0,
            "angle_peak": 1.0,
            "output_saturation_pct": 10.0,
            "oscillation_detected": False,
        }

    cfg = SweepConfig(
        kp_values=[31.0, 40.0],
        ki_values=[0.05],
        kd_values=[1.05],
        settle_s=0.0,
        observe_s=0.1,
        max_candidates=10,
        rollback_on_fail=True,
        restore_baseline_at_end=False,
    )
    runner = ParameterSweepRunner(gateway, observe_fn=failing_observe)
    report = runner.run(cfg)
    bad = next(r for r in report["rows"] if r["kp"] == 40.0)

    assert bad["ok"] is False
    assert bad["rolled_back"] is True
    assert "angle_variance" in bad["failures"]
    assert "output_saturation_pct" in bad["failures"]


def test_write_sweep_csv_exports_expected_columns(tmp_path) -> None:
    rows = [
        {
            "index": 1,
            "kp": 32.0,
            "ki": 0.06,
            "kd": 1.2,
            "ok": True,
            "score": 97.1,
            "applied": True,
            "rolled_back": False,
            "failures": [],
            "metrics": {
                "sample_count": 20,
                "angle_variance": 0.5,
                "angle_peak": 0.8,
                "output_saturation_pct": 10.0,
                "oscillation_detected": False,
            },
        }
    ]
    out = tmp_path / "sweep.csv"
    write_sweep_csv(out, rows)
    text = out.read_text(encoding="utf-8")
    assert "kp,ki,kd" in text
    assert "32.0,0.06,1.2" in text
    assert "angle_variance" in text


def test_best_candidate_summary_includes_core_fields() -> None:
    report = {
        "ranked_top": [
            {
                "kp": 32.0,
                "ki": 0.06,
                "kd": 1.2,
                "score": 98.5,
                "ok": True,
                "metrics": {
                    "angle_variance": 0.4,
                    "output_saturation_pct": 5.0,
                    "oscillation_detected": False,
                },
            }
        ]
    }
    s = best_candidate_summary(report)
    assert "BEST" in s
    assert "kp=32.0" in s
    assert "ki=0.06" in s
    assert "kd=1.2" in s
    assert "score=98.5" in s

"""
Phase 2 trace replay regression tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from trace_replay import evaluate_replay, load_trace_csv, replay_trace  # noqa: E402


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_nominal_trace_replay_passes_thresholds() -> None:
    samples = load_trace_csv(FIXTURES_DIR / "trace_replay_nominal.csv")
    report = replay_trace(samples, i_limit=70.0, out_limit=180.0, cmd_vel=0.0)
    verdict = evaluate_replay(report, cmd_rmse_max=1.0, cmd_abs_max=3.0)

    assert report["ok"] is True
    assert report["summary"]["sample_count"] >= 8
    assert verdict["ok"] is True
    assert verdict["pass"] is True


def test_regressed_trace_replay_fails_thresholds() -> None:
    samples = load_trace_csv(FIXTURES_DIR / "trace_replay_regressed.csv")
    report = replay_trace(samples, i_limit=70.0, out_limit=180.0, cmd_vel=0.0)
    verdict = evaluate_replay(report, cmd_rmse_max=5.0, cmd_abs_max=10.0)

    assert report["ok"] is True
    assert report["summary"]["rmse_command"] > 20.0
    assert verdict["ok"] is True
    assert verdict["pass"] is False


def test_replay_requires_enough_samples() -> None:
    samples = load_trace_csv(FIXTURES_DIR / "trace_replay_nominal.csv")[:2]
    report = replay_trace(samples)
    assert report["ok"] is False
    assert report["error"] == "insufficient_samples"

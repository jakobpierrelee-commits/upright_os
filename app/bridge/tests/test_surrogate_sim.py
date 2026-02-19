from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from surrogate_sim import load_rows, simulate_from_logs


def test_load_rows_fixture():
    p = Path('app/bridge/tests/fixtures/trace_replay_nominal.csv')
    rows = load_rows(p)
    assert len(rows) > 8
    assert isinstance(rows[0].ang, float)


def test_simulate_from_logs_basic():
    paths = [
        Path('app/bridge/tests/fixtures/trace_replay_nominal.csv'),
        Path('app/bridge/tests/fixtures/trace_replay_regressed.csv'),
    ]
    out = simulate_from_logs(paths, kp=31.0, ki=0.05, kd=1.05, setpoint=0.0, duration_s=2.0)
    assert out['ok'] is True
    assert out['model']['log_count'] >= 2
    assert out['model']['sample_count'] >= 8
    assert 0.0 <= float(out['model']['confidence']) <= 1.0
    assert out['simulation']['sample_count'] > 5
    assert 'rmse' in out['simulation']['metrics']


def test_simulate_flags_out_of_distribution_gain():
    paths = [
        Path('app/bridge/tests/fixtures/trace_replay_nominal.csv'),
        Path('app/bridge/tests/fixtures/trace_replay_regressed.csv'),
    ]
    out = simulate_from_logs(paths, kp=120.0, ki=1.2, kd=20.0, setpoint=0.0, duration_s=1.5)
    assert out['ok'] is True
    assert float(out['model']['distance_from_known']) > 0.0
    assert out['model']['warning'] in {'gain_outside_training_distribution', 'low_log_count', None}


def test_simulate_requires_enough_rows(tmp_path: Path):
    bad = tmp_path / 'tiny.csv'
    bad.write_text('ms,angle,gyro,out,setpoint,kp,ki,kd\n0,0,0,0,0,1,0,0\n', encoding='utf-8')
    out = simulate_from_logs([bad], kp=1.0, ki=0.0, kd=0.0, setpoint=0.0)
    assert out['ok'] is False

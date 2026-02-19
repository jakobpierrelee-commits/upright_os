"""
Parity-focused tests for firmware control math primitives.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from control_math import (  # noqa: E402
    KalmanState,
    PidState,
    balance_control_step,
    kalman_update,
)


def test_kalman_update_deterministic_snapshot() -> None:
    state = KalmanState(angle=0.0, bias=0.0, p00=1.0, p01=0.0, p10=0.0, p11=1.0)

    out = kalman_update(
        state,
        meas_deg=1.2,
        gyro_dps=0.3,
        dt=0.005,
        q_angle=0.001,
        q_bias=0.003,
        r_measure=0.03,
    )

    assert out == pytest.approx(1.1650932497111735, rel=0, abs=1e-9)
    assert state.bias == pytest.approx(-0.005817791714804422, rel=0, abs=1e-9)
    assert state.p00 == pytest.approx(0.029126239041581292, rel=0, abs=1e-9)
    assert state.p01 == pytest.approx(-0.0001456268264031146, rel=0, abs=1e-9)
    assert state.p10 == pytest.approx(-0.0001456268264031146, rel=0, abs=1e-9)
    assert state.p11 == pytest.approx(0.9999907288622663, rel=0, abs=1e-9)


def test_kalman_update_requires_positive_dt() -> None:
    state = KalmanState()
    with pytest.raises(ValueError, match="dt must be > 0"):
        kalman_update(
            state,
            meas_deg=0.0,
            gyro_dps=0.0,
            dt=0.0,
            q_angle=0.001,
            q_bias=0.003,
            r_measure=0.03,
        )


def test_balance_control_integrator_clamp_upper_and_lower() -> None:
    state = PidState(integrator=0.0, prev_angle=0.0)

    first = balance_control_step(
        state,
        setpoint_deg=10.0,
        angle_deg=0.0,
        wheel_speed=0.0,
        cmd_vel=0.0,
        pos_ref=0.0,
        wheel_pos=0.0,
        kp=0.0,
        ki=10.0,
        kd=0.0,
        kv=0.0,
        kx=0.0,
        i_limit=5.0,
        out_limit=100.0,
        dt=1.0,
    )
    assert first.command == pytest.approx(5.0)
    assert state.integrator == pytest.approx(5.0)

    second = balance_control_step(
        state,
        setpoint_deg=-10.0,
        angle_deg=0.0,
        wheel_speed=0.0,
        cmd_vel=0.0,
        pos_ref=0.0,
        wheel_pos=0.0,
        kp=0.0,
        ki=10.0,
        kd=0.0,
        kv=0.0,
        kx=0.0,
        i_limit=5.0,
        out_limit=100.0,
        dt=2.0,
    )
    assert second.command == pytest.approx(-5.0)
    assert state.integrator == pytest.approx(-5.0)


def test_balance_control_output_saturation_matches_out_limit() -> None:
    state = PidState(integrator=0.0, prev_angle=0.0)
    result = balance_control_step(
        state,
        setpoint_deg=20.0,
        angle_deg=0.0,
        wheel_speed=0.0,
        cmd_vel=0.0,
        pos_ref=0.0,
        wheel_pos=0.0,
        kp=10.0,
        ki=0.0,
        kd=0.0,
        kv=0.0,
        kx=0.0,
        i_limit=70.0,
        out_limit=180.0,
        dt=0.005,
    )
    assert result.angle_out == pytest.approx(200.0)
    assert result.command == pytest.approx(180.0)


def test_balance_control_derivative_uses_negative_angle_rate_and_updates_prev() -> None:
    state = PidState(integrator=0.0, prev_angle=1.0)
    result = balance_control_step(
        state,
        setpoint_deg=0.0,
        angle_deg=2.0,
        wheel_speed=0.0,
        cmd_vel=0.0,
        pos_ref=0.0,
        wheel_pos=0.0,
        kp=0.0,
        ki=0.0,
        kd=1.0,
        kv=0.0,
        kx=0.0,
        i_limit=70.0,
        out_limit=300.0,
        dt=0.01,
    )
    assert result.derivative == pytest.approx(-100.0)
    assert result.command == pytest.approx(-100.0)
    assert state.prev_angle == pytest.approx(2.0)


def test_balance_control_motion_term_matches_firmware_equation() -> None:
    state = PidState(integrator=0.0, prev_angle=0.0)
    result = balance_control_step(
        state,
        setpoint_deg=0.0,
        angle_deg=0.0,
        wheel_speed=5.0,
        cmd_vel=2.0,
        pos_ref=100.0,
        wheel_pos=90.0,
        kp=0.0,
        ki=0.0,
        kd=0.0,
        kv=0.5,
        kx=0.2,
        i_limit=70.0,
        out_limit=300.0,
        dt=0.02,
    )
    # (-kv*(wheelSpeed-cmdVel)) + (kx*(posRef-wheelPos))
    assert result.motion_out == pytest.approx(0.5)
    assert result.command == pytest.approx(0.5)


def test_balance_control_requires_positive_dt() -> None:
    state = PidState()
    with pytest.raises(ValueError, match="dt must be > 0"):
        balance_control_step(
            state,
            setpoint_deg=0.0,
            angle_deg=0.0,
            wheel_speed=0.0,
            cmd_vel=0.0,
            pos_ref=0.0,
            wheel_pos=0.0,
            kp=1.0,
            ki=0.0,
            kd=0.0,
            kv=0.0,
            kx=0.0,
            i_limit=70.0,
            out_limit=180.0,
            dt=0.0,
        )


def test_balance_control_tiny_dt_is_finite() -> None:
    state = PidState(integrator=0.0, prev_angle=0.0)
    result = balance_control_step(
        state,
        setpoint_deg=0.0,
        angle_deg=0.000001,
        wheel_speed=0.0,
        cmd_vel=0.0,
        pos_ref=0.0,
        wheel_pos=0.0,
        kp=0.0,
        ki=0.0,
        kd=0.1,
        kv=0.0,
        kx=0.0,
        i_limit=70.0,
        out_limit=180.0,
        dt=1e-6,
    )
    assert math.isfinite(result.derivative)
    assert math.isfinite(result.command)

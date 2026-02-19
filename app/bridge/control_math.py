"""
Firmware-parity control math helpers for Nano balance firmware.

These helpers mirror the core equations in:
`tumbller_v06_nano_balance_v2/tumbller_v06_nano_balance_v2.ino`
"""

from __future__ import annotations

from dataclasses import dataclass


def _clamp(value: float, lo: float, hi: float) -> float:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


@dataclass
class KalmanState:
    angle: float = 0.0
    bias: float = 0.0
    p00: float = 1.0
    p01: float = 0.0
    p10: float = 0.0
    p11: float = 1.0


def kalman_update(
    state: KalmanState,
    *,
    meas_deg: float,
    gyro_dps: float,
    dt: float,
    q_angle: float,
    q_bias: float,
    r_measure: float,
) -> float:
    """
    Mirror of firmware `kalmanUpdate(...)`.
    Returns updated estimated angle.
    """
    if dt <= 0.0:
        raise ValueError("dt must be > 0")
    if r_measure <= 0.0:
        raise ValueError("r_measure must be > 0")

    rate = gyro_dps - state.bias
    state.angle += dt * rate

    state.p00 += dt * (dt * state.p11 - state.p01 - state.p10 + q_angle)
    state.p01 -= dt * state.p11
    state.p10 -= dt * state.p11
    state.p11 += q_bias * dt

    innovation = meas_deg - state.angle
    s = state.p00 + r_measure
    k0 = state.p00 / s
    k1 = state.p10 / s

    state.angle += k0 * innovation
    state.bias += k1 * innovation

    p00 = state.p00
    p01 = state.p01
    state.p00 -= k0 * p00
    state.p01 -= k0 * p01
    state.p10 -= k1 * p00
    state.p11 -= k1 * p01

    return state.angle


@dataclass
class PidState:
    integrator: float = 0.0
    prev_angle: float = 0.0


@dataclass
class ControlStepResult:
    error: float
    derivative: float
    angle_out: float
    motion_out: float
    command: float


def balance_control_step(
    state: PidState,
    *,
    setpoint_deg: float,
    angle_deg: float,
    wheel_speed: float,
    cmd_vel: float,
    pos_ref: float,
    wheel_pos: float,
    kp: float,
    ki: float,
    kd: float,
    kv: float,
    kx: float,
    i_limit: float,
    out_limit: float,
    dt: float,
) -> ControlStepResult:
    """
    Mirror of firmware BALANCING branch:
      err = setpoint - angle
      integrator += ki * err * dt; clamp to [-iLimit, iLimit]
      deriv = -(angle - prevAngle) / dt
      angleOut = kp*err + integrator + kd*deriv
      motionOut = (-kv*(wheelSpeed-cmdVel)) + (kx*(posRef-wheelPos))
      u = clamp(angleOut+motionOut, -outLimit, outLimit)
    """
    if dt <= 0.0:
        raise ValueError("dt must be > 0")
    if i_limit < 0.0:
        raise ValueError("i_limit must be >= 0")
    if out_limit < 0.0:
        raise ValueError("out_limit must be >= 0")

    err = setpoint_deg - angle_deg
    state.integrator += ki * err * dt
    state.integrator = _clamp(state.integrator, -i_limit, i_limit)

    deriv = -(angle_deg - state.prev_angle) / dt
    state.prev_angle = angle_deg

    angle_out = kp * err + state.integrator + kd * deriv
    pos_err = pos_ref - wheel_pos
    motion_out = (-kv * (wheel_speed - cmd_vel)) + (kx * pos_err)
    cmd = _clamp(angle_out + motion_out, -out_limit, out_limit)

    return ControlStepResult(
        error=err,
        derivative=deriv,
        angle_out=angle_out,
        motion_out=motion_out,
        command=cmd,
    )

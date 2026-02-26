# PID + Estimation Reference v1.1 (Trusted Sources)

## Source basis
- UMich CTMS inverted pendulum control/modeling:
  - https://ctms.engin.umich.edu/CTMS/index.php?example=InvertedPendulum&section=SystemModeling
  - https://ctms.engin.umich.edu/CTMS/index.php?example=InvertedPendulum&section=ControlPID
- MIT Underactuated Robotics feedback/stability framing:
  - https://underactuated.mit.edu/
- Kalman filter intro (state, covariance, innovation):
  - https://www.cs.unc.edu/~welch/media/pdf/kalman_intro.pdf

## PID form
u(t) = Kp * e(t) + Ki * integral(e dt) + Kd * de/dt

Discrete tuning intuition:
- `Kp`: faster error correction, but can increase oscillation.
- `Ki`: removes bias, but risks windup if overused.
- `Kd`: adds damping, but can amplify measurement noise.

## Inverted pendulum implications
- The balancing plant is unstable in open loop; closed-loop feedback must add damping and sufficient corrective authority.
- Derivative action is useful for damping near upright, but should be noise-aware.
- Integral action is secondary and should be introduced carefully after `Kp/Kd` are close.

## 1D angle + gyro-bias estimator (common Kalman structure)
State:
- angle
- gyro bias

Predict:
- rate = gyro - bias
- angle = angle + dt * rate

Correct:
- innovation = accel_angle - angle
- update angle and bias with Kalman gains

Tuning implications:
- Higher process noise -> faster adaptation, noisier estimate.
- Higher measurement noise -> smoother output, slower accel correction.
- Large persistent `raw` vs `ang` mismatch suggests calibration/alignment issue before PID changes.

## Discrete Kalman equations (2-state, angle+bias)
State vector:
- `x = [angle, bias]^T`

System:
- `angle_k = angle_{k-1} + dt * (gyro_k - bias_{k-1})`
- `bias_k = bias_{k-1}`

Innovation (measurement residual):
- `innovation = accel_angle - angle_pred`

Covariance + gain:
- `P_pred = A * P_prev * A^T + Q`
- `K = P_pred * H^T * (H * P_pred * H^T + R)^-1`

Correction:
- `x = x_pred + K * innovation`
- `P = (I - K * H) * P_pred`

Operator meaning:
- Innovation is the confidence gap between accelerometer and predicted angle.
- Small steady innovation indicates estimator alignment.
- Large persistent innovation indicates calibration/noise/model mismatch.

## Signal -> Error -> Output control chain
Canonical upright control path:
- Signal estimate: `ang` (filtered), with `raw` and `gyro|gyr|gx` as sensor inputs.
- Error: `e = set - ang`
- Controller output (pre-clamp): `u = Kp*e + Ki*int(e) + Kd*d(e)/dt`
- Actuator output (post-clamp): `out = clamp(u, -out_max, out_max)`

Recommended diagnostics:
- `innovation = raw - ang` (or `kal_innov` if emitted explicitly)
- `pid_err = set - ang`
- `pid_u_unsat`, `pid_u_sat`, and saturation flag for anti-windup behavior

## Practical estimator-controller coupling
- Cleaner angle estimate supports higher `kp/kd` safely.
- Noisy estimate requires conservative `kd`.
- Always diagnose sensor quality before large controller changes.

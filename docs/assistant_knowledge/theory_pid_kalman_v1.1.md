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

## Practical estimator-controller coupling
- Cleaner angle estimate supports higher `kp/kd` safely.
- Noisy estimate requires conservative `kd`.
- Always diagnose sensor quality before large controller changes.

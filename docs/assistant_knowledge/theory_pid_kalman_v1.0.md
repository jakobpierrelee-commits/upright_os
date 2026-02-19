# PID + Kalman Reference v1.0

## PID (continuous form)
u(t) = Kp * e(t) + Ki * integral(e(t) dt) + Kd * d/dt(e(t))

Discrete intuition:
- `Kp`: immediate correction proportional to tilt error.
- `Ki`: removes persistent bias over time.
- `Kd`: damping using rate-like behavior, reducing overshoot.

For self-balancing robots:
- `Kp` too high -> aggressive oscillation.
- `Ki` too high -> windup / slow large rebounds.
- `Kd` too high -> noisy/twitchy actuation.

## Kalman angle estimator (common 1D form)
State:
- angle, gyro bias

Predict:
- rate = gyro - bias
- angle = angle + dt * rate
- update covariance terms

Correct:
- innovation = accel_angle - angle
- compute Kalman gains
- angle = angle + K0 * innovation
- bias  = bias  + K1 * innovation

Practical notes:
- Increase process noise (`qAngle/qBias`) for faster adaptation, but noisier estimate.
- Increase measurement noise (`rMeasure`) to trust gyro integration more than accel.
- If `raw` diverges from `ang` persistently, check calibration and axis polarity first.

## Controller-estimator interaction
- Cleaner `ang` lets higher `kp`/`kd` without instability.
- Noisy `ang` demands lower `kd`.
- Tuning should consider estimator quality, not PID alone.


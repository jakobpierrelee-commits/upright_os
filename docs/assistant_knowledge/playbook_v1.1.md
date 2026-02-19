# UpRight Balancer Tuning Playbook v1.1 (Trusted Sources)

## Goal
Minimize tilt error and recovery oscillation while preserving actuator smoothness and avoiding fail-safe events.

## Source basis
- MIT Underactuated Robotics (feedback, stability intuition): https://underactuated.mit.edu/
- UMich CTMS Inverted Pendulum modeling + PID design: 
  - https://ctms.engin.umich.edu/CTMS/index.php?example=InvertedPendulum&section=SystemModeling
  - https://ctms.engin.umich.edu/CTMS/index.php?example=InvertedPendulum&section=ControlPID
- MathWorks anti-windup practice for saturated actuators:
  - https://www.mathworks.com/help/simulink/slref/anti-windup-control-using-a-pid-controller.html

## Required telemetry
- `ang` (filtered angle, deg)
- `raw` (accelerometer angle, deg)
- `gyro|gyr|gx` (rate, dps)
- `out` (controller output)
- `kp,ki,kd,kv,kx,set`
- `mode,estop`

## Fast tuning loop
1. Safety gate: only tune in safe controlled conditions.
2. Run a short test window (15-30 s).
3. Classify behavior: overshoot, jitter, drift, sluggishness.
4. Apply one bounded parameter change.
5. Re-test and compare metrics.

## Source-backed symptom -> action
- Overshoot / underdamped:
  - Increase `kd` first for damping.
  - Then increase `kp` slightly only if rise is too slow.
- High-frequency jitter / noisy output:
  - Decrease `kd` first (derivative amplifies noise).
  - Then reduce `kp` if chatter remains.
- Slow correction:
  - Increase `kp` slightly.
  - Add small `ki` only if persistent bias remains.
- Persistent lean bias / steady-state error:
  - Increase `ki` in small steps.
  - Verify zero/calibration before further integral increase.
- Windup-like long recovery after disturbance:
  - Reduce `ki` and favor anti-windup behavior.

## Motion term ordering
- Tune base stabilization (`kp,ki,kd`) before motion terms (`kv,kx`).
- Excessive `kv/kx` can inject unnecessary acceleration and noise.

## Apply discipline
- One family per step (`pid` OR `motion` OR `setpoint`).
- Save snapshot before apply.
- Revert immediately if key metrics regress.

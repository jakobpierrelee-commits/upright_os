# Controls Tuning Procedure v1.0

## Scope
Use this procedure for upright self-balancing bots when tuning from live telemetry, replay logs, and surrogate simulation.

## Core Concepts (Operator + Assistant)
- Integral windup: integrator keeps accumulating while output is saturated; causes delayed recovery and hunting.
- Conditional integration: integrate only when actuator is unsaturated, or when error drives output back from saturation.
- Clamping: bound integrator (`i_max`) and command (`out_max`) to deterministic safety limits.
- Low-pass cutoff frequency: sensor smoothing boundary (`fc` in Hz). Lower `fc` reduces noise, increases lag.
- Filter coefficient (discrete): `alpha = dt / (tau + dt)`, `tau = 1/(2*pi*fc)`.
- Integral feedback path: `Ki/s` branch; improves steady-state error but must be anti-windup protected.
- Laplace transfer functions: use for stability intuition (poles/zeros, damping, bandwidth), then verify against time-domain telemetry.
- Cohen-Coon method: acceptable coarse seed only when telemetry is sparse; do not treat as final tuning on balancing robots.

## Runtime Knobs
- Runtime-applicable now: `PID (kp, ki, kd)`, `MOTION (kv, kx)`, `SETPOINT`, `LIMITS (out_max, tip_deg, i_max)`.
- Recommendation/simulation knobs (firmware support required for runtime apply):
  - `lowpass_cutoff_hz`
  - `conditional_integration`

## Rugged Procedure
1. Capture baseline:
   - 10-20s stable window.
   - Save current PID/MOTION/SETPOINT/LIMITS snapshot.
2. Score baseline:
   - angle variance
   - output saturation %
   - overshoot
   - settle time
   - replay parity (when logs available)
3. Change one family only:
   - PID or LIMITS or filter behavior.
   - Use bounded step sizes.
4. Re-run same observation window.
5. Promote only if score improves and safety remains green.
6. If uncertain:
   - rollback
   - reduce step size
   - collect additional logs

## Safety Heuristics
- High saturation:
  - reduce `kp` and/or increase `out_max` only after confirming motor/driver thermal headroom.
- Low-frequency oscillation:
  - reduce `ki`, reduce `i_max`, enable conditional integration.
- High-frequency oscillation/noise:
  - increase `kd` cautiously and lower `lowpass_cutoff_hz`.
- Good stability:
  - checkpoint and freeze as rollback-safe profile.

## Acceptance Criteria for Recommendations
- Every recommendation includes:
  - action
  - rationale
  - confidence
  - whether runtime apply is supported
- No recommendation may require unsafe multi-parameter jumps.
- If confidence is low or gain distance from known logs is high, assistant must explicitly warn.

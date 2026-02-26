# PID + Estimation Reference v1.2 (Applied to UpRight Event Validity)

## Control truths for this platform
- A self-balancer is unstable open-loop; closed-loop damping + authority are both required.
- PID tuning without event-valid capture can look stable while still failing physically.
- Estimator quality and control quality must be diagnosed together.

## Practical signal chain
- Estimate signal: `ang` (from sensor fusion / filter).
- Error: `set - ang`.
- Controller output: `out`.
- Motion terms modify effective command: `kv`, `kx`.
- Plant response proxies: `wposRaw`, `wdelta`, `wspd`, encoder counts.

## Why operator observations can outrank bad logs
- If the robot physically runs away/falls but logs show low signal:
  - likely wrong capture window/trigger,
  - or telemetry pipeline missing onset dynamics.
- In that case, classify as invalid evidence and fix capture before tuning.

## Saturation and authority
- If catch-up fails, verify whether controller demanded authority:
  - high `|out|` near limit with growing error indicates authority bottleneck,
  - low `|out|` during observed failure indicates capture mismatch or controller not entering high-demand state.
- Interpret `out_max`, slew limits, and motor/driver behavior together.

## Kalman/filter usage guidance
- Large persistent `raw - ang` bias suggests calibration/alignment issue first.
- Increase in derivative sensitivity (`kd`) without estimator quality can amplify noise.
- Avoid attributing all failures to gains when sensor reference is inconsistent.

## Evidence-first tuning doctrine
1. Capture valid event.
2. Classify failure mode.
3. Apply one bounded change.
4. Re-test under matched conditions.
5. Promote only with objective improvement and no safety regression.

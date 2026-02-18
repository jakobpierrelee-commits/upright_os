# Commissioning Standard

## Pipeline (5-Phase)
1. Baseline apply.
2. Encoder integrity check.
3. Motor pulse validation.
4. Burst capture.
5. Metric evaluation.

## Pass Gates (all required)
- `enc_check_ok = 1`
- `motor_pulse_ok = 1`
- `ok = 1` for burst metrics

## KPI Requirements (all required)
1. Disturbance recovery.
2. Long-hold stability.
3. Position return accuracy.

## Latency Targets
- Command-to-actuation max: 100 ms.
- UI telemetry refresh: 20 Hz.

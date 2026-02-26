# balance_mvp_v1_1_gsched

Purpose: Nano-safe balance firmware with gain scheduling (`GSCHED`) for improved large-perturbance authority.

Included:
- Single-loop tilt PID (`PID`, `SETPOINT`, `LIMITS`)
- Runtime gain scheduling (`GSCHED <err_deg> <boost>`)
- IMU workflows (`IMU CAL`, `IMU LOAD`, `IMU SAVE`, `IMU INFO`, `CAL ZERO`)
- Safety path (`ESTOP`, `ARM`, `DISARM`, tip fault, sensor fault, encoder-stale fault)
- Bounded auto-zero trim (`AUTOZERO`, `AUTOZERO STATUS`, `AUTOZERO CLR`, `AUTOZERO SAVE`)
- Essential telemetry + burst csv (`GET`, `LOGT`, `LOGCSV`, `BURSTCSV`, `CSVHDR`, `IDENT`)
- Seed configs: `tuning_seed_profiles.json` (starting points only; bot/surface/calibration specific)

Deliberately excluded for baseline stage:
- Motion/feedforward control loop (`MOTION`)
- Runtime filter retuning command surface (`FILTER`)
- Runtime Kalman retuning command surface (`KAL`)
- Autotune helper command surfaces

Compile:
- `arduino-cli compile --clean --fqbn arduino:avr:nano app/bridge/firmware_templates/balance_mvp_v1_1_gsched`

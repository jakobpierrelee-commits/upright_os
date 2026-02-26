# balance_mvp_v1

Purpose: minimal, balance-first firmware for Arduino Nano bring-up and PID tuning.

Included:
- Single-loop tilt PID (`PID`, `SETPOINT`, `LIMITS`)
- IMU workflows (`IMU CAL`, `IMU LOAD`, `IMU SAVE`, `IMU INFO`, `CAL ZERO`)
- Safety path (`ESTOP`, `ARM`, `DISARM`, tip fault, sensor fault, encoder-stale fault)
- Bounded auto-zero trim (`AUTOZERO`, `AUTOZERO STATUS`, `AUTOZERO CLR`, `AUTOZERO SAVE`)
- Essential telemetry + burst csv (`GET`, `LOGT`, `LOGCSV`, `BURSTCSV`, `CSVHDR`, `IDENT`)

Deliberately excluded for baseline stage:
- Motion/feedforward control loop (`MOTION`)
- Runtime filter retuning command surface (`FILTER`)
- Runtime Kalman retuning command surface (`KAL`)
- Autotune helper command surfaces

Compile:
- `arduino-cli compile --clean --fqbn arduino:avr:nano app/bridge/firmware_templates/balance_mvp_v1`

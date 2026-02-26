# balance_mvp_v2_core_esp32

Purpose: stripped tuning-first ESP32 sketch with deterministic balance loop, gain scheduling, full EEPROM persistence for iterative tuning variables, and current fault latch behavior.

Included:
- Core runtime commands: `GET IDENT ARM DISARM ESTOP PID SETPOINT LIMITS CAL ZERO SAVECFG FAULTCLR`
- Tuning commands (EEPROM-backed): `MOTION SLEW RAMP MOTIONCFG GSCHED DCFG AUTORUN`
- Auto setpoint trim commands (EEPROM-backed): `AUTOTRIM TRIMCFG TRIMLIMS TRIMCLR`
- Boot autorun + runtime autorun delay control
- IMU offset persistence and service commands (`IMU CAL/LOAD/SAVE/INFO`) + `CAL ZERO` setpoint-zero workflow
- Safety path: estop latch, tip fault, sensor fault, encoder-stale fault, loop-overrun tracking

Deliberately excluded:
- Legacy autozero logic
- Verbose telemetry, burst logging, autotune helper commands
- Non-essential command surfaces not needed for iterative balancing on ESP32

Compile:
- `arduino-cli compile --clean --fqbn esp32:esp32:esp32 app/bridge/firmware_templates/balance_mvp_v2_core_esp32`

# UpRight Control Lab V1 Handoff

## Purpose
This handoff describes how to validate and extend the new sketch:
- `/Users/jvke/Documents/UpRight.os/app/bridge/firmware_templates/upright_control_lab_v1/upright_control_lab_v1.ino`

The sketch is a fresh build (not a patch of prior balance sketches) and is aligned to UpRight.os-style serial sync/telemetry/command patterns.

## Term Mapping (Requested Concepts)
1. Integral windup:
- Implemented with two anti-windup mechanisms:
  - conditional integration gate
  - back-calculation integral feedback path (`kaw`)
2. Limit adjustments:
- Runtime via `LIMITS <out_max> <tip_deg> <i_max> [i_term_max]`
3. Conditional integration:
- Runtime via `FILTER <d_cutoff_hz> <conditional_i> [kaw]`
4. Clamping:
- Integrator state clamp (`i_max`)
- Integral term clamp (`i_term_max`)
- Output clamp (`out_max`)
5. Cutoff frequency filter (low-pass):
- Derivative term LPF with cutoff `d_cutoff_hz`
- Filter coefficient `alpha` computed each loop and telemetered as `filter_alpha`
6. Laplace domain transfer functions:
- `TF` command prints controller/plant/closed-loop forms
7. Integral feedback path:
- Back-calculation term: `i_state += kaw * (u_sat - u_unsat) * dt`
8. Filter coefficient:
- `filter_alpha` emitted in `STATUS` and `CSV`
9. Cohen-Coon method:
- `CC <K> <T> <L>` computes suggested PID and prints `kp/ki/kd`

## UpRight.os Sync + Command Contract Notes
Core compatibility intent:
- `GET` emits a single-line `STATUS ...` key/value payload.
- `HELP` returns an `OK HELP ...` command list.
- Common commands acknowledged with `OK ...` lines.
- Unknown commands return `ERR UNKNOWN ...`.

Implemented commands:
1. `GET`
2. `HELP`
3. `IDENT`
4. `ARM`
5. `DISARM`
6. `ESTOP 1|0`
7. `PID <kp> <ki> <kd>`
8. `MOTION <kv> <kx>`
9. `SETPOINT <deg>`
10. `LIMITS <out_max> <tip_deg> <i_max> [i_term_max]`
11. `FILTER <d_cutoff_hz> <conditional_i> [kaw]`
12. `KAL <q_angle> <q_bias> <r_measure>`
13. `CC <K> <T> <L>`
14. `TF`
15. `LOGCSV 1|0`
16. `LOGT 1|0`
17. `BURSTCSV`
18. `CSVHDR`
19. `CAL ZERO`
20. `SAVECFG`

## STATUS Telemetry Keys
Current `STATUS` includes:
- `mode`, `estop`
- `ang`, `raw`, `gyro`
- `set`, `out`
- `kp`, `ki`, `kd`, `kv`, `kx`
- `pid_err`, `pid_p`, `pid_i`, `pid_d`, `pid_u_unsat`, `pid_u_sat`
- `output_saturated`
- `out_max`, `tip_deg`, `i_max`, `i_term_max`, `conditional_i`, `kaw`
- `d_cutoff_hz`, `filter_alpha`
- `wpos`, `wspd`, `encL`, `encR`, `volRaw`

This satisfies expected UpRight HUD keys (`mode`, `ang`, `raw`, `gyro`, `out`, `kp`, `ki`, `kd`, `set`) and adds control diagnostics.

## Encoder Strategy
Board assumption: Arduino Nano classic (ATmega328P).

- Left encoder: `D2` via external interrupt (`attachInterrupt`)
- Right encoder: `D4` via pin change interrupt (`PCINT20`)

Velocity sign is inferred from commanded output direction when only one channel per wheel is available.

## Acceptance Test Checklist
1. Boot banner:
- Expect `UPRIGHT_CONTROL_LAB_BOOT`
2. Command/ack:
- `HELP` returns `OK HELP ...`
- `PID 20 0.2 0.8` returns `OK PID`
- `LIMITS 180 30 70 120` returns `OK LIMITS`
- `FILTER 20 1 0.25` returns `OK FILTER`
- `KAL 0.001 0.003 0.03` returns `OK KAL`
3. STATUS contract:
- `GET` line contains at least: `mode=`, `ang=`, `raw=`, `gyro=`, `out=`, `kp=`, `ki=`, `kd=`, `set=`
4. Cohen-Coon helper:
- `CC 1.2 0.8 0.15` returns `CC PID kp=... ki=... kd=...`
5. Transfer function helper:
- `TF` prints 3 lines (`C(s)`, `G(s)`, `T(s)`)
6. Logging:
- `LOGT 1` produces periodic `STATUS`
- `LOGCSV 1` produces periodic `CSV`
7. Encoder interrupts:
- Toggle D2 and D4 input edges; verify `encL` and `encR` increment

## Known Limits
1. IMU and motor paths are intentionally stubs in this version:
- `readAccelAngleDegStub()`
- `readGyroRateDpsStub()`
- `applyMotorOutput()`
2. Bidirectional wheel motion is inferred from command sign (not true quadrature).
3. `SAVECFG` is ack-only placeholder (no EEPROM persistence yet).

## Next Agent Tasks
1. Wire real IMU reads into `g_raw` and `g_gyro`.
2. Replace `applyMotorOutput()` with TB6612 motor drive writes.
3. Add EEPROM-backed config persistence for PID/filter/limits.
4. Keep all existing command names and `STATUS` keys backward-compatible.

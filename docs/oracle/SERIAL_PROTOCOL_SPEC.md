# Serial Protocol Spec (V1)

## Core Commands
- `GET`
- `ARM`, `DISARM`, `STATE SAFE|ARM|BAL|FAULT`
- `PID <kp> <ki> <kd>`
- `MOTION <kv> <kx>`
- `SETPOINT <deg>`
- `LIMITS <out tip iMax>`
- `CAL ZERO`
- `SAVECFG`, `LOADCFG`, `DEFAULTCFG`
- `LOGCSV 1|0`, `BURSTCSV <delay lines>`
- `MOTOR <l r>`, `MOTOROFF`

## Response Rules
- Every command must return deterministic ack/error.
- `GET` must return a parseable `STATUS ...` line.
- Timeouts and retries must be bounded in host bridge.

## Live-Tuning Policy
- While BALANCING: only bounded incremental changes allowed.
- Large tuning changes require SAFE/ARM modes.

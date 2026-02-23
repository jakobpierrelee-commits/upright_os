# Command/API Map

| Command | Changes | Notes |
| --- | --- | --- |
| `GET` | Reads status snapshot | No state mutation |
| `PID <kp> <ki> <kd>` | PID gains (`kp`,`ki`,`kd`) | Inner loop tuning |
| `MOTION <kv> <kx>` | Motion gains (`kv`,`kx`) | Outer behavior tuning |
| `SETPOINT <deg>` | Balance target angle (`set`) | Degrees |
| `LIMITS <out_max> <tip_deg> <i_max>` | Safety/output constraints | Device-side clamp |
| `CAL ZERO` | Calibration zero offset | Use while stationary upright |
| `SAVECFG` | Persists config | Writes active config to storage |
| `ARM` | Transition toward armed path | Guarded by safety checks |
| `DISARM` | Transition to safe/idle path | Stops balancing loop |
| `ESTOP LATCH` / `ESTOP RESET` | Emergency stop state | Latch blocks motion commands |

Source mode: `profile_plus_sketch_inline`.

Contract note: STATUS telemetry should include `ang`, `raw`, and `gyro|gyr|gx` for Kalman/compatibility compliance.

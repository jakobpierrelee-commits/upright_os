# Control State Machine

## States
- `DISCONNECTED`
- `SAFE_IDLE`
- `ARMED`
- `BALANCING`
- `FAULT`
- `CALIBRATING`

## Required Transitions
- `DISCONNECTED -> SAFE_IDLE`: successful serial session + ready status.
- `SAFE_IDLE -> ARMED`: explicit user arm command.
- `ARMED -> BALANCING`: arming conditions met.
- `BALANCING -> FAULT`: safety violation, tip cutoff, invalid mode event.
- `BALANCING -> SAFE_IDLE`: explicit disarm.
- `ANY -> DISCONNECTED`: transport/session loss.
- `BALANCING + DISCONNECTED`: immediate disarm policy.

## Forbidden
- Implicit auto-arming on boot in default policy.
- Silent transitions without telemetry/log event.

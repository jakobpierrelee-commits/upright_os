# App Architecture V1

## Scope
Single-user local control stack with production-grade architecture patterns.

## Locked Decisions
- Runtime topology: split services.
- UI hosting policy: local-only for now (cloud-ready later).
- Bridge auth model: localhost + local user context only.
- Profile storage: local with cloud-ready schema.
- Telemetry transport: WebSocket stream.
- Live tuning during BALANCING: bounded, queued, tick-boundary apply.
- Arming UX: two-step arm.
- E-Stop policy: latching reset flow.
- Commissioning orchestration: both scripted and step-based.

## Service Boundaries
1. Bridge Service (`app/bridge`)
- Owns serial session.
- Enforces command safety policy.
- Exposes HTTP control API + WebSocket telemetry.
- Executes commissioning workflow and stores artifacts.

2. Ops Console UI (`app/ui/ops-console`)
- React/Vite/TypeScript frontend.
- Two-step arm flow and latching E-Stop controls.
- Tuning panel with bounded live-change constraints.
- Commissioning panel: `Run Full` and `Step Mode`.

## Bridge API Contract (V1)
- `GET /health`
- `GET /status`
- `POST /command`
- `POST /arm/prepare`
- `POST /arm/confirm`
- `POST /disarm`
- `POST /estop/latch`
- `POST /estop/reset`
- `POST /tuning/pid`
- `POST /tuning/motion`
- `POST /setpoint`
- `POST /commissioning/run`
- `POST /commissioning/step`
- `GET /commissioning/status`
- `GET /commissioning/artifacts`
- `WS /telemetry`

## Safety Enforcement (Bridge-side)
1. Drop all remote-nonlocal requests (localhost only in V1).
2. On bridge disconnect from app session during BALANCING: immediate `DISARM`.
3. Reject large tuning jumps while BALANCING.
4. Apply allowed tuning deltas only at tick boundaries.

## KPI Gate (all required)
1. Disturbance recovery.
2. Long-hold stability.
3. Position return accuracy.

## Latency Targets
- Command-to-actuation <= 100 ms.
- Telemetry stream >= 20 Hz.

## Future Cloud Path
- Keep API contract stable.
- Add auth/token layer when hosted UI is enabled.
- Move profile sync to Railway + Postgres without changing local runtime controls.

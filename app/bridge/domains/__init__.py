"""
UpRight.os Domain Layer

Domain modules contain business logic organized by bounded context.
Each domain is responsible for a specific area of functionality.

Domains:
- control_runtime: Serial gateway, watchdog, telemetry hub
- firmware_lifecycle: Compile, upload, recovery, artifacts
- hardware_profile: Robot profiles, manifests, compatibility
- safety_prearm: Preflight checks, pre-arm gates, fail-closed
- tuning_intelligence: Tuning policy, recommendations
- session_traceability: Session state, checkpoints, audit
"""

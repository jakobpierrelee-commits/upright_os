# Domain Map

**Status:** Active
**Authority:** PRD: Architecture Foundation + Refactor Execution Protocol
**Version:** 1.0
**Created:** 2026-02-26
**Owner:** Mission Command (JVKE)

---

## Purpose

Canonical domain ownership, boundaries, and source-of-truth references for the UpRight.os modular monolith architecture.

---

## Domain Set (Canonical)

Per PRD §4.1, seven domains define the architecture:

| # | Domain | Description |
|---|--------|-------------|
| 1 | Control Runtime | Serial, watchdog, telemetry loop |
| 2 | Firmware Lifecycle | Compile/upload/recovery/artifacts |
| 3 | Hardware Profile + Compatibility | Profiles/manifests/compat gates |
| 4 | Safety + Pre-Arm | Preflight/prearm/fail-closed blocks |
| 5 | Tuning Intelligence | Policy/recommendation logic |
| 6 | Session + Traceability | Session state/provenance/audit |
| 7 | Operator UX | Workflow surfaces and state orchestration |

---

## Domain Ownership Matrix

| Domain | Owner | Primary Implementation | Policy Authority | Contract Authority | Test Authority |
|--------|-------|------------------------|------------------|-------------------|----------------|
| Control Runtime | Cascade | `app/bridge/serial_gateway.py` | `docs/contracts/telemetry_contract_v2.md` | `docs/contracts/telemetry_contract_v2.md` | `app/bridge/tests/test_serial_*.py` |
| Firmware Lifecycle | Cascade | `app/bridge/clean_firmware_ops.py` | PRD §6 | `docs/contracts/artifact_provenance_schema_v1.md` | `app/bridge/tests/test_firmware_*.py` |
| Hardware Profile | Cascade | `app/bridge/robot_profiles.json` | `docs/contracts/multi_hardware_profile_contract_v1.md` | `docs/contracts/compat_policy_v1.json` | `app/bridge/tests/test_*profile*.py` |
| Safety + Pre-Arm | Cascade | `app/bridge/arm_safety.py`, `app/bridge/clean_preflight.py` | PRD §6.4 (Safety integrity) | TBD | `app/bridge/tests/test_*preflight*.py` |
| Tuning Intelligence | Cascade | `app/bridge/tuning_policy.py` | `docs/contracts/tuning_sessions_schema_v1.md` | `docs/contracts/tuning_sessions_schema_v1.md` | `app/bridge/tests/test_tuning_*.py` |
| Session + Traceability | Cascade | `app/bridge/codex_db.py` | PRD §4.2 | TBD | `app/bridge/tests/test_codex_*.py` |
| Operator UX | Cascade | `app/ui/ops-console/src/` | UI Style Guide (TBD) | TBD | `app/ui/ops-console/src/*.test.tsx` |

---

## Boundary Rules

### Backend (app/bridge)

```
routes/          → Transport-only handlers (HTTP/WS endpoints)
domains/         → Business logic per domain (target structure)
adapters/        → Serial/DB/filesystem/external wrappers
contracts/       → Request/response/event schemas
policies/        → Invariants + gate rules
```

### Allowed Import Edges

Per `docs/contracts/dependency_matrix_v1.json`:

| From | To | Allowed |
|------|----|---------|
| routes | domains | ✓ |
| domains | adapters | ✓ |
| domains | contracts | ✓ |
| domains | policies | ✓ |
| routes | adapters | ✗ (except framework glue) |
| domain A | domain B | ✗ (without explicit entry) |

### Frontend (app/ui/ops-console)

```
features/        → Domain-aligned UI modules
components/ui/   → Shared presentational primitives
lib/api/         → Domain-aligned API clients (NEW)
  ├── client.ts     → Shared fetch utilities
  ├── health.ts     → Health/status endpoints
  ├── control.ts    → Arm/disarm/tuning endpoints
  ├── firmware.ts   → Firmware lifecycle endpoints
  ├── profiles.ts   → Hardware profiles/compat
  ├── auth.ts       → Authentication endpoints
  └── telemetry.ts  → Serial/burst/trace endpoints
```

| From | To | Allowed |
|------|----|---------|
| ui_features | ui_components | ✓ |
| ui_features | ui_lib | ✓ |
| ui_components | ui_lib | ✓ |
| ui_features | backend internals | ✗ |

---

## Source-of-Truth Links

### Contracts (Canonical Artifacts)

| Artifact | Path | Purpose |
|----------|------|---------|
| Dependency Matrix | `docs/contracts/dependency_matrix_v1.json` | Import boundary enforcement |
| Dependency Schema | `docs/contracts/dependency_matrix_v1.schema.json` | Matrix validation |
| Compat Policy | `docs/contracts/compat_policy_v1.json` | Hardware compatibility gates |
| Provider Routing | `docs/contracts/provider_routing_v1.json` | AI provider routing rules |
| Telemetry Contract | `docs/contracts/telemetry_contract_v2.md` | Telemetry data format |
| Tuning Sessions Schema | `docs/contracts/tuning_sessions_schema_v1.md` | Tuning session structure |
| Hardware Profile Contract | `docs/contracts/multi_hardware_profile_contract_v1.md` | Profile requirements |
| Artifact Provenance | `docs/contracts/artifact_provenance_schema_v1.md` | Firmware artifact tracking |

### Governance Docs (Root Authority)

| Doc | Path | Purpose |
|-----|------|---------|
| Architecture PRD | `docs/PRD_ARCHITECTURE_FOUNDATION_REFACTOR_PROTOCOL.md` | Refactor execution protocol |
| Domain Map | `docs/DOMAIN_MAP.md` | This document |
| Session Handoff | `docs/SESSION_HANDOFF.md` | Agent handoff records |
| Pending Decisions | `docs/PENDING_DECISIONS.md` | Blocker queue |
| Signoff Ledger | `docs/MULTI_AGENT_SIGNOFF_LEDGER.md` | Decision records |

---

## Verification Tooling

Per PRD §7.2, these tools enforce boundaries:

| Tool | Purpose | Pass Criteria |
|------|---------|---------------|
| `tools/lean/check_dependency_matrix.py` | Validate matrix structure | `--help` exits 0; pinned command passes |
| `tools/lean/check_import_boundaries.py` | Enforce forbidden imports | `--help` exits 0; pinned command passes |
| `tools/lean/check_contract_drift.py` | Detect contract drift | `--help` exits 0; pinned command passes |
| `tools/lean/ci_clean_lane.sh` | Baseline quality gate | Exit 0 |

---

## Current State vs Target

| Area | Current | Target | Status |
|------|---------|--------|--------|
| server.py | 9,106 lines (composition root + routes) | Composition root only | ✅ Phase B complete |
| routes/ | Flat in bridge root as `routes_*.py` | Transport handlers | 🟡 Optional consolidation |
| domains/ | 7 domains, 28 modules extracted | Domain modules | ✅ Phase B complete |
| adapters/ | `serial_gateway.py` | Full adapter layer | 🟡 Partial |
| UI features/ | CleanApp default, features/ partial | Domain-aligned | 🟡 Phase D in progress |
| lib/api/ | 7 domain API clients extracted | Domain clients | ✅ Phase D.2 complete |
| codex_tools.py | 3,485 lines | Extracted to domains | 🔴 Phase E.2 pending |
| api.ts | 1,962 lines (legacy) | Migrate to lib/api/ | � Gradual migration |

### Domain Module Inventory (as of 2026-02-26, updated)

```
app/bridge/domains/
├── ai_agent/                          # Shared constants/contracts for tools
│   ├── ai_manager.py                  # AI provider orchestration
│   └── tool_constants.py              # ToolResult, error codes, limits (shared)
├── control_runtime/
│   ├── bridge_control_state.py
│   ├── telemetry_hub.py
│   ├── tools.py                       # ControlTools (delegated from codex_tools)
│   └── watchdog.py
├── firmware_lifecycle/
│   ├── firmware_manager.py
│   └── tools.py                       # FirmwareTools (delegated from codex_tools)
├── hardware_profile/
│   ├── hardware_context.py
│   └── robot_profiles_manager.py
├── safety_prearm/
│   ├── tools.py                       # SafetyTools (delegated from codex_tools)
│   └── tuning_preflight.py
├── session_traceability/
│   ├── agent_mission_manager.py
│   ├── ai_profile_manager.py
│   ├── assistant_knowledge.py
│   ├── auth_manager.py
│   ├── checkpoint_manager.py
│   ├── config_history.py
│   ├── config_history_manager.py
│   ├── design_memory.py
│   ├── mission_memory.py
│   ├── setup_attempt_history.py
│   └── tools.py                       # SessionTools (delegated from codex_tools)
└── tuning_intelligence/
    ├── commissioning_manager.py
    ├── host_capture_manager.py
    ├── simulation_tools.py            # SimulationTools (delegated from codex_tools)
    └── tools.py                        # TelemetryTools (delegated from codex_tools)
```

**Note:** `ai_agent/` is designated as `domain_shared` zone in `dependency_matrix_v1.json`. All domain tools may import from it. Evaluate migration to `contracts/` in Phase F.

---

## Frozen Restart Queue (per PRD §8.2)

Restart queue is frozen in this order for initial decomposition pass:

| Priority | Slice | Risk Level | Status |
|----------|-------|------------|--------|
| 1 | `health/status` routes | Low | ✅ Complete (routes_health.py) |
| 2 | `profiles/compat` routes | Low | ✅ Complete (routes_profiles.py extended) |
| 3 | `firmware lifecycle` routes | Medium | ✅ Complete (routes_firmware.py: 10 GET + 9 POST) |
| 4 | `preflight/prearm` safety wrappers | Medium (no behavior drift) | 🔴 Not started |
| 5 | `codex/chat` route wrappers | Medium | 🔴 Not started |
| 6 | `tuning intelligence` routes | High (safety-adjacent) | 🔴 Not started |

**Change control:** Any queue reorder requires explicit decision log entry in `docs/MULTI_AGENT_SIGNOFF_LEDGER.md`.

---

## Amendment Process

1. Log change proposal with rationale, risk, and rollback plan.
2. Approve via Mission Command decision ID.
3. Update this document and `dependency_matrix_v1.json` in same change set.
4. Broadcast update to all active agents.

---

## References

- PRD: `docs/PRD_ARCHITECTURE_FOUNDATION_REFACTOR_PROTOCOL.md`
- Dependency Matrix: `docs/contracts/dependency_matrix_v1.json`
- Pause PRD: `docs/PRD_SAFE_MULTI_AGENT_REFACTOR_PAUSE.md`

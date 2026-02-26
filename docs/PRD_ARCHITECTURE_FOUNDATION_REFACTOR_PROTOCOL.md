# PRD: Architecture Foundation + Refactor Execution Protocol

**Status:** Proposed (Execution-Ready after approval)
**Priority:** P0
**Owner:** Mission Command (JVKE)
**Primary Implementation:** Cascade
**Governance Review:** Codex
**Created:** 2026-02-25

---

## 1) Purpose

Define a principles-first architecture policy for resuming refactor safely, with minimal non-negotiable controls that preserve reliability, safety, and delivery speed.

---

## 2) Objectives

1. Establish complete domain identification across repo.
2. Establish explicit boundaries and allowed dependencies.
3. Assign one canonical source of truth per domain.
4. Resume refactor in deterministic, low-risk slices.
5. Preserve runtime safety and operator continuity while improving maintainability.
6. Replace rule-heavy execution with principles + minimal hard controls.

### 2.1 Operating Mode (Current)

- **Delivery model:** Single-agent execution (Cascade) with Mission Command final authority.
- **Mission Command decisions required for:** boundary changes, contract/schema/API changes, and safety/prearm/tuning guardrail behavior changes.
- **Peer-agent coordination:** optional; not required for day-to-day execution in this mode.

---

## 3) Non-Goals

- Full greenfield rewrite.
- Breaking API changes during foundation phase.
- Parallel feature expansion during boundary-definition phase.
- Governance ambiguity between root docs and lane-local docs.

---

## 4) Architecture Model (Target)

Adopt a **modular monolith** runtime with hard internal boundaries.

### 4.1 Domain Set (Canonical)
1. **Control Runtime** (serial, watchdog, telemetry loop)
2. **Firmware Lifecycle** (compile/upload/recovery/artifacts)
3. **Hardware Profile + Compatibility** (profiles/manifests/compat gates)
4. **Safety + Pre-Arm** (preflight/prearm/fail-closed blocks)
5. **Tuning Intelligence** (policy/recommendation logic)
6. **Session + Traceability** (session state/provenance/audit)
7. **Operator UX** (workflow surfaces and state orchestration)

### 4.2 Canonical Source-of-Truth Rule
Each domain must have:
- 1 policy authority file,
- 1 contract authority (schema/spec),
- 1 primary implementation root,
- 1 test authority suite.

If conflict exists, the domain's contract authority wins; all other docs must reference it.

### 4.3 Principles (Best-Practice Policy Layer)

1. **Safety over speed:** no refactor decision can weaken prearm/fail-closed behavior.
2. **Small reversible changes:** refactor in thin slices with explicit rollback point.
3. **Evidence over assertion:** claims require tests, command output, or artifacts.
4. **Single source of truth:** every decision and contract points to one canonical path.
5. **Transparency by default:** failures and uncertainties are logged explicitly, never hidden.

---

## 5) Target Repo Structure (Operational)

```text
app/bridge/
  server.py                 # composition root only
  routes/                   # transport-only handlers
  domains/
    control_runtime/
    firmware_lifecycle/
    hardware_profile/
    safety_prearm/
    tuning_intelligence/
    session_traceability/
  adapters/                 # serial/db/filesystem/external wrappers
  contracts/                # request/response/event schemas
  policies/                 # invariants + gate rules

app/ui/ops-console/src/
  features/                 # domain-aligned UI modules
  components/ui/            # shared presentational primitives
  lib/                      # shared utilities
```

---

## 6) Minimal Non-Negotiables (Hard Controls)

Only these controls are hard gates for this PRD:

1. **Boundary integrity:** routes do transport only; domain logic lives in domains.
2. **Dependency integrity:** imports must satisfy canonical dependency matrix.
3. **Contract integrity:** no unintended schema/API drift.
4. **Safety integrity:** fail-closed/prearm behavior must remain intact.
5. **Governance integrity:** root shared docs are canonical; lane-local docs are draft unless synced.

---

## 7) Dependency Matrix Policy

Maintain a machine-checkable allowlist:

- Allowed: `routes -> domains`, `domains -> adapters/contracts/policies`
- Forbidden: `routes -> adapters` (except framework glue), `domain A -> domain B` without explicit entry
- Forbidden: UI feature importing backend internals

Canonical artifact path (single source of truth):
- `docs/contracts/dependency_matrix_v1.json`

Supporting artifacts:
- `docs/contracts/dependency_matrix_v1.schema.json` (validation schema)
- `docs/DOMAIN_MAP.md` (human-readable domain ownership + boundary rationale)

CI must fail on forbidden import edges.

### 7.1 CI Command Contract (Pinned)

The following commands are authoritative for architecture-boundary enforcement. CI must run these exact commands (or wrappers invoking them unchanged):

```bash
# 1) Validate dependency matrix structure
python3 tools/lean/check_dependency_matrix.py \
  --matrix docs/contracts/dependency_matrix_v1.json \
  --schema docs/contracts/dependency_matrix_v1.schema.json

# 2) Enforce forbidden import edges from dependency matrix
python3 tools/lean/check_import_boundaries.py \
  --matrix docs/contracts/dependency_matrix_v1.json \
  --repo-root .

# 3) Enforce contract drift checks
python3 tools/lean/check_contract_drift.py \
  --contracts-root docs/contracts \
  --fail-on-drift

# 4) Run clean-lane CI baseline checks
./tools/lean/ci_clean_lane.sh
```

Notes:
- Commands (1)-(3) are mandatory deliverables for Phase A exit if not yet present.
- `./tools/lean/ci_clean_lane.sh` remains the baseline quality/safety gate for current lane.

### 7.2 Tooling Existence Gate (Hard)

Phase A cannot exit unless all architecture-governance tooling exists and is executable:

- `tools/lean/check_dependency_matrix.py`
- `tools/lean/check_import_boundaries.py`
- `tools/lean/check_contract_drift.py`

Pass criteria:
1. File exists at required path.
2. `--help` exits with status `0` for each tool.
3. Pinned command contract in §7.1 executes without runtime/tooling errors.

Failure handling:
- If any required tool is missing or non-executable, trigger STOP-POINT and log blocker in `docs/PENDING_DECISIONS.md`.
- No Phase A exit claim is valid until gate is green.

---

## 8) Practical Sequence (Execution Plan)

### Phase A — Foundation Lock (2-4 days)
1. Publish `DOMAIN_MAP.md` with owners, boundaries, and SoT matrix.
2. Publish dependency matrix at `docs/contracts/dependency_matrix_v1.json` and schema at `docs/contracts/dependency_matrix_v1.schema.json`.
3. Freeze restart queue and slice order.
4. Lock regression gates per slice.

**Exit:** Foundation artifacts approved and decision ID logged.

### 8.2 Frozen Restart Queue + Slice Order (v1)

Restart queue is frozen in this order for initial decomposition pass:
1. `health/status` routes (low risk)
2. `profiles/compat` routes
3. `firmware lifecycle` routes
4. `preflight/prearm` safety wrappers (no behavior drift)
5. `codex/chat` route wrappers
6. `tuning intelligence` routes (last; safety-adjacent)

Change control:
- Any queue reorder requires explicit decision log entry in `docs/MULTI_AGENT_SIGNOFF_LEDGER.md`.

### 8.3 Locked Regression Gate Pack (v1)

The following gate pack is locked for all slice completion claims:
1. `python3 tools/lean/check_dependency_matrix.py --matrix docs/contracts/dependency_matrix_v1.json --schema docs/contracts/dependency_matrix_v1.schema.json`
2. `python3 tools/lean/check_import_boundaries.py --matrix docs/contracts/dependency_matrix_v1.json --repo-root .`
3. `python3 tools/lean/check_contract_drift.py --contracts-root docs/contracts --fail-on-drift`
4. `./tools/lean/ci_clean_lane.sh`

Recording requirements:
- Exact command outputs are recorded in `docs/SESSION_HANDOFF.md`.
- Any gate failure blocks slice completion and must be logged in `docs/PENDING_DECISIONS.md` if not immediately self-resolved.

### Phase B — Composition Root Slim-down
1. Reduce `server.py` to composition/wiring and route registration.
2. No endpoint contract changes.
3. Add parity tests around moved handlers.

**Exit:** contract parity verified + tests green.

### Phase C — Domain-Slice Refactor (one slice per PR)
Recommended order:
1. health/status (low risk)
2. profiles/compat
3. firmware lifecycle
4. preflight/prearm safety wrappers
5. codex/chat route wrappers
6. tuning intelligence routes (last; safety-adjacent)

Each slice requires:
- no behavior drift,
- parity tests,
- rollback note,
- handoff snapshot.

### Phase D — UI Boundary Convergence
1. Move UI sections to domain-aligned features.
2. Enforce `strings.ts`/copy centralization.
3. Eliminate duplicate gate logic in frontend.

### Phase E — Hardening + Governance Consolidation
1. Consolidate decision/governance flow to explicit authority chain.
2. Add CI checks for module size + forbidden imports + contract drift.
3. Final architecture handoff with risks/open items.

### Governance Topology Rule (Shared vs Lane-Local)

Canonical governance docs (shared authority):
- `docs/*` at repo root are authoritative for active program decisions, PRDs, and handoff governance.

Lane-local docs (working copies only):
- `.worktrees/<lane>/docs/*` are non-authoritative and may diverge temporarily for drafting.

Conflict resolution:
1. Root `docs/*` wins by default.
2. Lane-local updates must be promoted via explicit sync commit into root `docs/*`.
3. Handoffs must cite root doc references, not lane-local paths, unless marked `DRAFT_NOT_CANONICAL`.

Required handoff metadata:
- `governance_source=shared_root_docs`
- `lane_local_docs_used=true|false`
- `lane_sync_status=synced|pending`

### 8.1 Check-In Cadence (Lean)

To reduce coordination drag while preserving governance integrity:

1. Mandatory check-ins occur only at:
   - slice start,
   - slice completion,
   - escalation events (boundary/contract/safety).
2. Optional heartbeat check-in: every 4 hours for long-running slices.
3. If lane-local governance docs are used, promotion to root `docs/*` must occur before the next merge checkpoint.

Failure handling:
1. If lane-local governance content is not synced by merge checkpoint, merge is blocked until sync completes.
2. Repeated missed sync checkpoints in the same session require Mission Command review.

---

## 9) Decision Policy (How to Decide Work)

Use this lightweight decision order:

1. **Is this a boundary change?**
   - Yes: update/approve architecture artifacts first.
   - No: proceed as in-boundary slice.
2. **Does this change any contract/schema/API?**
   - Yes: explicit approval + contract tests required.
   - No: continue with normal slice checks.
3. **Does this touch safety/prearm/tuning guardrails?**
   - Yes: require parity confirmation before merge.
4. **Can this be isolated to one slice/PR?**
   - No: split until it can.

### 9.1 Merge Gate Stack (Applies to Every Change)

No change may merge unless all gates pass:
1. Scope gate: task mapped to approved domain/slice.
2. Contract gate: no unintended drift.
3. Verification gate: pinned command set passed.
4. Handoff gate: branch/SHA/files/tests/results/risks recorded.
5. Governance gate: canonical root docs referenced.

### 9.2 Self-Resolve-First Escalation Model

Default behavior is to resolve at the lowest level possible.

#### L1 — Self-Resolve (Default)
Agent may proceed without Mission Command escalation when all are true:
1. No boundary/domain ownership change.
2. No contract/schema/API change.
3. No safety/prearm/tuning guardrail behavior change.
4. Work is reversible and scoped to one slice.
5. Merge gate stack in §9.1 passes.

#### L2 — Peer-Resolve
If uncertainty remains but still appears in-bounds:
1. Perform an independent self-review pass (or optional peer review if available).
2. If confidence is restored and §9.1 passes, proceed.
3. If uncertainty persists, escalate to L3.

#### L3 — Mission Command Escalation
Escalation is mandatory when any are true:
1. Boundary/domain ownership conflict.
2. Contract drift or schema/API change required.
3. Safety/prearm/tuning guardrail behavior impact.
4. Unresolved cross-agent conflict.
5. Ambiguous authoritative source-of-truth document.

#### Required Evidence for L1/L2 Resolution
Record in handoff:
- `decision_type=self_resolved|peer_resolved|escalated`
- short decision rationale
- commands run + exact results
- rollback note
- files touched

Single-agent note:
- In single-agent mode, `peer_resolved` may be replaced with `self_reviewed` when no peer reviewer is in the active execution loop.

---

## 10) Work Classification Matrix

| Task Type | Allowed During Refactor | Requires New Approval |
|---|---|---|
| Mechanical move inside approved boundary | Yes | No (but all mandatory gates still apply) |
| Contract/schema change | Conditional | Yes |
| Safety gate behavior change | Conditional | Yes (high scrutiny) |
| New feature | No (during foundation and active slices) | Yes |
| Artifact/log/runtime output cleanup in product commit | No | N/A |

Uniformity rule:
- This matrix does not create alternate execution lanes.
- "No" in approval column means no additional design approval, not exemption from mandatory gate stack.

---

## 11) Verification Protocol

Per slice, run and record:
1. Targeted unit/integration tests for moved domain.
2. Contract parity tests for affected endpoints.
3. Build/type checks for UI/backend touched areas.
4. Regression command(s) relevant to affected safety/tuning surfaces.

Minimum architecture-governance command set (must be recorded in handoff):
1. `python3 tools/lean/check_dependency_matrix.py --matrix docs/contracts/dependency_matrix_v1.json --schema docs/contracts/dependency_matrix_v1.schema.json`
2. `python3 tools/lean/check_import_boundaries.py --matrix docs/contracts/dependency_matrix_v1.json --repo-root .`
3. `python3 tools/lean/check_contract_drift.py --contracts-root docs/contracts --fail-on-drift`
4. `./tools/lean/ci_clean_lane.sh`

All results recorded in `docs/SESSION_HANDOFF.md`.

---

## 12) Acceptance Criteria

- [ ] Canonical domain map exists and is approved.
- [ ] Dependency matrix exists and CI-enforced.
- [ ] `server.py` reduced to composition root with route/domain separation underway.
- [ ] At least 2 low-risk slices completed with parity.
- [ ] No unauthorized cross-domain dependencies introduced.
- [ ] Handoff and signoff logs updated for each slice.

---

## 13) Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Over-design slows delivery | Medium | Timebox foundation phase (2-4 days) |
| Hidden behavior drift in route extraction | High | Mandatory endpoint parity tests |
| Cross-agent overlap/conflicts | High | One-slice ownership + explicit queue |
| Governance doc sprawl persists | Medium | Single authority chain + conflict rule |

---

## 14) Policy Authority and Amendment

For work within this PRD scope, policy authority order is:
1. Mission Command decision records
2. Root shared governance docs in `docs/*`
3. This PRD and referenced contract artifacts
4. Lane-local working docs in `.worktrees/*/docs/*` (draft-only unless synced)

Policy amendment process:
1. Log change proposal with rationale, risk, and rollback plan.
2. Approve via Mission Command decision ID.
3. Update root shared docs and this PRD in the same change set.
4. Broadcast update to all active agents before continued execution.

---

## 15) Immediate Next Steps

1. Approve this PRD + pause PRD.
2. Create/approve `docs/DOMAIN_MAP.md` (derived action).
3. Start Phase A foundation lock.
4. Resume refactor only through Phase B/C slice protocol.

---

## 16) Program Default Answer (For All Agents)

"Follow principles-first execution with five hard controls only: boundary, dependency, contract, safety, and governance integrity. Keep slices small, reversible, and evidence-backed. Use root shared docs as canonical authority."

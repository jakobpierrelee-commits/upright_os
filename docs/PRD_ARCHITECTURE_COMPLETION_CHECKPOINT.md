# PRD: Architecture Completion Checkpoint

**Status:** Active
**Priority:** P0
**Owner:** Mission Command (JVKE)
**Parent PRD:** PRD_ARCHITECTURE_FOUNDATION_REFACTOR_PROTOCOL.md
**Created:** 2026-02-26
**Purpose:** Consolidate unfinished work and define clear path to PRD completion

---

## 1) Context

Work was executed out of sequence. Phase E (backend cleanup) and Phase D (UI convergence) were partially completed before Phase A (Foundation Lock) requirements were met.

This sub-PRD reconciles what was done, what remains, and establishes a clear completion path.

---

## 2) Work Completed (Out of Sequence)

### Phase D — UI Boundary Convergence
| Task | Status | Evidence |
|------|--------|----------|
| D.1 — Migrate App.tsx → CleanApp.tsx | ✅ Done | Feature extraction complete |
| D.2 — Split api.ts into domain clients | ✅ Done | `features/*/api.ts` created |
| D.3 — Enforce strings.ts centralization | 🔴 Pending | Hardcoded strings remain |
| D.4 — Eliminate duplicate gate logic | 🔴 Pending | Duplicates not audited |

### Phase E — Backend Cleanup
| Task | Status | Evidence |
|------|--------|----------|
| E.1 — Remove duplicates | ✅ Done | Duplicate `codex_db.py` removed |
| E.2 — Extract codex_tools.py | ✅ Done | 6 domain tool classes extracted |
| E.3 — Consolidate routes into domains | ⚪ Skipped | Optional per PRD |

### Domain Tool Classes Extracted
```
app/bridge/domains/
├── ai_agent/tool_constants.py       # Constants, errors, ToolResult
├── firmware_lifecycle/tools.py      # FirmwareTools
├── tuning_intelligence/tools.py     # TelemetryTools
├── tuning_intelligence/simulation_tools.py  # SimulationTools
├── session_traceability/tools.py    # SessionTools
├── control_runtime/tools.py         # ControlTools
└── safety_prearm/tools.py           # SafetyTools
```

### Delegation Completed in codex_tools.py
- `_tool_get_probe_results` → TelemetryTools
- `_tool_query_telemetry` → TelemetryTools
- `_tool_query_checkpoints` → SessionTools
- `_tool_search_docs` → SessionTools
- `_tool_execute_shell` → ControlTools
- `_tool_execute_command` → ControlTools
- `_tool_edit_sketch_value` → FirmwareTools
- `_tool_read_sketch` → FirmwareTools

---

## 3) Work Remaining (Sequenced Properly)

### Phase A — Foundation Lock (COMPLETE ✅)

**All deliverables verified 2026-02-26:**

| Deliverable | Status | Evidence |
|-------------|--------|----------|
| `docs/DOMAIN_MAP.md` (approved) | ✅ Complete | Updated with current inventory, frozen restart queue |
| `docs/contracts/dependency_matrix_v1.json` | ✅ Complete | 9 zones, 8 allowed edges, notes documented |
| `docs/contracts/dependency_matrix_v1.schema.json` | ✅ Complete | JSON Schema 2020-12 |
| `tools/lean/check_dependency_matrix.py` | ✅ Complete | `--help` exits 0, pinned command passes |
| `tools/lean/check_import_boundaries.py` | ✅ Complete | `--help` exits 0, pinned command passes |
| `tools/lean/check_contract_drift.py` | ✅ Complete | `--help` exits 0, pinned command passes |
| Frozen restart queue documented | ✅ Complete | Added to DOMAIN_MAP §Frozen Restart Queue |

### Phase B — Composition Root Slim-down

| Deliverable | Status | Action Required |
|-------------|--------|-----------------|
| `server.py` reduced to composition/wiring only | 🔴 Not started | Extract business logic to domains |
| Route registration only in server.py | 🔴 Not started | Move handlers to domain routes |
| Parity tests for moved handlers | 🔴 Not started | Add tests |

### Phase C — Domain-Slice Refactor

| Slice | Status | Priority |
|-------|--------|----------|
| health/status routes | 🔴 Not started | 1 (lowest risk) |
| profiles/compat routes | 🔴 Not started | 2 |
| firmware lifecycle routes | 🔴 Not started | 3 |
| preflight/prearm safety wrappers | 🔴 Not started | 4 |
| codex/chat route wrappers | 🔴 Not started | 5 |
| tuning intelligence routes | 🔴 Not started | 6 (highest risk) |

### Phase D — Remaining UI Work

| Task | Status | Action Required |
|------|--------|-----------------|
| D.3 — strings.ts centralization | 🔴 Pending | Audit and migrate hardcoded strings |
| D.4 — duplicate gate logic elimination | 🔴 Pending | Audit and consolidate |

### Phase F — Hardening + Governance

| Deliverable | Status | Action Required |
|-------------|--------|-----------------|
| CI checks for module size | 🔴 Not started | Add to CI |
| CI checks for forbidden imports | 🔴 Not started | Add to CI (depends on Phase A tools) |
| CI checks for contract drift | 🔴 Not started | Add to CI (depends on Phase A tools) |
| Final architecture handoff | 🔴 Not started | Complete after all phases |

---

## 4) Recommended Execution Order

**Phase A must complete before any further Phase B-F work.**

### Immediate (Phase A Completion)
1. Update `docs/DOMAIN_MAP.md` with:
   - Current domain ownership
   - Canonical source-of-truth per domain
   - Dependency rules (what can import what)
   - Frozen restart queue

2. Create `docs/contracts/dependency_matrix_v1.json`:
   - Define allowed import edges
   - Define forbidden import edges
   - Machine-parseable format

3. Create CI governance tools:
   - `check_dependency_matrix.py`
   - `check_import_boundaries.py`
   - `check_contract_drift.py`

### Then (Phases B-C)
4. Slim down `server.py` (Phase B)
5. Complete route slices in order (Phase C)

### Finally (Phases D-F)
6. Complete D.3, D.4 (UI cleanup)
7. Add CI hardening (Phase F)
8. Final handoff

---

## 5) Acceptance Criteria (This Sub-PRD)

- [x] Phase A deliverables complete and CI tools executable
- [x] `DOMAIN_MAP.md` updated and approved
- [x] Dependency matrix created and schema-validated
- [x] All 3 CI governance tools pass `--help` check
- [x] Clear path documented for remaining phases

**Phase A Exit Verified:** 2026-02-26

```bash
# Verification commands run:
python3 tools/lean/check_dependency_matrix.py --matrix docs/contracts/dependency_matrix_v1.json --schema docs/contracts/dependency_matrix_v1.schema.json
# [check_dependency_matrix] PASS (zones=9, allowed_edges=8)

python3 tools/lean/check_import_boundaries.py --matrix docs/contracts/dependency_matrix_v1.json --repo-root .
# [check_import_boundaries] PASS (scanned=11312, boundary_scoped=56, zones=8)

python3 tools/lean/check_contract_drift.py --contracts-root docs/contracts --fail-on-drift
# [check_contract_drift] PASS (contracts=10, versioned=8)
```

---

## 6) Current Branch State

- **Branch:** `recover/uiux-restore-2026-02-19`
- **Tests:** 415 passing
- **codex_tools.py:** Reduced from ~3,500 to ~3,060 lines

---

## 7) Decision Required

**Status:** Phase A complete. Ready for Phase B.

**Mission Command:** Confirm Phase A exit and approve Phase B start.

**Recommended Next Step:** Begin Phase B (Composition Root Slim-down) — extract business logic from `server.py` to domain modules, following frozen restart queue order.

---

## 8) Phase A Exit Gate (Verified)

All criteria from PRD §7.2 satisfied:

| Criterion | Result |
|-----------|--------|
| `check_dependency_matrix.py` exists | ✅ |
| `check_dependency_matrix.py --help` exits 0 | ✅ |
| `check_import_boundaries.py` exists | ✅ |
| `check_import_boundaries.py --help` exits 0 | ✅ |
| `check_contract_drift.py` exists | ✅ |
| `check_contract_drift.py --help` exits 0 | ✅ |
| Pinned command contract executes | ✅ |

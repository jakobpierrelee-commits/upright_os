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

### Phase A — Foundation Lock (BLOCKING)

**Required for PRD exit — cannot proceed without these:**

| Deliverable | Status | Action Required |
|-------------|--------|-----------------|
| `docs/DOMAIN_MAP.md` (approved) | 🟡 Exists but stale | Update with current domain ownership, boundaries, SoT matrix |
| `docs/contracts/dependency_matrix_v1.json` | 🔴 Missing | Create machine-checkable dependency rules |
| `docs/contracts/dependency_matrix_v1.schema.json` | 🔴 Missing | Create validation schema |
| `tools/lean/check_dependency_matrix.py` | 🔴 Missing | Create CI tool |
| `tools/lean/check_import_boundaries.py` | 🔴 Missing | Create CI tool |
| `tools/lean/check_contract_drift.py` | 🔴 Missing | Create CI tool |
| Frozen restart queue documented | 🔴 Missing | Document in DOMAIN_MAP |

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

- [ ] Phase A deliverables complete and CI tools executable
- [ ] `DOMAIN_MAP.md` updated and approved
- [ ] Dependency matrix created and schema-validated
- [ ] All 3 CI governance tools pass `--help` check
- [ ] Clear path documented for remaining phases

---

## 6) Current Branch State

- **Branch:** `recover/uiux-restore-2026-02-19`
- **Tests:** 415 passing
- **codex_tools.py:** Reduced from ~3,500 to ~3,060 lines

---

## 7) Decision Required

**Mission Command:** Approve this checkpoint PRD and confirm execution order.

Options:
1. **Complete Phase A first** — Create governance artifacts before more code changes
2. **Continue mechanical refactor** — Finish delegation work, update governance later
3. **Hybrid** — Minimal Phase A (DOMAIN_MAP only), then continue

**Recommendation:** Option 1 — The governance artifacts will prevent architectural drift and make future work more deliberate.

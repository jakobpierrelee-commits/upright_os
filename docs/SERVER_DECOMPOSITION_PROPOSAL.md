# Server Decomposition Proposal - Codex Review Request

**Date:** 2026-02-25  
**Requestor:** Augment Agent #3 (Support Work)  
**Scope:** Mechanical refactoring of `app/bridge/server.py` (15,349 lines)  
**Status:** AWAITING CODEX APPROVAL

---

## Context

Per OWNERSHIP_BOUNDARIES.md, I am **Augment Agent #3** with delegated authority for:
- Mechanical refactoring (NO behavior changes)
- Test/verification support
- Documentation updates

Jake requested I check in with **Codex (mission control)** before proceeding with server.py decomposition work.

---

## Current State

### File Size Analysis
```bash
$ wc -l app/bridge/server.py
15349 app/bridge/server.py
```

### Existing Documentation
- **DEPLOYMENT_STRATEGY_2026-02-25.md** (lines 135-167): Defines server decomposition task
- **ARCHITECTURE_AUDIT_2026-02-25.md** (lines 56-73): Identifies server.py as "Critical" improvement
- **CLEANUP_MATRIX.md** (line 11): Defines pass/fail gates for server.py cleanup
- **OWNERSHIP_BOUNDARIES.md** (lines 30-50): Confirms Augment Agent #1 owns server decomposition

### Existing Clean Modules
The codebase already has extracted modules:
- `clean_auth_helpers.py`
- `clean_codex_chat.py`
- `clean_contracts.py`
- `clean_firmware_ops.py`
- `clean_legacy_gate.py`
- `clean_preflight.py`
- `clean_request_parsers.py`
- `clean_route_helpers.py`
- `clean_sse.py`
- `clean_status.py`
- `clean_threads.py`

---

## Proposed Approach

### Phase 1: Assessment & Test Baseline
1. **Run existing test suite** to establish baseline
2. **Map route structure** in server.py (identify all endpoints)
3. **Identify dependencies** between routes and managers
4. **Document current behavior** (no changes yet)

### Phase 2: Incremental Extraction (One Route File Per PR)
Following DEPLOYMENT_STRATEGY recommendation:

| Priority | Module | Endpoints | Est. Lines | Risk |
|----------|--------|-----------|------------|------|
| 1 | `routes/health.py` | `/status`, `/health` | ~300 | Low (read-only) |
| 2 | `routes/profiles.py` | Robot profile CRUD | ~400 | Low (isolated) |
| 3 | `routes/commissioning.py` | Commissioning workflows | ~400 | Medium |
| 4 | `routes/firmware.py` | Compile/upload/recovery | ~800 | Medium |
| 5 | `routes/codex.py` | AI chat, tools | ~600 | Medium |
| 6 | `routes/tuning.py` | `/pid`, `/motion`, `/limits` | ~500 | **HIGH - BLOCKED** |

**CRITICAL CONSTRAINT:** Per OWNERSHIP_BOUNDARIES.md line 42:
> `/tooling/tuning/*` routes are **Safety-adjacent, Cascade-only**

**Decision needed:** Should I extract tuning routes, or leave them in monolith for Cascade?

### Phase 3: Core Abstractions
Extract shared infrastructure:
- `core/control_state.py` - BridgeControlState class
- `core/request_handler.py` - Base handler, CORS, auth
- `core/middleware.py` - Common request/response handling

---

## Verification Strategy

### Per CLEANUP_MATRIX.md (line 11):
**Pass Gates:**
```bash
python3 -m py_compile app/bridge/server.py
cd app/bridge && pytest -q tests/test_clean_*.py \
  tests/test_server_runtime_manifest.py \
  tests/test_server_runtime_manifest_compat.py \
  tests/test_firmware_*.py
```

**Fail Gates:**
- Any endpoint contract change without scorecard/decision update
- Parity or firmware contract test regression
- Route behavior moved without wrapper parity tests

### Additional Verification
```bash
# Full test suite
cd app/bridge && pytest tests/ -v

# Engineering governance check
tools/verify_all.sh
```

---

## Questions for Codex

1. **Scope Approval:** Should I proceed with server decomposition as parallel track to M1?
2. **Tuning Routes:** Should I extract `/tooling/tuning/*` routes, or leave for Cascade?
3. **Priority Order:** Start with low-risk routes (health, profiles) or wait for M1 Phase 1?
4. **Branch Strategy:** Use `refactor/server-decomposition` or different naming?
5. **Rollback Plan:** Keep `server_legacy.py` backup as suggested in DEPLOYMENT_STRATEGY?

---

## Constraints I Will Honor

Per OWNERSHIP_BOUNDARIES.md:
- ✅ **NO behavior changes** - pure mechanical moves only
- ✅ **Must pass existing tests** - all 55+ test files
- ✅ **Does NOT own `/tooling/tuning/*`** - safety-adjacent, Cascade-only
- ✅ **Does NOT own migration logic** - consistency-critical
- ✅ **Exit criteria:** All tests pass, Cascade parity review approved, no functional diff

Per MULTI_AGENT_SYNC_PROTOCOL.md:
- ✅ Provide Start Gate (this document)
- ✅ Provide End Gate (files changed, tests run, results, handoff snapshot)
- ✅ Update MULTI_AGENT_SIGNOFF_LEDGER.md
- ✅ Append to SESSION_HANDOFF.md

---

## Recommendation

**Wait for Codex approval** before starting any extraction work.

If approved, I propose:
1. Start with **routes/health.py** (lowest risk, read-only endpoints)
2. Verify test suite passes
3. Get Cascade parity review
4. Proceed incrementally with one route file per iteration

---

## Next Steps

Awaiting Codex decision on:
- [ ] Approval to proceed with server decomposition
- [ ] Clarification on tuning route ownership
- [ ] Priority/sequencing guidance
- [ ] Any additional constraints or requirements

**Signed:** Augment Agent #3  
**Date:** 2026-02-25


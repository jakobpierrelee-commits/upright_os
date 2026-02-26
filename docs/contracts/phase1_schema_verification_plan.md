# Phase 1 Schema Verification Plan

**Decision ID:** MC-2026-0225-002  
**Owner:** Augment (verification) / Codex-Execution (implementation)  
**Status:** ACTIVE  
**Created:** 2026-02-25

---

## Scope

Verification-only plan for Codex-Execution Phase 1 schema work:
1. `tuning_sessions` + `tuning_candidates` tables
2. `artifact_provenance` table
3. Migration safety (forward/backward)
4. Regression test matrix for touched DB paths

**NOT in scope:** Product implementation, schema changes, or behavioral modifications.

---

## 1. Expected Schema Contracts

### 1.1 Tuning Sessions
- **Contract:** `docs/contracts/tuning_sessions_schema_v1.md`
- **Tables:** `tuning_sessions`, `tuning_candidates`
- **Dataclasses:** `TuningSession`, `TuningCandidate`
- **Indexes:** 5 total (3 on sessions, 2 on candidates)

### 1.2 Artifact Provenance
- **Contract:** `docs/contracts/artifact_provenance_schema_v1.md`
- **Tables:** `artifact_provenance`
- **Dataclasses:** `ArtifactProvenance`
- **Indexes:** 4 total

---

## 2. Migration Safety Checklist

### 2.1 Forward Migration (Phase 1 → Production)

**Pre-Migration Checks:**
- [ ] Backup existing `codex.db` before migration
- [ ] Verify existing tables unaffected: `telemetry_snapshots`, `checkpoints`, `doc_chunks`, `embeddings_meta`, `tool_audit`
- [ ] Confirm `IF NOT EXISTS` used for all CREATE TABLE statements
- [ ] Confirm `IF NOT EXISTS` used for all CREATE INDEX statements

**Migration Execution:**
```bash
# 1. Baseline existing schema
sqlite3 app/bridge/codex.db ".schema" > /tmp/schema_before.sql

# 2. Run migration (via CodexDB.init_schema() or dedicated migration script)
python3 -c "from app.bridge.codex_db import CodexDB; db = CodexDB(); db.init_schema()"

# 3. Verify new schema
sqlite3 app/bridge/codex.db ".schema tuning_sessions"
sqlite3 app/bridge/codex.db ".schema tuning_candidates"
sqlite3 app/bridge/codex.db ".schema artifact_provenance"

# 4. Verify indexes
sqlite3 app/bridge/codex.db "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name IN ('tuning_sessions', 'tuning_candidates', 'artifact_provenance');"

# 5. Verify existing tables unchanged
sqlite3 app/bridge/codex.db ".schema" > /tmp/schema_after.sql
diff /tmp/schema_before.sql /tmp/schema_after.sql | grep -v "tuning_sessions\|tuning_candidates\|artifact_provenance"
# Expected: No output (only new tables added)
```

**Post-Migration Checks:**
- [ ] All new tables exist
- [ ] All indexes created
- [ ] Foreign key constraints enforced
- [ ] Existing data intact (row counts unchanged)
- [ ] No schema modifications to existing tables

### 2.2 Backward Migration (Rollback)

**Rollback Execution:**
```bash
# 1. Backup current state
cp app/bridge/codex.db app/bridge/codex.db.backup

# 2. Drop new tables
sqlite3 app/bridge/codex.db "DROP TABLE IF EXISTS tuning_candidates;"
sqlite3 app/bridge/codex.db "DROP TABLE IF EXISTS tuning_sessions;"
sqlite3 app/bridge/codex.db "DROP TABLE IF EXISTS artifact_provenance;"

# 3. Verify rollback
sqlite3 app/bridge/codex.db ".schema" | grep -E "tuning_sessions|tuning_candidates|artifact_provenance"
# Expected: No output (tables removed)

# 4. Verify existing tables intact
sqlite3 app/bridge/codex.db "SELECT COUNT(*) FROM telemetry_snapshots;"
sqlite3 app/bridge/codex.db "SELECT COUNT(*) FROM checkpoints;"
# Expected: Same counts as before migration
```

**Rollback Verification:**
- [ ] New tables dropped successfully
- [ ] Existing tables unaffected
- [ ] Existing data intact
- [ ] Application continues to function (existing tests pass)

---

## 3. Regression Test Matrix

### 3.1 Baseline Tests (Must Pass Before & After)

| Test File | Test Focus | Pass Criteria |
|-----------|------------|---------------|
| `test_codex_db.py` | Existing schema init, telemetry, checkpoints, doc chunks | All tests green |
| `test_server_tuning_guardrails.py` | Tuning policy guardrails, preflight checks | 19 tests pass |
| `test_firmware_run_artifacts.py` | Firmware artifact persistence | All tests green |

**Baseline Command:**
```bash
pytest app/bridge/tests/test_codex_db.py -v
pytest app/bridge/tests/test_server_tuning_guardrails.py -v
pytest app/bridge/tests/test_firmware_run_artifacts.py -v
```

**Expected Output:**
```
test_codex_db.py::test_schema_init PASSED
test_codex_db.py::test_telemetry_logging PASSED
test_codex_db.py::test_checkpoint_crud PASSED
test_codex_db.py::test_doc_chunks PASSED
test_codex_db.py::test_embedding_meta PASSED
test_codex_db.py::test_stats PASSED
test_codex_db.py::test_retention_priority PASSED
test_codex_db.py::test_prune_empty_db PASSED

test_server_tuning_guardrails.py ... 19 passed

test_firmware_run_artifacts.py ... all passed
```

### 3.2 Phase 1 New Tests (Expected After Implementation)

| Test File | Test Focus | Pass Criteria |
|-----------|------------|---------------|
| `test_tuning_session_lifecycle.py` | Session CRUD, baseline/candidate tracking | All tests green |
| `test_artifact_provenance.py` | Provenance tracking, seed/version recording | All tests green |
| `test_phase1_migration.py` | Forward/backward migration safety | All tests green |

---

## 4. Exact Verification Commands

### 4.1 Schema Verification
```bash
# Verify tuning_sessions table
sqlite3 app/bridge/codex.db "PRAGMA table_info(tuning_sessions);"
# Expected: 12 columns (id, session_id, robot_id, started_at, ended_at, status, baseline_config_json, hypothesis, forbidden_moves_json, verdict, notes, created_by)

# Verify tuning_candidates table
sqlite3 app/bridge/codex.db "PRAGMA table_info(tuning_candidates);"
# Expected: 8 columns (id, session_id, candidate_index, applied_at, config_json, metrics_json, rating, notes)

# Verify artifact_provenance table
sqlite3 app/bridge/codex.db "PRAGMA table_info(artifact_provenance);"
# Expected: 13 columns (id, artifact_id, artifact_type, created_at, run_id, commit_sha, firmware_version, model_version, random_seed, numpy_seed, torch_seed, parent_artifact_id, metadata_json)

# Verify foreign keys
sqlite3 app/bridge/codex.db "PRAGMA foreign_key_list(tuning_candidates);"
# Expected: 1 FK to tuning_sessions(session_id) with CASCADE delete

sqlite3 app/bridge/codex.db "PRAGMA foreign_key_list(artifact_provenance);"
# Expected: 1 FK to artifact_provenance(artifact_id) for parent_artifact_id
```

### 4.2 Index Verification
```bash
sqlite3 app/bridge/codex.db "SELECT name, tbl_name FROM sqlite_master WHERE type='index' AND tbl_name='tuning_sessions';"
# Expected: idx_tuning_sessions_robot, idx_tuning_sessions_status, idx_tuning_sessions_started

sqlite3 app/bridge/codex.db "SELECT name, tbl_name FROM sqlite_master WHERE type='index' AND tbl_name='tuning_candidates';"
# Expected: idx_tuning_candidates_session, idx_tuning_candidates_applied

sqlite3 app/bridge/codex.db "SELECT name, tbl_name FROM sqlite_master WHERE type='index' AND tbl_name='artifact_provenance';"
# Expected: idx_artifact_provenance_type, idx_artifact_provenance_run_id, idx_artifact_provenance_commit, idx_artifact_provenance_created
```

### 4.3 Data Integrity Verification
```bash
# Test foreign key enforcement (tuning_candidates → tuning_sessions)
sqlite3 app/bridge/codex.db "PRAGMA foreign_keys=ON; INSERT INTO tuning_candidates (session_id, candidate_index, applied_at) VALUES ('nonexistent_session', 1, 1234567890.0);"
# Expected: FOREIGN KEY constraint failed

# Test CASCADE delete
sqlite3 app/bridge/codex.db "PRAGMA foreign_keys=ON; INSERT INTO tuning_sessions (session_id, robot_id, started_at) VALUES ('test_session', 'test_robot', 1234567890.0); INSERT INTO tuning_candidates (session_id, candidate_index, applied_at) VALUES ('test_session', 1, 1234567891.0); DELETE FROM tuning_sessions WHERE session_id='test_session'; SELECT COUNT(*) FROM tuning_candidates WHERE session_id='test_session';"
# Expected: 0 (candidate deleted via CASCADE)
```

---

## 5. Pass/Fail Criteria

### 5.1 PASS Criteria
- ✅ All baseline tests remain green (no regressions)
- ✅ All new tables created with correct schema
- ✅ All indexes created
- ✅ Foreign key constraints enforced
- ✅ Migration up succeeds without errors
- ✅ Migration down (rollback) succeeds without data loss
- ✅ Existing tables unmodified (schema diff clean)
- ✅ Phase 1 new tests pass (when implemented)

### 5.2 FAIL Criteria (Triggers PAUSE)
- ❌ Any baseline test fails after migration
- ❌ Schema mismatch between contract and implementation
- ❌ Missing indexes
- ❌ Foreign key constraints not enforced
- ❌ Existing table schema modified
- ❌ Data loss during migration or rollback
- ❌ Migration script errors

---

## 6. Acceptance Criteria Gaps (STOP-POINT Triggers)

If any of the following are unclear during verification, PAUSE and log blocker:

1. **Unclear:** How to handle existing `codex.db` files in production (migration strategy for deployed instances)
2. **Unclear:** Whether `tuning_sessions.session_id` should be UUID or human-readable (e.g., `session_2026-02-25_001`)
3. **Unclear:** Whether `artifact_provenance` should link to ALL existing artifacts retroactively or only new ones
4. **Unclear:** Performance impact of indexes on large datasets (need benchmark baseline)
5. **Unclear:** Whether `tuning_candidates.metrics_json` schema is defined (what fields are required?)

---

## 7. References

- MILESTONE_M1.md (M1 exit criteria)
- TUNING_INTELLIGENCE_PRD.md (Phase 1 requirements)
- docs/contracts/tuning_sessions_schema_v1.md
- docs/contracts/artifact_provenance_schema_v1.md
- docs/OWNERSHIP_BOUNDARIES.md (seed/version lock requirements)

---

## 8. Handoff to Codex-Execution

**Verification artifacts to provide:**
1. This verification plan
2. Schema contracts (tuning_sessions, artifact_provenance)
3. Exact verification commands
4. Pass/fail criteria
5. Regression test matrix

**Expected from Codex-Execution:**
1. Implementation of schema changes in `app/bridge/codex_db.py`
2. Dataclass definitions matching contracts
3. Migration script (or `init_schema()` updates)
4. Phase 1 tests (`test_tuning_session_lifecycle.py`, `test_artifact_provenance.py`, `test_phase1_migration.py`)
5. Verification run output (all commands from Section 4)


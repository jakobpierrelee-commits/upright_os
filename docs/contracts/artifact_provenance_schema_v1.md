# Artifact Provenance Schema Contract v1

**Decision ID:** MC-2026-0225-002  
**Owner:** Codex-Execution (implementation) / Augment (verification)  
**Status:** DRAFT (verification contract)  
**Created:** 2026-02-25

---

## Purpose

Define expected schema for `artifact_provenance` table to support traceability requirements per MILESTONE_M1.md (Phase 10 plumbing moved to Phase 1).

---

## Table: `artifact_provenance`

### Schema Definition

```sql
CREATE TABLE IF NOT EXISTS artifact_provenance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    artifact_id TEXT UNIQUE NOT NULL,
    artifact_type TEXT NOT NULL,  -- 'session', 'checkpoint', 'burst_capture', 'firmware_upload', etc.
    created_at REAL NOT NULL,
    run_id TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    firmware_version TEXT NOT NULL DEFAULT '',
    model_version TEXT NOT NULL DEFAULT '',
    random_seed INTEGER,
    numpy_seed INTEGER,
    torch_seed INTEGER,
    parent_artifact_id TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(parent_artifact_id) REFERENCES artifact_provenance(artifact_id)
);

CREATE INDEX IF NOT EXISTS idx_artifact_provenance_type ON artifact_provenance(artifact_type);
CREATE INDEX IF NOT EXISTS idx_artifact_provenance_run_id ON artifact_provenance(run_id);
CREATE INDEX IF NOT EXISTS idx_artifact_provenance_commit ON artifact_provenance(commit_sha);
CREATE INDEX IF NOT EXISTS idx_artifact_provenance_created ON artifact_provenance(created_at);
```

### Column Specifications

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Internal DB identifier |
| `artifact_id` | TEXT | UNIQUE NOT NULL | UUID or unique artifact identifier |
| `artifact_type` | TEXT | NOT NULL | Category: session, checkpoint, burst, firmware, etc. |
| `created_at` | REAL | NOT NULL | Unix timestamp (seconds since epoch) |
| `run_id` | TEXT | NOT NULL | Unique run identifier (UUID) |
| `commit_sha` | TEXT | NOT NULL | Git commit SHA (short or full) |
| `firmware_version` | TEXT | NOT NULL DEFAULT '' | Firmware version string (e.g., `profiled_runtime_v1.1.0`) |
| `model_version` | TEXT | NOT NULL DEFAULT '' | ML model version (semver, e.g., `tuning_model_v1.0.0`) |
| `random_seed` | INTEGER | NULL | Python random seed (for reproducibility) |
| `numpy_seed` | INTEGER | NULL | NumPy random seed |
| `torch_seed` | INTEGER | NULL | PyTorch random seed (if applicable) |
| `parent_artifact_id` | TEXT | NULL | Links to parent artifact (e.g., session → candidates) |
| `metadata_json` | TEXT | NOT NULL DEFAULT '{}' | Additional context (robot_id, operator, etc.) |

---

## Dataclass Definition (Expected)

```python
@dataclass
class ArtifactProvenance:
    id: Optional[int] = None
    artifact_id: str = ""
    artifact_type: str = ""
    created_at: float = 0.0
    run_id: str = ""
    commit_sha: str = ""
    firmware_version: str = ""
    model_version: str = ""
    random_seed: Optional[int] = None
    numpy_seed: Optional[int] = None
    torch_seed: Optional[int] = None
    parent_artifact_id: Optional[str] = None
    metadata_json: str = "{}"
```

---

## Integration Points

### Firmware Run Artifacts
- Existing `FirmwareManager._record_run_artifact()` should link to provenance
- `run_id` from firmware META command should populate `artifact_provenance.run_id`
- Firmware version from STATUS line should populate `firmware_version`

### Tuning Sessions
- Each `tuning_sessions` row should have corresponding `artifact_provenance` entry
- `artifact_type = 'tuning_session'`
- `artifact_id = tuning_sessions.session_id`

### Checkpoints
- Each `checkpoints` row should optionally link to provenance
- `artifact_type = 'checkpoint'`
- `parent_artifact_id` links to session if created during session

---

## Migration Safety Requirements

1. **Forward Migration:**
   - Table created with `IF NOT EXISTS`
   - No modifications to existing tables
   - Indexes created with `IF NOT EXISTS`
   - Self-referencing foreign key (parent_artifact_id) must handle NULL

2. **Backward Migration (Rollback):**
   ```sql
   DROP TABLE IF EXISTS artifact_provenance;
   ```

3. **Data Preservation:**
   - Existing tables unaffected
   - No foreign key constraints FROM existing tables TO provenance
   - Provenance is additive-only (no breaking changes)

---

## Verification Checklist

- [ ] Table `artifact_provenance` created successfully
- [ ] All indexes created
- [ ] Self-referencing foreign key works (parent_artifact_id)
- [ ] Dataclass `ArtifactProvenance` matches schema
- [ ] Migration up test passes
- [ ] Migration down test passes (rollback)
- [ ] Existing tests remain green
- [ ] No modifications to existing tables
- [ ] Integration with firmware run artifacts verified
- [ ] Integration with tuning sessions verified

---

## Seed/Version Lock Compliance

Per `docs/OWNERSHIP_BOUNDARIES.md` (lines 90-100):

**Every stochastic run MUST record:**
- ✅ `random_seed: int`
- ✅ `numpy_seed: int`
- ✅ `torch_seed: int` (if applicable)
- ✅ `firmware_version: str`
- ✅ `model_version: str` (semver)
- ✅ `commit_sha: str`
- ✅ `run_id: uuid`

**Replay Guarantee:**
- Any run must be reproducible from recorded seeds
- Test: `replay(run_id) == original_result` assertion required

---

## References

- MILESTONE_M1.md (lines 20-23, 49-51)
- TUNING_INTELLIGENCE_PRD.md (Phase 10, lines 170)
- docs/OWNERSHIP_BOUNDARIES.md (lines 89-111)
- app/bridge/tests/test_firmware_run_artifacts.py (existing provenance patterns)


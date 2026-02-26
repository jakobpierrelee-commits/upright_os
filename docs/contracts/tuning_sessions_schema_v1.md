# Tuning Sessions Schema Contract v1

**Decision ID:** MC-2026-0225-002  
**Owner:** Codex-Execution (implementation) / Augment (verification)  
**Status:** DRAFT (verification contract)  
**Created:** 2026-02-25

---

## Purpose

Define expected schema for `tuning_sessions` table to support Phase 1 baseline/candidate A/B comparison per MILESTONE_M1.md and TUNING_INTELLIGENCE_PRD.md.

---

## Table: `tuning_sessions`

### Schema Definition

```sql
CREATE TABLE IF NOT EXISTS tuning_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT UNIQUE NOT NULL,
    robot_id TEXT NOT NULL DEFAULT '',
    started_at REAL NOT NULL,
    ended_at REAL,
    status TEXT NOT NULL DEFAULT 'active',  -- 'active', 'completed', 'abandoned'
    baseline_config_json TEXT NOT NULL DEFAULT '{}',
    hypothesis TEXT NOT NULL DEFAULT '',
    forbidden_moves_json TEXT NOT NULL DEFAULT '[]',
    verdict TEXT,
    notes TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT 'codex'
);

CREATE INDEX IF NOT EXISTS idx_tuning_sessions_robot ON tuning_sessions(robot_id);
CREATE INDEX IF NOT EXISTS idx_tuning_sessions_status ON tuning_sessions(status);
CREATE INDEX IF NOT EXISTS idx_tuning_sessions_started ON tuning_sessions(started_at);
```

### Column Specifications

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Internal DB identifier |
| `session_id` | TEXT | UNIQUE NOT NULL | UUID or human-readable session identifier |
| `robot_id` | TEXT | NOT NULL DEFAULT '' | Links to robot profile |
| `started_at` | REAL | NOT NULL | Unix timestamp (seconds since epoch) |
| `ended_at` | REAL | NULL | Unix timestamp when session ended (NULL if active) |
| `status` | TEXT | NOT NULL DEFAULT 'active' | Session lifecycle state |
| `baseline_config_json` | TEXT | NOT NULL DEFAULT '{}' | JSON snapshot of PID/MOTION/LIMITS at session start |
| `hypothesis` | TEXT | NOT NULL DEFAULT '' | Human-readable tuning hypothesis/goal |
| `forbidden_moves_json` | TEXT | NOT NULL DEFAULT '[]' | JSON array of parameter changes to avoid |
| `verdict` | TEXT | NULL | Final outcome: 'improved', 'degraded', 'inconclusive', etc. |
| `notes` | TEXT | NOT NULL DEFAULT '' | Operator/agent notes |
| `created_by` | TEXT | NOT NULL DEFAULT 'codex' | Agent or user identifier |

### Related Table: `tuning_candidates`

```sql
CREATE TABLE IF NOT EXISTS tuning_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    candidate_index INTEGER NOT NULL,
    applied_at REAL NOT NULL,
    config_json TEXT NOT NULL DEFAULT '{}',
    metrics_json TEXT NOT NULL DEFAULT '{}',
    rating TEXT,  -- 'poor', 'ok', 'good', 'great'
    notes TEXT NOT NULL DEFAULT '',
    FOREIGN KEY(session_id) REFERENCES tuning_sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tuning_candidates_session ON tuning_candidates(session_id);
CREATE INDEX IF NOT EXISTS idx_tuning_candidates_applied ON tuning_candidates(applied_at);
```

---

## Dataclass Definition (Expected)

```python
@dataclass
class TuningSession:
    id: Optional[int] = None
    session_id: str = ""
    robot_id: str = ""
    started_at: float = 0.0
    ended_at: Optional[float] = None
    status: str = "active"
    baseline_config_json: str = "{}"
    hypothesis: str = ""
    forbidden_moves_json: str = "[]"
    verdict: Optional[str] = None
    notes: str = ""
    created_by: str = "codex"

@dataclass
class TuningCandidate:
    id: Optional[int] = None
    session_id: str = ""
    candidate_index: int = 0
    applied_at: float = 0.0
    config_json: str = "{}"
    metrics_json: str = "{}"
    rating: Optional[str] = None
    notes: str = ""
```

---

## Migration Safety Requirements

1. **Forward Migration:**
   - Tables created with `IF NOT EXISTS`
   - No modifications to existing tables
   - Indexes created with `IF NOT EXISTS`

2. **Backward Migration (Rollback):**
   ```sql
   DROP TABLE IF EXISTS tuning_candidates;
   DROP TABLE IF EXISTS tuning_sessions;
   ```

3. **Data Preservation:**
   - Existing `checkpoints` table unaffected
   - Existing `telemetry_snapshots` table unaffected
   - No foreign key constraints to existing tables

---

## Verification Checklist

- [ ] Table `tuning_sessions` created successfully
- [ ] Table `tuning_candidates` created successfully
- [ ] All indexes created
- [ ] Foreign key constraint enforced (CASCADE delete)
- [ ] Dataclass `TuningSession` matches schema
- [ ] Dataclass `TuningCandidate` matches schema
- [ ] Migration up test passes
- [ ] Migration down test passes (rollback)
- [ ] Existing tests remain green
- [ ] No modifications to existing tables

---

## References

- MILESTONE_M1.md (lines 36-37, 49-51)
- TUNING_INTELLIGENCE_PRD.md (F1-F5, lines 70-75)
- docs/OWNERSHIP_BOUNDARIES.md (seed/version lock requirements)


# Milestone M1: Foundation (Weeks 1-3)

**Definition:** Minimum Viable First Milestone per Codex recommendation  
**Scope:** Phases 0, 0.5, 1, 2, 3 + traceability plumbing + shadow mode  
**Exit Gate:** All criteria pass → proceed to Phases 4-6.5

---

## M1 Scope

### Included Phases
| Phase | Name | Deliverables |
|-------|------|--------------|
| 0 | Pre-work | Feature flag, migration strategy, rollback docs |
| 0.5 | Metrology | Uncertainty budget, jitter characterization |
| 1 | Session + Traceability | TuningSession dataclass, provenance table, start/compare/end tools |
| 2 | Step Response | Real settling time, overshoot from telemetry |
| 3 | D-Term Effectiveness | Noise rejection measurement |

### Traceability Plumbing (From Phase 10)
- `artifact_provenance` table in SQLite
- run_id, commit_sha, firmware_version on every artifact
- Forward/backward migration verification test

### Shadow Mode
- New system logs recommendations but **does not apply** them
- Side-by-side comparison: new recommendation vs current policy
- No autonomous changes to robot

---

## M1 Exit Criteria

### Functional
- [ ] Feature flag `TUNING_V2_ENABLED` toggles new behavior
- [ ] `TuningSession` dataclass stores baseline + candidates
- [ ] `start_tuning_session` tool creates session in DB
- [ ] `compare_to_baseline` tool computes real metrics
- [ ] `end_tuning_session` tool finalizes with verdict
- [ ] Step response extracts settling_time, overshoot from telemetry
- [ ] D-term effectiveness computed from real data

### Metrology
- [ ] Uncertainty budget documented (`METROLOGY_BUDGET.md`)
- [ ] Timestamp jitter measured (1000+ samples)
- [ ] Jitter 95th percentile < 10ms

### Traceability
- [ ] `artifact_provenance` table created
- [ ] Every session artifact has run_id, commit_sha
- [ ] Migration up/down test passes

### Regression
- [ ] All existing tuning tests pass
- [ ] Current `tuning_policy.py` behavior unchanged
- [ ] Parity test: shadow recommendation ≈ current recommendation

### Shadow Mode
- [ ] New recommendations logged but not applied
- [ ] Operator can see both recommendations in UI
- [ ] No robot state changes from new system
- [ ] **No `/tooling/tuning/*` behavioral diffs permitted in M1 (shadow-only path)**

---

## M1 Non-Goals

| Excluded | Reason |
|----------|--------|
| Phase 1.5 UI Panel | Can start after M1 backend proven |
| Phases 4-6 | Wait for M1 gate |
| Monte Carlo (Phase 8) | Requires data governance |
| Neural network (Phase 14) | Blocked on data gate |
| Server decomposition | Parallel track, not M1 critical path |

---

## M1 Timeline

### Week 1
| Day | Deliverable | Owner |
|-----|-------------|-------|
| Mon | Phase 0: Feature flag infrastructure | Cascade |
| Tue | Phase 0: Migration strategy document | Cascade |
| Wed | Phase 0: Rollback procedure document | Cascade |
| Thu | Phase 0.5: Metrology budget draft | Cascade |
| Fri | Phase 0.5: Jitter characterization test | Cascade |

### Week 2
| Day | Deliverable | Owner |
|-----|-------------|-------|
| Mon | Phase 1: TuningSession dataclass | Cascade |
| Tue | Phase 1: artifact_provenance table | Cascade |
| Wed | Phase 1: start/compare/end tools | Cascade |
| Thu | Phase 1: Integration test | Cascade |
| Fri | Phase 1: Traceability verification | Cascade |

### Week 3
| Day | Deliverable | Owner |
|-----|-------------|-------|
| Mon | Phase 2: Step response analysis | Cascade |
| Tue | Phase 2: Telemetry extraction | Cascade |
| Wed | Phase 3: D-term effectiveness | Cascade |
| Thu | Shadow mode integration | Cascade |
| Fri | **M1 Gate Review** | Codex |

---

## M1 Gate Review Protocol

### Review Artifacts
1. All exit criteria checkboxes
2. Test run output (pytest results)
3. Shadow mode comparison log (10+ sessions)
4. Metrology budget document
5. Jitter histogram

### Gate Decision
| Outcome | Action |
|---------|--------|
| **PASS** | Proceed to Phases 4-6.5 |
| **PARTIAL** | Fix gaps, re-review in 2 days |
| **FAIL** | Halt, root cause analysis, replan |

### Escalation
If M1 fails, do not proceed to aerospace/ML phases.
Return to foundation work until gate passes.

---

## Rollback Plan

### If M1 Must Be Reverted
1. Set `TUNING_V2_ENABLED=false`
2. Git revert M1 commits
3. Drop new tables: `DROP TABLE tuning_sessions; DROP TABLE artifact_provenance;`
4. Existing system continues unchanged

### Rollback Trigger
- Regression in existing tuning behavior
- Shadow mode shows divergent/unsafe recommendations
- Critical bug in new session logic

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Existing test pass rate | 100% | pytest output |
| Shadow recommendation correlation | >80% match | Log analysis |
| Jitter 95th percentile | <10ms | Histogram |
| Session creation success | 100% | Integration test |
| Traceability coverage | 100% artifacts have provenance | DB query |

---

## Ready to Start

All Codex blockers addressed:
- [x] Traceability moved to Phase 1
- [x] Metrology phase added (0.5)
- [x] Deterministic replay policy defined
- [x] Ownership boundaries frozen

**M1 is ready to begin when you approve.**

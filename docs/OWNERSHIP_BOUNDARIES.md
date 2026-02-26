# Agent Ownership Boundaries (Frozen)

**Date:** 2026-02-25  
**Status:** FROZEN per Codex review requirement  
**Authority:** Any boundary change requires explicit user + Codex approval

---

## Cascade (Windsurf) — Primary Implementation

### Owns (Exclusive)
| Area | Reason |
|------|--------|
| Phases 0, 0.5, 1 (backend), 2-6, 6.5 | Core tuning logic, deep context required |
| Phases 7-13, 13.5, 14-16 | Aerospace verification, ML implementation |
| `tuning_policy.py` modifications | Safety-adjacent, recommendation semantics |
| `/tooling/tuning/*` endpoints | Recommendation quality gate logic |
| Safety invariant definitions | Critical, cannot delegate |
| Migration logic (DB schema) | Session/audit consistency |
| Deterministic replay harness | Seed/version policy enforcement |

### Coordinates With
| Area | Coordination Model |
|------|-------------------|
| Phase 1.5 UI Panel | Cascade defines API contract → Augment implements |
| Server decomposition | Cascade reviews PRs, validates parity tests |

---

## Augment — Implementation Support

### Owns (Delegated)
| Area | Constraints |
|------|-------------|
| Route extraction scaffolding | NO behavior changes |
| Module boundary creation | Mechanical moves only |
| Import reorganization | Must pass existing tests |
| `TuningSessionPanel.tsx` | Follow API contract from Cascade |
| `BaselineComparisonCard.tsx` | Use existing dark theme |
| `CandidateHistoryList.tsx` | Use strings.ts for copy |
| `ForbiddenMovesBadges.tsx` | Follow CodexPanel patterns |
| Test fixture generation | Follow spec from Cascade |
| Documentation updates | Factual updates only |
| Golden trace capture | Use defined protocol |

### Does NOT Own (Augment mechanical/refactor tracks)
| Area | Reason |
|------|--------|
| Migration logic | Consistency-critical (Cascade-owned) |
| API endpoint design | Cascade defines contracts |
| Backend session logic | Cascade-only |
| Safety-related UI states | Cascade specifies exact behavior |
| Test logic/tolerance changes without approval | Regression risk / false confidence |
| Any Python/firmware behavior changes | Out of scope for Augment tracks |

### Exit Criteria (Augment #1: server mechanical extraction)
- Existing tests pass
- Cascade parity review approved
- No functional diff in HTTP responses

### Exit Criteria (Augment #2: UI implementation)
- UI matches API contract
- UI tests pass
- Cascade UX review approved

---

## Codex — Governance & Validation

### Owns (Exclusive)
| Area | Reason |
|------|--------|
| Acceptance contract authoring | Phase exit criteria + pass/fail schemas |
| Regression gate definition | Golden traces + tolerances |
| Risk burn-down governance | Weekly go/no-go across tracks |
| Integration adjudication | When tracks conflict |
| Plan review authority | Final approval on phase changes |

### Escalation Path
1. Agent encounters ambiguity → escalate to Codex
2. Codex reviews and rules
3. Decision logged in this document

---

## Stochastic Phase Policy (Codex Blocker)

For Phases 8 (Monte Carlo), 14-16 (ML):

### Seed/Version Lock Requirements
```
Every stochastic run MUST record:
- random_seed: int
- numpy_seed: int  
- torch_seed: int (if applicable)
- firmware_version: str
- model_version: str (semver)
- commit_sha: str
- run_id: uuid
```

### Replay Guarantee
- Any run must be reproducible from recorded seeds
- Test: `replay(run_id) == original_result` assertion required

### Version Policy
- Model versions use semver: `tuning_model_v1.0.0.pkl`
- Breaking changes = major version bump
- New features = minor version bump
- Bug fixes = patch version bump

---

## Metrology Phase (0.5) Requirements (Codex Blocker)

Before Phase 2 metrics are treated as truth:

### Measurement Uncertainty Budget
| Metric | Source | Uncertainty | Action |
|--------|--------|-------------|--------|
| Angle (deg) | IMU | ±0.5° | Kalman R_measure |
| Timestamp | Host clock | ±2ms | Characterize jitter |
| Gyro (dps) | IMU | ±1 dps | Calibration |
| PWM output | Firmware | Exact | N/A |

### Timestamp Jitter Characterization
- Measure host_ts vs firmware ms delta distribution
- Document 95th percentile jitter
- Define acceptable jitter threshold for step response analysis

### Deliverable
- `docs/METROLOGY_BUDGET.md` with uncertainty table
- Test: jitter histogram from 1000+ samples
- Gate: must complete before Phase 2 metrics are used

---

## Data Governance Gate (13.5) Requirements (Codex Blocker)

Before Phase 14 (Neural Network) starts:

### Data Readiness Checklist
- [ ] Labeling SOP documented
- [ ] Label quality audit (10% sample review)
- [ ] Minimum dataset size: 500+ labeled sessions
- [ ] Cross-surface/cross-battery stratification verified
- [ ] Drift/OOD detection policy defined
- [ ] Train/val/test split documented (no leakage)

### Gate Criteria
- All checkboxes complete
- Codex approval on labeling SOP
- Audit shows <5% label disagreement

### If Gate Fails
- Phase 14 does not start
- Return to data collection
- Re-audit when 500+ sessions reached

---

## Change Log

| Date | Change | Approved By |
|------|--------|-------------|
| 2026-02-25 | Initial frozen boundaries | User + Codex |
| 2026-02-25 | Consolidated Augment #1/#2/#3 into single Augment agent; tightened "Does NOT Own" scope headings; split exit criteria per track | Codex — MC-2026-0225-001 |

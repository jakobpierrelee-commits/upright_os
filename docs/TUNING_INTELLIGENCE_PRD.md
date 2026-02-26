# Tuning Intelligence System PRD + Scorecard

A 16-phase upgrade to transform the UpRight.os tuning system into an aerospace-grade, ML-powered tuning intelligence platform with verifiable proof artifacts.

---

## 0) Program Snapshot

- Program name: `Tuning Intelligence System`
- Owner: `Codex + JVKE`
- Created: `2026-02-25`
- Predecessor: `docs/SKILLS_TUNABILITY_SCORECARD.md` (Gate B: Closed-Loop Tuning)
- Current state: `PLANNING`
- Target completion: `All 16 phases with validation gates`

### Definition of Done

The system is complete when:
- A) Session-based tuning with baseline comparison is operational
- B) Real telemetry metrics (step response, D-term effectiveness, noise floor) replace simulated/placeholder values
- C) Aerospace-grade verification artifacts are generated and pass gates
- D) Neural network model is trained and outperforms decision tree on holdout data
- E) All proof artifacts are machine-readable, timestamped, and queryable

---

## 1) Priority Objectives

| Priority | Objective |
|----------|-----------|
| `P0` | Baseline/candidate A/B comparison with session state |
| `P0` | Real step response metrics from burst captures |
| `P0` | D-term effectiveness ratio (noise vs signal diagnosis) |
| `P0` | Computed noise floor spectrum (replace -45 dB placeholder) |
| `P1` | Session continuity with hypothesis tracking and forbidden moves |
| `P1` | Multi-variable interaction handling (decision tree) |
| `P1` | Stability margin analysis (gain/phase margin) |
| `P1` | Monte Carlo robustness validation |
| `P2` | Regression test suite with golden traces |
| `P2` | Configuration traceability (audit trail) |
| `P2` | Fault injection testing |
| `P2` | Safety invariant enforcement |
| `P2` | HIL validation gate |
| `P3` | Neural network tuning model |
| `P3` | Multiple tuning rule comparison |
| `P3` | FOPDT model identification |

Rule: No `P1+` work begins until `P0` phases pass validation gates.

---

## 2) Research Sources Integrated

| Source | Star Count | What We're Taking |
|--------|------------|-------------------|
| FPVtune (Betaflight) | — | Step response, D-term effectiveness, noise floor, neural network |
| hirschmann/pid-autotune | 200+ | A/B comparison, multiple tuning rules (Z-N, Tyreus-Luyben, Cohen-Coon) |
| arduino-pid-autotuner | 150+ | Ziegler-Nichols modes (basic, less overshoot, no overshoot) |
| TCLab/APMonitor | Academic | FOPDT model identification, IMC tuning correlations |
| Aerospace/SpaceX standards | — | Stability margins, Monte Carlo, regression, traceability, fault injection, invariants, HIL |

---

## 3) Gate Structure

### Gate F: Foundation (Phases 1-6) — Weight: 40

| ID | Requirement | Status | Validation |
|----|-------------|--------|------------|
| F1 | `TuningSession` dataclass in `codex_db.py` | `TODO` | Unit test |
| F2 | `tuning_sessions` SQLite table created | `TODO` | Schema migration test |
| F3 | `start_tuning_session` tool operational | `TODO` | Integration test |
| F4 | `compare_to_baseline` tool returns delta metrics | `TODO` | Unit test with mock data |
| F5 | `evaluate_tuning_plan()` accepts optional `baseline` param | `TODO` | Backward compat test |
| F6 | Step response analysis from real burst captures | `TODO` | Test with fixture burst |
| F7 | D-term effectiveness ratio computed | `TODO` | Unit test with noisy/clean data |
| F8 | Noise floor spectrum computed (not placeholder) | `TODO` | FFT validation test |
| F9 | Session continuity persists across restarts | `TODO` | SQLite persistence test |
| F10 | Forbidden moves filter applied to recommendations | `TODO` | Unit test |
| F11 | Decision tree handles compound symptoms | `TODO` | Multi-condition test cases |

Gate F status: `TODO`
Gate F score: `0 / 40`

---

### Gate A: Aerospace Verification (Phases 7-13) — Weight: 35

| ID | Requirement | Status | Validation |
|----|-------------|--------|------------|
| A1 | `compute_stability_margins()` returns gain/phase margin | `TODO` | Compare to scipy.signal |
| A2 | Stability margin < threshold blocks recommendation | `TODO` | Gate enforcement test |
| A3 | `run_monte_carlo_validation()` with N=100 runs | `TODO` | Statistical pass rate test |
| A4 | Monte Carlo pass_rate >= 0.95 required | `TODO` | Threshold enforcement |
| A5 | Golden trace regression suite created | `TODO` | At least 5 golden traces |
| A6 | `run_tuning_regression()` compares to golden outputs | `TODO` | Exact/bounded delta match |
| A7 | `tuning_audit_trail.json` append-only log | `TODO` | Immutability test |
| A8 | Change requires `change_request_id` link | `TODO` | Traceability query |
| A9 | `inject_fault()` tool with 3+ fault modes | `TODO` | Graceful degradation test |
| A10 | Safety invariants defined and enforced | `TODO` | Violation logging test |
| A11 | HIL validation gate blocks `SAVECFG` on failure | `TODO` | Integration test |

Gate A status: `TODO`
Gate A score: `0 / 35`

---

### Gate M: ML-Powered (Phases 14-16) — Weight: 25

| ID | Requirement | Status | Validation |
|----|-------------|--------|------------|
| M1 | Training data collection integrated with Phase 5 | `TODO` | Feature + label logging |
| M2 | >= 500 labeled sessions accumulated | `TODO` | Dataset size check |
| M3 | `train_tuning_model()` produces model artifact | `TODO` | Model file exists |
| M4 | Cross-validation accuracy > decision tree baseline | `TODO` | Holdout comparison |
| M5 | `predict_optimal_gains()` returns recommendations | `TODO` | Inference test |
| M6 | Confidence gating: fallback to decision tree if < 0.7 | `TODO` | Low-confidence test |
| M7 | `compare_tuning_rules()` shows 6+ methods side-by-side | `TODO` | Output format test |
| M8 | `identify_fopdt_model()` fits K, tau, theta | `TODO` | Fit quality r² > 0.9 |
| M9 | FOPDT feeds Cohen-Coon and IMC rules | `TODO` | Integration test |

Gate M status: `TODO`
Gate M score: `0 / 25`

---

## 4) Proof Artifacts

Every gate produces machine-readable, timestamped, signed artifacts:

| Artifact | Gate | Contents |
|----------|------|----------|
| `session_state.json` | F | Baseline, candidates, hypothesis, forbidden moves |
| `step_response_report.json` | F | delay_ms, rise_time_ms, overshoot_pct, settle_time_ms |
| `d_term_effectiveness.json` | F | ratio, diagnosis, d_noise_rms, d_signal_rms |
| `noise_floor_report.json` | F | noise_floor_db, noise_band_hz, noise_energy_ratio |
| `stability_margin_report.json` | A | gain_margin_db, phase_margin_deg, stable |
| `monte_carlo_report.json` | A | pass_rate, failures, confidence_interval |
| `regression_results.json` | A | per-case pass/fail, delta values |
| `tuning_audit_trail.json` | A | Immutable append-only change log |
| `fault_injection_report.json` | A | fault_type, duration, outcome |
| `invariant_violations.json` | A | Empty if safe, detailed if not |
| `hil_validation_report.json` | A | model_version, simulation outputs |
| `model_training_report.json` | M | accuracy, confusion_matrix, feature_importance |
| `tuning_rules_comparison.json` | M | Per-rule Kp/Ki/Kd recommendations |
| `fopdt_model.json` | M | K, tau_ms, theta_ms, fit_quality |

All artifacts:
- JSON format
- SHA256 content hash
- ISO 8601 timestamp
- Queryable via `codex_db`

---

## 5) Implementation Phases

| Phase | Name | Files Modified | Test File |
|-------|------|----------------|-----------|
| 1 | Baseline/Candidate A/B | `codex_db.py`, `codex_tools.py` | `test_tuning_session_lifecycle.py` |
| 1.5 | UI Panel | `TuningSessionPanel.tsx` | `TuningSessionPanel.test.tsx` |
| 2 | Step Response Analysis | `codex_tools.py`, `tuning_policy.py` | `test_step_response_analysis.py` |
| 3 | D-Term Effectiveness | `codex_tools.py`, `tuning_policy.py` | `test_d_effectiveness.py` |
| 4 | Noise Floor Spectrum | `codex_tools.py` | `test_noise_floor.py` |
| 5 | Session Continuity | `codex_db.py`, `codex_tools.py`, `tuning_policy.py` | `test_session_continuity.py` |
| 6 | Multi-Variable Handling | `tuning_policy.py`, `tuning_decision_tree.py` | `test_decision_tree.py` |
| 7 | Stability Margins | `codex_tools.py` | `test_stability_margins.py` |
| 8 | Monte Carlo | `codex_tools.py` | `test_monte_carlo.py` |
| 9 | Regression Suite | `tuning_regression_suite/`, `codex_tools.py` | `test_regression_suite.py` |
| 10 | Config Traceability | `codex_db.py`, `codex_tools.py` | `test_audit_trail.py` |
| 11 | Fault Injection | `codex_tools.py` | `test_fault_injection.py` |
| 12 | Safety Invariants | `codex_tools.py`, `tuning_policy.py` | `test_invariants.py` |
| 13 | HIL Validation | `codex_tools.py` | `test_hil_gate.py` |
| 14 | Neural Network | `tuning_model.py`, `codex_tools.py` | `test_tuning_model.py` |
| 15 | Multi-Rule Comparison | `codex_tools.py` | `test_rule_comparison.py` |
| 16 | FOPDT Model | `codex_tools.py` | `test_fopdt.py` |

---

## 6) Hard Guardrails

1. **Backward Compatibility:** Existing tests must remain green at every phase
2. **New Tables Only:** `tuning_sessions` + `artifact_provenance` tables added; no modifications to existing tables
3. **Optional Parameters:** New parameters to `evaluate_tuning_plan()` are optional with defaults
4. **No Code Without Tests:** Every new function has a unit test
5. **Proof Artifacts Required:** Every gate produces its specified artifacts
6. **No Silent Failures:** All tool failures logged with explicit error cause

---

## 7) Validation Commands

```bash
# Run all tuning tests
pytest app/bridge/tests/test_tuning_*.py -v

# Run specific phase tests
pytest app/bridge/tests/test_tuning_session_lifecycle.py -v  # Phase 1
pytest app/bridge/tests/test_step_response_analysis.py -v   # Phase 2
pytest app/bridge/tests/test_d_effectiveness.py -v          # Phase 3

# Run regression suite
python -m app.bridge.tools.run_tuning_regression --golden-dir tuning_regression_suite/

# Run Monte Carlo validation
python -m app.bridge.tools.run_monte_carlo --n-runs 100 --output monte_carlo_report.json

# Verify audit trail integrity
python -m app.bridge.tools.verify_audit_trail --file tuning_audit_trail.json
```

---

## 8) Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Session A/B comparison accuracy | 100% delta correctness | Unit test |
| Step response extraction | ±5ms delay, ±2% overshoot | Fixture comparison |
| D-term effectiveness diagnosis | 95% agreement with manual label | Labeled test set |
| Monte Carlo pass rate | >= 95% across parameter envelope | Statistical test |
| Regression suite | 0 regressions on golden traces | Exact match |
| Neural network vs decision tree | +10% improvement on holdout | A/B comparison |
| Audit trail completeness | 100% of changes traced | Query coverage |

---

## 9) Risks and Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Insufficient labeled data for NN | High | Phase 14 delayed | Collect aggressively in Phase 5 |
| FOPDT fit quality low for nonlinear system | Medium | Phase 16 limited | Use piecewise linearization |
| Monte Carlo too slow (100 runs) | Low | UX impact | Parallel execution, caching |
| HIL model diverges from real hardware | Medium | False confidence | Periodic model validation |

---

## 10) Codex Evaluation Prompt

**For Codex to evaluate this PRD:**

```
Review this Tuning Intelligence System PRD and answer:

1. Are the 16 phases correctly ordered for dependency management?
2. Are there any missing requirements for aerospace-grade verification?
3. Is the neural network architecture appropriate for this use case?
4. Are the proof artifacts sufficient for external audit?
5. What risks are not addressed?
6. What would you add to make this truly SpaceX-adjacent?

Be specific and cite research if available.
```

---

## 11) Operational Readiness Additions

### Phase 0: Pre-Work (Before Phase 1)

| ID | Requirement | Status |
|----|-------------|--------|
| O1 | Feature flag infrastructure (`TUNING_V2_ENABLED` env var) | `TODO` |
| O2 | Database migration strategy (forward/backward compat) | `TODO` |
| O3 | Rollback procedure documented | `TODO` |

### Cross-Cutting: Testing Infrastructure

| ID | Requirement | Status |
|----|-------------|--------|
| T1 | Integration test suite for full tuning flows | `TODO` |
| T2 | Performance benchmark baseline (latency, memory) | `TODO` |
| T3 | Hardware-in-loop test protocol defined | `TODO` |
| T4 | Golden trace fixtures versioned with firmware | `TODO` |

### Phase 6.5: Performance Validation

| ID | Requirement | Status |
|----|-------------|--------|
| P1 | Measure tuning policy latency (target < 50ms) | `TODO` |
| P2 | Measure SQLite query performance under load | `TODO` |
| P3 | Memory profiling for session accumulation | `TODO` |

### Phase 14.5: Model Lifecycle

| ID | Requirement | Status |
|----|-------------|--------|
| ML1 | Model versioning scheme (semver for tuning_model.pkl) | `TODO` |
| ML2 | Model rollback procedure | `TODO` |
| ML3 | A/B test infrastructure (model vs decision tree) | `TODO` |
| ML4 | Retraining trigger criteria defined | `TODO` |

### Canary Deployment Strategy

1. **Single-robot canary:** New tuning logic runs on test bot only
2. **Shadow mode:** New system logs recommendations but doesn't apply
3. **Gradual rollout:** Feature flag percentage (10% → 50% → 100%)
4. **Automatic rollback:** If error rate > threshold, disable flag

### Operator Training

| Material | Status |
|----------|--------|
| Tuning Session Panel walkthrough video | `TODO` |
| Updated TUNING_STAGE_TRACKER with new fields | `TODO` |
| Quick reference card for new metrics | `TODO` |

---

## 12) Updated Phase Order (With Codex Review Blockers Addressed)

| Phase | Name | Type | Notes |
|-------|------|------|-------|
| **0** | **Pre-work (flags, migration, rollback)** | **Ops** | |
| **0.5** | **Metrology & Uncertainty** | **Ops** | **NEW: Codex blocker** |
| 1 | Baseline/Candidate A/B + Traceability Plumbing | Feature | **Traceability moved here** |
| 1.5 | UI Panel | Feature | |
| 2 | Step Response Analysis | Feature | |
| 3 | D-Term Effectiveness | Feature | |
| 4 | Noise Floor Spectrum | Feature | |
| 5 | Session Continuity | Feature | |
| 6 | Multi-Variable Handling | Feature | |
| **6.5** | **Performance Validation + Soak Tests** | **Ops** | **Added: reliability SLOs** |
| 7 | Stability Margins | Feature | |
| 8 | Monte Carlo Testing | Feature | **Requires seed/version policy** |
| 9 | Regression Suite | Feature | **Continuous, not phase-gated** |
| 10 | Config Traceability (full) | Feature | Plumbing done in Phase 1 |
| 11 | Fault Injection | Feature | Isolated environment only |
| 12 | Safety Invariants | Feature | |
| 13 | HIL Validation Gate | Feature | |
| **13.5** | **Data Governance Gate** | **Ops** | **NEW: Codex blocker** |
| 14 | Neural Network Model | Feature | Only if data gate passes |
| **14.5** | **Model Lifecycle** | **Ops** | |
| 15 | Multi-Rule Comparison | Feature | |
| 16 | FOPDT Model ID | Feature |

---

## 13) Change Log

| Date | Author | Change |
|------|--------|--------|
| 2026-02-25 | Cascade | Initial PRD created from research synthesis |
| 2026-02-25 | Cascade | Added operational readiness phases (0, 6.5, 14.5) |
| 2026-02-25 | Cascade | Codex review: Added 0.5 (Metrology), 13.5 (Data Gov), moved traceability to Phase 1 |

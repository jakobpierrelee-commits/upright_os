# Pending Decisions

**Owner:** JVKE (Mission Command)
**Managed by:** JVKE + Codex (manual governance)
**Check this file at the start of every session.**

**This file is the primary manual stop-point queue.**

Any blocker requiring approval, clarification, rejection, or escalation must be logged here immediately.
Clear the row once resolved and log the outcome in `docs/MULTI_AGENT_SIGNOFF_LEDGER.md`.

---

## Open Items

| # | Date | Agent | Block | Decision Needed | Deadline | Status |
|---|---|---|---|---|---|---|
| 3 | 2026-02-25 | Augment | MC-2026-0225-007 validation | Codex-Execution Phase 1 schema diverges from Augment verification contracts: tuning_sessions missing 5 columns (session_id, started_at, ended_at, baseline_config_json, hypothesis, forbidden_moves_json, verdict, created_by), artifact_provenance missing 9 columns (artifact_id, run_id, commit_sha, firmware_version, model_version, random_seed, numpy_seed, torch_seed, parent_artifact_id). Options: (A) Request Codex align with full contract, (B) Approve minimal schema as Phase 1 foundation with explicit Phase 2 extension plan, (C) Revise contract to match minimal implementation. Recommendation: (B) if minimal schema supports M1 exit criteria, else (A). | ASAP | RESOLVED — MC-2026-0226-001 |
| 4 | 2026-02-26 | Augment | MC-2026-0225-008 plan validation | Codex Phase 1B plan has column naming divergence from Augment contract v1: session_uid vs session_id, artifact_uid vs artifact_id, supersedes_artifact_id vs parent_artifact_id; missing contract columns: baseline_config_json, hypothesis, forbidden_moves_json, verdict, created_by (tuning_sessions), commit_sha, model_version, random_seed, numpy_seed, torch_seed (artifact_provenance). Migration safety PASS (additive-only, rollback coverage). Options: (A) Request Codex align Phase 1B names/columns with contract v1, (B) Approve Phase 1B as pragmatic evolution with explicit contract revision. Recommendation: (A) for semantic consistency, else (B) with contract update. | ASAP | RESOLVED — MC-2026-0226-002 |
| 5 | 2026-02-26 | Mission Command | PRD §7.2 tooling gate check | Required architecture-gate tools are missing at canonical paths: `tools/lean/check_dependency_matrix.py`, `tools/lean/check_import_boundaries.py`, `tools/lean/check_contract_drift.py`. Decide whether to (A) assign immediate implementation in Foundation Lock and keep HOLD, or (B) amend PRD gating contract. Recommendation: (A). | ASAP | RESOLVED — MC-2026-0226-004 |
| 6 | 2026-02-26 | Mission Command | PRD §7.1 command #4 gate failure (`./tools/lean/ci_clean_lane.sh`) | Baseline clean-lane check fails after static checks due module-size guardrails: `app/bridge/server.py` max function length 4674 > 4500 and `app/ui/ops-console/src/styles.css` line count 9018 > 9000. Decide whether to (A) run scoped debt-reduction pass to satisfy current limits, or (B) approve temporary guardrail exception with owner/timebox. Recommendation: (A) unless Mission Command explicitly grants exception. | ASAP | RESOLVED — MC-2026-0226-006 |
| 7 | 2026-02-26 | Cascade | PRD Phase A exit approval | Phase A execution artifacts are now complete: `docs/DOMAIN_MAP.md` present, dependency matrix/schema present, restart queue + slice order frozen in PRD §8.2, regression gate pack locked in PRD §8.3, and pinned commands (1)-(4) pass (`check_dependency_matrix`, `check_import_boundaries`, `check_contract_drift`, `ci_clean_lane`). Request Mission Command ruling: (A) approve Phase A complete and log decision ID, or (B) hold with explicit missing criteria. Recommendation: (A). | ASAP | RESOLVED — MC-2026-0226-008 |

---

## How Agents Use This File

When blocked, append a row using this format:

```
| <#> | <YYYY-MM-DD> | <Agent> | <M1-A|M1-B|M1-C> | <one-line description of what needs deciding> | <deadline or ASAP> | OPEN |
```

Rules:
- Submit the row at the exact stop-point where progress requires a ruling.
- Do NOT write vague entries. One sentence must be enough for JVKE to understand the blocker.
- Add a short options summary in the same commit or handoff note (A/B/C + recommendation).
- Once JVKE resolves it, update Status to `RESOLVED — MC-###` and move outcome to the ledger.
- If an assignment is intended for a different agent, do not execute it. Mark it as `MISROUTED_ASSIGNMENT`, notify Mission Command, and wait for corrected routing.

---

## Resolved Items

| # | Date | Agent | Decision | Resolved By | Decision ID |
|---|---|---|---|---|---|
| 1 | 2026-02-25 | JVKE | Consolidate Augment #1/#2/#3 into single Augment agent | Codex | MC-2026-0225-001 |
| 2 | 2026-02-25 | Augment | Task clarified: Augment authorized for verification-only work on Codex-Execution Phase 1 schema (no implementation) | JVKE | MC-2026-0225-002 |
| 3 | 2026-02-26 | Augment | Approved Option B: keep minimal Phase 1A schema as foundation; require explicit Phase 1B extension and compatibility verification before resume | JVKE | MC-2026-0226-001 |
| 4 | 2026-02-26 | Augment | Approved Option A: align Phase 1B naming and column plan to contract v1 semantics before implementation | JVKE | MC-2026-0226-002 |
| 5 | 2026-02-26 | Mission Command | Approved implementation of PRD §7.2 tooling artifacts and command set (1)-(3) verification | JVKE | MC-2026-0226-004 |
| 6 | 2026-02-26 | Mission Command | Approved timeboxed exception for module-size guardrails; `ci_clean_lane.sh` passed with updated exception caps and explicit remediation deadlines | JVKE | MC-2026-0226-006 |
| 7 | 2026-02-26 | Mission Command | Approved Option A: Phase A complete; proceed to Phase B Slice 1 under locked queue/gate pack and self-resolve-first model | JVKE | MC-2026-0226-008 |

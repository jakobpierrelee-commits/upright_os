# Decision Log

Purpose: capture important architecture/process choices so execution stays consistent and we avoid repeated re-debates.

Last updated: `2026-02-23`
Owner: `Codex + JVKE`

Status values: `Accepted`, `Superseded`, `Proposed`

## Decisions

### D-001

- Date: `2026-02-22`
- Status: `Accepted`
- Decision: Lock clean lane to local bridge endpoint (`127.0.0.1:8797`) and fail closed on contract mismatch.
- Why: Prevent accidental legacy-path usage and reduce drift.
- Impact: Faster diagnosis, clearer operator failure modes.
- Links: `docs/OVERHAUL_SPRINT_SCORECARD.md` (`#5`, `#20`)

### D-002

- Date: `2026-02-22`
- Status: `Accepted`
- Decision: Use fail-closed manifest/profile/pre-arm safety gates before arm-critical actions.
- Why: Safety and deterministic bring-up are non-negotiable.
- Impact: More explicit blocks up front, fewer unsafe runtime states.
- Links: `docs/OVERHAUL_SPRINT_SCORECARD.md` (`#5`, `#21`)

### D-003

- Date: `2026-02-22`
- Status: `Accepted`
- Decision: Clean chat runtime prioritizes Codex CLI session auth over API-key-only paths for the clean lane.
- Why: Align execution behavior with desired IDE/Codex experience.
- Impact: Login-state checks are first-class in clean endpoints.
- Links: `docs/OVERHAUL_SPRINT_SCORECARD.md` (`#2`, `#26`)

### D-004

- Date: `2026-02-23`
- Status: `Accepted`
- Decision: Refactor in thin vertical slices with no endpoint contract changes.
- Why: Keep hardware/operator workflows running while reducing monolith risk.
- Impact: New modules added incrementally; tests/CI expanded per slice.
- Links: `docs/OVERHAUL_SPRINT_SCORECARD.md` (`#26`, `#27`, `#29`, `#30`)

### D-005

- Date: `2026-02-23`
- Status: `Accepted`
- Decision: Keep live clean-gate CI execution opt-in (`RUN_LIVE_CLEAN_GATES=1`), while static/contract checks always run.
- Why: Hosted CI environments are variable for hardware/login dependencies.
- Impact: Reliable baseline CI plus explicit live-gate trigger when needed.
- Links: `docs/OVERHAUL_SPRINT_SCORECARD.md` (`#2`, `#20`, `#30`)

### D-006

- Date: `2026-02-23`
- Status: `Accepted`
- Decision: Use scorecard as source of truth, with stage/risk/decision companions.
- Why: Scorecard alone tracks completion but not sequencing/risk rationale.
- Impact: Better planning discipline and faster unblock decisions.
- Links: `docs/STAGE_PLAN.md`, `docs/RISK_REGISTER.md`, `docs/OVERHAUL_SPRINT_SCORECARD.md`

### D-007

- Date: `2026-02-23`
- Status: `Accepted`
- Decision: Add a one-page change proposal gate (`docs/CHANGE_PROPOSAL_TEMPLATE.md`) before non-trivial scope adds or architecture changes.
- Why: Enforce requirement ownership, delete-first scrutiny, fail-closed design, and test-backed acceptance before coding.
- Impact: Fewer speculative modules, clearer tradeoffs, and stronger execution discipline.
- Links: `docs/CHANGE_PROPOSAL_TEMPLATE.md`, `docs/STAGE_PLAN.md`

### D-008

- Date: `2026-02-24`
- Status: `Accepted`
- Decision: Treat `docs/assistant_knowledge/` as canonical, versioned tuning memory with explicit supersession rules (`v1.2` active).
- Why: Preserve high-quality learning across sessions while allowing guidance to evolve with new evidence.
- Impact: Tuning guidance changes are auditable, updateable, and tied to run evidence; stale assumptions are less likely to persist.
- Links: `docs/assistant_knowledge/manifest.json`, `docs/assistant_knowledge/knowledge_governance_v1.0.md`, `docs/SKILLS_TUNABILITY_SCORECARD.md`

## Update Rules

1. Any new architecture/process choice that changes execution path gets a decision entry.
2. If a decision is replaced, set old entry to `Superseded` and add successor reference.
3. Keep entries short and tied to scorecard items.

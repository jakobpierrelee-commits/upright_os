# Skills + Tunability Scorecard

Purpose: drive this program to one outcome only: a robot that can balance autonomously and be tuned with trustworthy evidence.

Scope boundary:
- Starts after `docs/OVERHAUL_SPRINT_SCORECARD.md` closure.
- This scorecard is complete only when a bot is successfully tuned under repeatable, safety-valid conditions.

---

## 0) Program Snapshot

- Program name: `Skills + Tunability Validation`
- Owner: `Codex + JVKE`
- Last updated: `2026-02-24`
- Active hardware mode: `single_bot_test` (no required profile-selection UX for this bot)
- Active hardware profile: `test_bot_balance_mvp_v1` (`TEST BOT - Balance MVP v1`)
- Current scoring state: `FROZEN` (displayed legacy score `24 / 100` retained for audit only)
- Why frozen: event/capture validity must pass before any tuning-lift score is trusted.

Definition of done (program complete):
- A) Evidence integrity gate is green (valid fall/runaway characterization, low invalid-window rate).
- B) Closed-loop tuning gate is green (objective improvement from bounded deltas).
- C) Balance acceptance passes: bot maintains autonomous upright windows with minimal/no rescue input across repeat runs.

---

## 1) Priority Objectives (Reassessed)

1. `P0` Prove we can actually balance the robot autonomously.
2. `P0` Ensure falls/runaways are characterized from correct variables and valid capture windows.
3. `P0` Harden tuning UX so invalid/assisted runs cannot silently pollute decisions.
3. `P1` Tune only after A/B evidence is valid (single-variable changes only).
4. `P1` Preserve fail-closed safety and prearm discipline during all tuning runs.
5. `P2` Improve operator efficiency after tuning validity is stable.
6. `P2` Keep this bot in `single_bot_test` mode to avoid premature profile workflow complexity.

Rule:
- No section score progression while `P0` objectives are failing.

---

## 2) Gate A: Evidence Integrity (Weight: 45)

Goal: logs must represent real behavior (including fall/runaway onset), not idle windows.

### A1) Event Contract Readiness
- [x] `DONE` Host capture rows include required fields: `fault`, `fault_count`, `runaway`, `wposRaw`, `wdelta`, control outputs.
- [x] `DONE` Summary includes event-contract fields: `fall_detected`, `runaway_detected`, `event_detected`, `data_coherence_ok`, `invalid_window`, `bad_data_incoherent_event`.
- [x] `DONE` Operator outcome labels integrated per run (`fell_forward`, `fell_backward`, `runaway_forward_saved`, `runaway_backward_saved`, `stable_window`) with `operator_assisted` + `run_valid_for_tuning` hard gate.

### A2) Window/Signal Validity
- [ ] `TODO` Invalid-window rate below threshold (`<= 20%` over last 10 runs).
- [ ] `TODO` Incoherent-event rate below threshold (`<= 10%` over last 10 runs).
- [ ] `TODO` Trigger profile consistently captures 2s pre-event + event + post-event behavior.
- [ ] `TODO` Run is rejected from tuning-scoring when event contract flags `invalid_window` or `bad_data_incoherent_event`.

### A3) Operator ↔ Telemetry Agreement
- [ ] `TODO` Forward/backward outcome labels align with event-sign variables (`ang`, `out`, `wposRaw`) at acceptable agreement rate.
- [ ] `TODO` Any mismatch is marked and excluded from scoring until explained.

Gate A status: `IN PROGRESS`
Gate A score: `FROZEN until A2 minimum validity threshold is met`

---

## 3) Gate B: Closed-Loop Tuning Success (Weight: 40)

Goal: objective, repeatable performance lift after bounded tuning deltas.

### B1) Run Pair Validity
- [ ] `TODO` Baseline capture is Gate A-valid.
- [ ] `TODO` Post-change capture is Gate A-valid.
- [ ] `TODO` Baseline/post conditions are matched (surface, battery band, runtime identity, capture settings).

### B2) Bounded Delta Discipline
- [ ] `TODO` One variable change per run (`PID`, `MOTION`, or `LIMITS`; never multi-axis edits in one step).
- [ ] `TODO` Rollback path exists and is logged for each accepted change.

### B3) Objective Improvement
- [ ] `TODO` Stability metrics improve (settle/IAE/peak angle) or remain within tolerance with clear tradeoff.
- [ ] `TODO` Disturbance recovery improves without increased critical fault risk.
- [ ] `TODO` No safety regression (`prearm`, `estop`, fail-closed behavior intact).

Gate B status: `TODO`
Gate B score: `0 / 40` (not yet eligible)

---

## 4) Balance Acceptance Gate (Weight: 15)

Goal: confirm practical balance ability, not just metric movement.

- [ ] `TODO` Autonomous upright hold (short window) with no rescue input.
- [ ] `TODO` Repeat autonomous hold across multiple runs (same tune, same context).
- [ ] `TODO` Disturbance trial: controlled push/release with non-fault recovery at least once.
- [ ] `TODO` Operator reports reduced intervention burden relative to baseline.

Status: `TODO`

---

## 5) Hard Guardrails

- Keep fail-closed safety behavior unchanged.
- No deletion of safety checks to force pass.
- One variable change per tuning run.
- If evidence is insufficient or inconsistent, mark explicitly and stop scoring.
- `FAULT`-ended runs are valid evidence when event-contract checks pass.
- For this bot, keep `single_bot_test` mode active (implicit hardware path, no mandatory profile selection flow).
- Never treat only PID as the full control surface; always evaluate dynamic shapers (slew, engage ramp, saturation, motion terms, gates, filters, anti-windup) before attributing behavior to gains alone.

---

## 6) Current Blocking Findings

1. Multiple runs were operator-observed as fall/runaway, but captures often looked low-signal.
2. This indicates prior window/trigger mismatch or incomplete event characterization, not reliable "stable" proof.
3. Event-contract classifier was added; one run failed due missing `math` import and is invalidated.
4. Bot authority was increased (`LIMITS 170 35`), but recent valid captures still lacked clear high-stress segments.
5. Immediate requirement remains: capture true failure onset reliably, then tune.

---

## 7) Evidence Log (Recent + Relevant)

Core legacy evidence retained:
- `.runlogs/milestone_overhaul_closed_20260224_112923/`
- `.runlogs/prearm_signoff/prearm_signoff_20260224_132013.json`
- `.runlogs/firmware_ops/20260224_140850_upload_guarded_pass.json`

Encoder / observability checks:
- `.runlogs/encoder_checks/check1_disarmed_manual_spin_20260224_135840.jsonl`
- `.runlogs/encoder_checks/check2_balancing_slight_angle_20260224_135926.jsonl`
- `.runlogs/encoder_checks/check3_direct_get_balancing_20260224_140041.jsonl`
- `.runlogs/encoder_checks/motor_symmetry_220ms_20260224_141135.jsonl`

Recent burst captures:
- `tests/results/host_run_1771964558.csv`
- `tests/results/host_run_1771964852.csv`
- `tests/results/host_run_1771964979.csv`
- `tests/results/host_run_1771965396.csv` (invalid run; classifier runtime error)

Classifier rollout notes:
- Host capture summary now includes event contract fields (`event_contract_version=v1`).
- Invalid-window diagnosis now explicit (`invalid_window_low_signal`).
- Hardware profile activation complete: `test_bot_balance_mvp_v1` is active and compat-check passes against `balance_mvp_v1/runtime_manifest_v1.json`.
- Future multi-hardware contract (deferred for this bot): `docs/contracts/multi_hardware_profile_contract_v1.md`

---

## 8) Execution Plan (Now)

1. Run one burst with current tune and label operator outcome using forward/backward taxonomy.
2. Accept run only if Gate A flags indicate valid/coherent event characterization.
3. If valid, apply one bounded tuning delta and run post-capture under matched conditions.
4. Update this scorecard with artifact paths, outcome class, and rollback note.

Active tuning protocol:
- `docs/TUNING_AGENT_GROUND_RULES_V1.md` is now the required run contract for this bot.
- `docs/TUNING_STAGE_TRACKER_TEMPLATE.md` is the required per-run capture form.
- Any process-rule violations are tracked as run-validity failures in this scorecard.

---

## 8A) `P0` UX Hardening Sprint (Do Now, Single Scorecard Owner)

Owner:
- Requirement owner: `JVKE` (operator workflow + safety constraints)
- Implementation owner: `Codex` (bridge + clean tuning UX)

Scope:
- Applies to this scorecard only; no parallel tracking in Overhaul scorecard.
- Purpose is to make tuning runs trustworthy before further gain tuning.

Implementation checklist (must complete in order):
- [x] `DONE` Add `Run Intent` selector before burst/arm (`unassisted_tuning`, `assisted_safety_catch`, `bench_test`) and persist intent in run summary.
- [x] `DONE` Hard-block score eligibility for assisted runs by default, with explicit `run_valid_for_tuning=false` reason in UI and summary.
- [x] `DONE` Add one-click `Recover + Re-arm` action for this firmware path (`DISARM -> FAULTCLR -> ESTOP 0 -> ARM`) with live status confirmation.
- [x] `DONE` Add pre-release checklist modal (`battery`, `cable slack`, `clear runway`, `upright hold`) before arm is allowed.
- [x] `DONE` Enforce single-variable lock in tuning controls (prevent multi-parameter apply in one run step).
- [x] `DONE` Patch `balance_mvp_v1` sketch to expose required drift diagnostics per tick (`wposRaw_unclamped`, `wdelta_tick`, per-side applied output, fault trigger snapshot) without removing safety gates.
- [x] `DONE` Patch sketch arm behavior to reduce launch transient (bounded engage ramp) and keep existing fail-closed fault/estop semantics.

Acceptance criteria:
- [ ] `TODO` Three consecutive runs can be labeled without ambiguity (`intent`, `assisted`, `outcome`, `notes` all present).
- [ ] `TODO` At least one assisted run is automatically excluded from scoring with visible reason.
- [ ] `TODO` At least one invalid run is retried via `Recover + Re-arm` without manual command typing.
- [ ] `TODO` UI prevents multi-variable apply; attempted violation is surfaced as explicit guardrail error.
- [ ] `TODO` New sketch telemetry fields appear in host run CSV + summary artifacts and are non-zero during induced motion tests.
- [ ] `TODO` Engage transient magnitude is reduced vs current baseline in at least one matched A/B run, with no safety regression.

Exit rule:
- This `P0` sprint must be green before additional PID/motion tuning objectives are promoted.

---

## 9) Outcome Taxonomy (Operator Labels)

Allowed run outcomes:
- `fell_forward`
- `fell_backward`
- `runaway_forward_saved`
- `runaway_backward_saved`
- `stable_window`

These labels are required context for tuning decisions when telemetry alone is ambiguous.

---

## 10) Knowledge Memory Discipline (Required)

Canonical memory location:
- `docs/assistant_knowledge/manifest.json` (active pack selector)
- `docs/assistant_knowledge/knowledge_governance_v1.0.md` (supersession/update policy)

Current active knowledge pack:
- `v1.2` (`playbook_v1.2.md`, `rules_and_constraints_v1.2.md`, `theory_pid_kalman_v1.2.md`)

Required per meaningful learning update:
- [ ] `TODO` Add/modify versioned markdown in `docs/assistant_knowledge/` (no silent drift).
- [ ] `TODO` Update `manifest.json` changelog with what changed and why.
- [ ] `TODO` Link supporting evidence artifacts in this scorecard Evidence Log.
- [ ] `TODO` Mark superseded guidance explicitly instead of deleting prior versions.

---

## 11) Hardware Mode Policy (Current vs Future)

Current mode:
- `single_bot_test` is required for this bot until autonomous balance acceptance is green.
- Profile-selection UX is intentionally not mandatory in this mode.

Future mode trigger:
- Switch to `multi_hardware` only when a second hardware stack enters active bring-up.
- Source contract for that transition: `docs/contracts/multi_hardware_profile_contract_v1.md`

---

## 12) Process Governance Checklist

Protocol references (authoritative instructions):
- `docs/TUNING_AGENT_GROUND_RULES_V1.md`
- `docs/TUNING_STAGE_TRACKER_TEMPLATE.md`
- `docs/AGENT_SESSION_BRIEFING_STANDARD_V1.md`

### 12A) New Agent Baseline (Effective Immediately)
- [x] `DONE` New tuning-agent contract authored: `docs/TUNING_AGENT_GROUND_RULES_V1.md`.
- [x] `DONE` Mandatory full-bundle reapply + `GET` parity check defined per run.
- [x] `DONE` Standardized failure taxonomy includes reversal-specific failure classes.
- [x] `DONE` Regression guard and rollback protocol defined.
- [ ] `TODO` Run 3 consecutive tests under new contract and confirm zero variable-parity drift.

### 12B) Process Validity Tracking
- [ ] `TODO` Track and label each process violation (`bundle mismatch`, `missing parity check`, `multi-group edit`) as run-invalid.
- [ ] `TODO` Keep scorecard focused on outcomes, gate status, and evidence links only.
- [ ] `TODO` Route all operational tuning instructions to the runbook/template, not this scorecard.

### 12C) ChatGPT ↔ Codex Design Exchange (Full-Size Bot)
- [ ] `TODO` Require a versioned inbound design packet from ChatGPT before architecture decisions are accepted.
- [ ] `TODO` Inbound packet must include: chosen parts, rationale, known limits, compatibility with current parts/software, hard constraints, and required assumptions.
- [ ] `TODO` Codex produces a versioned audit response that checks: inconsistencies, integration risks, likely failure points, safety concerns, and migration cost.
- [ ] `TODO` Audit response must classify each issue as `blocker`, `high`, `medium`, or `low` and include concrete remediation options.
- [ ] `TODO` Audit response must explicitly separate:
  - `adapt_system_to_part` recommendations (preferred when quality/safety/performance improves),
  - `hold_system_constraint` cases where platform constraints are non-negotiable.
- [ ] `TODO` Audit scope must include full electrical interface validation:
  - pin in/out map, bus allocation, voltage domains, level-shifting needs, current budget, and boot-mode pin conflicts.
- [ ] `TODO` Require generated integration artifacts per accepted design cycle:
  - sketch scaffolds/stubs (firmware command + runtime contract aware),
  - Mermaid wiring/system diagrams tied to the validated pin map.
- [ ] `TODO` Require Codex to use local engineering memory sources first (before external assumptions):
  - support docs, datasheets, board files, and 3D assets in project storage.
- [ ] `TODO` Audit response must cite which local source artifacts were used and identify any missing source data that blocks confidence.
- [ ] `TODO` Maintain a round-trip artifact pair per review cycle:
  - inbound packet file (ChatGPT -> Codex),
  - outbound audit file (Codex -> ChatGPT).
- [ ] `TODO` No architecture-level part choice is marked accepted until a matching round-trip artifact pair exists and unresolved `blocker` items are zero.

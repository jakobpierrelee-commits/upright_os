# PRD: Bot Setup + Validation Flow V2 (Canonical)

Version: 1.0
Status: Active
Owner: Setup + Agent Reliability Track
Last Updated: 2026-02-20

## 1. Objective
Deliver a reliable setup flow that prevents invalid Tune entry, avoids infinite retry loops, and keeps sketch/source state auditable across New Bot and Existing Bot paths.

## 2. Problem
Current risks:
- sketch source-of-truth drift between app, IDE, and bot
- binary pass/fail without actionable diagnostics
- regeneration loops without deterministic guardrails
- weak outage handling for agent/bridge/runner failures
- insufficient per-attempt traceability for support/debug

## 3. Goals
- Canonical sketch lifecycle with deterministic precedence.
- Structured validation (compat + smoke) with clear blockers/warnings.
- Retry loop with bounded attempts and automatic escalation.
- Full attempt/audit history visible to users and support.
- Clean routing for New Bot and Existing Bot.

## 4. Non-Goals
- Full performance benchmarking pre-Tune.
- Replacing Tune itself.
- Multi-agent orchestration.

## 5. Core Terms
- Sketch: generated firmware artifact/config.
- Canonical sketch: single active sketch record for current attempt.
- Compat test: structured contract/capability validation.
- Smoke check: minimal runtime viability check after compat pass.
- Attempt: diagnose -> regenerate -> retest cycle.

## 6. User Flows

### 6.1 Entry
- First screen shows exactly two options:
  - New Bot
  - Existing Bot

### 6.2 New Bot
1. User enters mission + parts.
2. Agent gets structured context and generates Sketch v1.
3. System stores canonical sketch record (version/hash/source/timestamp).
4. Run compat.
5. If compat has no blockers, run smoke.
6. If smoke passes, unlock Tune.
7. If compat/smoke fails, enter retry loop.

### 6.3 Existing Bot
1. User picks one intake method:
  - Scan Existing Bot
  - Saved Profile Dropdown
2. Reconcile bot/app/IDE sources.
3. Select canonical sketch via precedence policy.
4. Run compat -> smoke.
5. On failure, same retry loop as New Bot.

## 7. Decision Policy

### 7.1 Tune Gate
Tune is reachable only when:
- compat blockers = 0
- smoke status = pass

Warnings do not block Tune, but must be shown before continue.

### 7.2 Canonical Source Precedence
When sources disagree, resolve in order:
1. explicit user-confirmed override for this session
2. latest valid canonical sketch (hash-verified)
3. bot readback (if parseable + hashable)
4. IDE buffer snapshot

If ambiguity remains, require user confirmation and log reconciliation event.

### 7.3 Retry/Escalation
- `max_attempts` default: 3
- Stop auto-loop at max attempts
- Route to guided manual troubleshooting with:
  - latest canonical sketch
  - latest blockers/warnings
  - diff history
  - suggested actions

## 8. Status Contract
All validation-like endpoints use:
- `pass | warn | fail | error | timeout | unavailable`

Semantics:
- `error`: execution exception
- `timeout`: runner exceeded budget
- `unavailable`: dependency down (agent/bridge/etc.)

## 9. Functional Requirements
- FR-1 Entry routing with exactly two choices.
- FR-2 New Bot sketch generation and canonical persistence.
- FR-3 Existing Bot dual intake + reconciliation.
- FR-4 Structured compat response:
  - `status`
  - `blocking_issues[]`
  - `warnings[]`
  - `recommended_fix_prompts[]`
- FR-5 Smoke gate after compat pass.
- FR-6 Bounded retry loop with escalation.
- FR-7 Operational resilience for agent/runner outages.
- FR-8 User-visible attempt timeline + backend audit log.
- FR-9 Account/robot/thread scoping on all artifacts.

## 10. Data Model (Minimum)

### 10.1 SketchVersion
- `account_id`, `robot_id`, `thread_id`
- `sketch_id`, `version`, `hash`
- `source` (`system|agent|user`)
- `parent_version`
- `diff_summary`
- `created_at`

### 10.2 ValidationResult
- `account_id`, `robot_id`
- `sketch_id`, `version`
- `compat_status`, `blocking_issues[]`, `warnings[]`
- `smoke_status`, `checks[]`, `failure_summary`
- `tested_at`

### 10.3 AttemptLog
- `account_id`, `robot_id`, `thread_id`
- `attempt_id`, `attempt_number`
- `request_id` (idempotency)
- `sketch_version`
- `report_id`, `agent_request_id`
- `result`
- `started_at`, `ended_at`

## 11. API Contract (V1 Draft)

### POST `/v1/setup/compat-test`
Req: `request_id`, `sketch_id`, `version`, `sketch_payload`
Res: `status`, `blocking_issues[]`, `warnings[]`, `recommended_fix_prompts[]`

### POST `/v1/setup/smoke-check`
Req: `request_id`, `sketch_id`, `version`
Res: `status`, `checks[]`, `failure_summary`

### POST `/v1/setup/diagnostic-report`
Req: `request_id`, `sketch_id`, `version`, `compat_result`, `smoke_result`
Res: `report_id`, `prompt_text`, `structured_actions[]`

### POST `/v1/setup/regenerate-sketch`
Req: `request_id`, `report_id`, `prior_sketch_version`, `context`
Res: `new_version`, `sketch_payload`, `diff_summary`

### POST `/v1/setup/reconcile`
Req: bot/app/IDE sources + hashes
Res: canonical selection + reconciliation event + diff summary

## 12. Failure Handling
- Agent timeout/unavailable:
  - mark status `timeout|unavailable`
  - queue retry candidate
  - offer manual prompt copy/send
- Bridge/runner failure:
  - mark `error|unavailable`
  - show reconnect + retry actions
- Preserve state across all recoverable failures.

## 13. UX Requirements
- Stepper: Mission -> Parts -> Sketch -> Compat -> Smoke -> Tune
- Existing intake cards: Scan + Saved Profile Dropdown
- Compat view:
  - pass/fail/warn badge
  - blockers/warnings lists
  - diagnostic panel
  - regenerate CTA
  - attempt history timeline

## 14. Observability + Audit
Per-attempt persistence:
- sketch version/hash
- diff from previous
- compat + smoke outputs
- timestamps + actor/source
- request/attempt IDs

## 15. Success Metrics
- first-pass validation rate
- average attempts before pass
- escalation rate at max attempts
- time-to-Tune
- support interventions per setup flow

## 16. State Machine
- `entry` -> `mission_parts` -> `sketch_generated`
- `sketch_generated` -> `compat_running` -> (`compat_blocked` | `compat_passed`)
- `compat_passed` -> `smoke_running` -> (`smoke_failed` | `tune_unlocked`)
- (`compat_blocked` | `smoke_failed`) -> `diagnose_regen` -> (`compat_running` or `manual_escalation`)
- `manual_escalation` terminal until user/manual fix resumes flow

## 17. Rollout
1. canonical sketch + attempt log base
2. structured compat contract + UI
3. smoke gate + Tune lock
4. bounded auto-regenerate loop
5. escalation + audit dashboard

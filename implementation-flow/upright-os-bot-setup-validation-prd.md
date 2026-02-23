# Superseded
This document is superseded by:
- `docs/PRD_BOT_SETUP_VALIDATION_V2.md` (canonical requirements)
- `docs/BOT_SETUP_VALIDATION_V2_IMPLEMENTATION_CHECKLIST.md` (repo-mapped execution)

# Product Requirements Document
## Upright OS Bot Setup and Validation Flow v2

## 1. Objective
Create a reliable bot setup experience that minimizes failed configurations, prevents infinite retry loops, and ensures users only reach Tune after validated compatibility and runtime viability.

## 2. Problem Statement
Current behavior risks:
- ambiguous sketch source of truth
- binary pass/fail outcomes with limited actionability
- manual handoff friction in failure loops
- potential infinite regenerate/test cycling
- missing operational error paths (agent/IDE outages)

## 3. Goals
- Standardize a canonical sketch lifecycle.
- Improve failure diagnostics and automated remediation.
- Gate Tune behind meaningful validation.
- Preserve full attempt history for debugging and trust.
- Support both New Bot and Existing Bot pathways cleanly.

## 4. Non-Goals
- Full bot performance benchmarking before Tune.
- Replacing Tune workflow itself.
- Multi-agent orchestration beyond single troubleshooting agent.

## 5. Users
- Primary: Operator configuring a new or existing bot.
- Secondary: Internal support/engineering reviewing failed attempts.

## 6. User Stories
1. As a user, I can choose New Bot or Existing Bot immediately on app open.
2. As a user, I can configure a new bot from mission and parts without manual wiring.
3. As a user, I can load an existing bot by scan or profile dropdown.
4. As a user, I receive clear blocker/warning diagnostics when validation fails.
5. As a user, I can rely on automatic regeneration cycles up to a safe limit.
6. As a user, I can continue to Tune only after validated readiness.
7. As support, I can inspect versioned attempts and diffs to diagnose issues.

## 7. Functional Requirements

### FR-1 Entry and Routing
- App open screen must present `New Bot` and `Existing Bot`.
- No additional primary options on first screen.

### FR-2 New Bot Creation
- Capture mission and selected parts.
- Auto-send selected configuration context to agent.
- Generate and store `Sketch v1` as canonical record.

### FR-3 Existing Bot Intake
- Provide two methods:
  - Scan Existing Bot
  - Saved Profile Dropdown
- Reconcile sketch sources (bot/app/IDE).
- Persist reconciliation outcomes and diffs.

### FR-4 Validation Pipeline
- Run compat test for canonical sketch.
- Compat output must include:
  - `status`
  - `blocking_issues[]`
  - `warnings[]`
  - `recommended_fix_prompts[]`
- Run smoke check only if no blockers.
- Route to Tune only if smoke passes.

### FR-5 Failure Loop
- On compat/smoke fail:
  - generate diagnostic report
  - auto-send to agent
  - regenerate sketch
  - rerun validation
- Persist each attempt with version and diff.
- Enforce `max_attempts` (default 3), then escalate to guided manual troubleshooting.

### FR-6 Operational Resilience
- Handle agent timeout/unavailable.
- Handle IDE bridge/test runner errors.
- Preserve state across retries and transient failures.

### FR-7 Observability and Audit
- Store attempt logs with timestamps, sketch hash, results, and source.
- Show user-visible attempt history in UI.

## 8. Non-Functional Requirements
- Reliability: no loss of sketch/attempt state during recoverable errors.
- Latency: validation feedback should appear progressively (status updates).
- Usability: user can understand failure cause in plain language.
- Security: account-scoped profile access only.
- Traceability: every Tune entry is linked to passing validation artifacts.

## 9. UX Requirements
- Stepper progression:
  - Mission
  - Parts
  - Sketch
  - Compat
  - Smoke
  - Tune
- Existing intake uses dual cards plus account profile dropdown.
- Compat view must include:
  - pass/fail badge
  - blockers/warnings list
  - report text panel
  - regenerate action
  - attempt timeline

## 10. Data Model (Minimum)

### SketchVersion
- `sketch_id`
- `version`
- `hash`
- `created_at`
- `source` (agent/system/user)
- `parent_version`
- `diff_summary`

### ValidationResult
- `sketch_id`
- `version`
- `compat_status`
- `blocking_issues[]`
- `warnings[]`
- `smoke_status`
- `tested_at`

### AttemptLog
- `attempt_number`
- `sketch_version`
- `report_id`
- `agent_request_id`
- `result`
- `started_at`
- `ended_at`

## 11. API Contract Shapes (Draft)

### POST /compat-test
Request:
- `sketch_id`
- `version`
- `sketch_payload`
Response:
- `status` (`pass|fail`)
- `blocking_issues[]`
- `warnings[]`
- `recommended_fix_prompts[]`

### POST /smoke-check
Request:
- `sketch_id`
- `version`
Response:
- `status` (`pass|fail`)
- `checks[]`
- `failure_summary`

### POST /diagnostic-report
Request:
- `sketch_id`
- `version`
- `compat_result`
- `smoke_result`
Response:
- `report_id`
- `prompt_text`
- `structured_actions[]`

### POST /regenerate-sketch
Request:
- `report_id`
- `prior_sketch_version`
- `context`
Response:
- `new_version`
- `sketch_payload`
- `diff_summary`

## 12. Success Metrics
- First-pass validation rate.
- Average attempts before pass.
- Percentage of flows escalated after max attempts.
- Time-to-Tune from app open.
- Reduction in manual support interventions.

## 13. Rollout Plan
1. Implement canonical sketch + attempt logging.
2. Add structured compat response and compat UI.
3. Add smoke gate and Tune lock.
4. Enable auto-regenerate loop with max attempts.
5. Add escalation workflow and full observability dashboard.

## 14. Risks and Mitigations
- Risk: false negatives in compat test.
  - Mitigation: categorize rules, tune severity thresholds.
- Risk: noisy regeneration loops.
  - Mitigation: dedupe repeated failures and enforce max attempts.
- Risk: sketch drift between systems.
  - Mitigation: canonical versioning + hash checks at every transition.

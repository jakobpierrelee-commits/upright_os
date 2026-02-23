# Superseded
This document is superseded by:
- `docs/PRD_BOT_SETUP_VALIDATION_V2.md`
- `docs/BOT_SETUP_VALIDATION_V2_IMPLEMENTATION_CHECKLIST.md`

# Upright OS Bot Flow v2 (Execution Spec)

## Purpose
Define the exact app flow for New Bot and Existing Bot paths, with validation gates, retry policy, and escalation rules.

## Entry
- Trigger: User opens Upright OS app.
- First screen must present exactly two options:
  - `New Bot`
  - `Existing Bot`

## Core Concepts
- `Sketch`: Generated bot configuration artifact.
- `Canonical Sketch`: Single source of truth for current attempt.
- `Compat Test`: Structured validation that returns blockers and warnings.
- `Smoke Check`: Minimal runtime check after compat pass, before Tune.
- `Attempt`: One cycle of diagnose -> regenerate -> retest.

## New Bot Flow
1. User defines mission.
2. User selects parts.
3. Agent receives mission + selected fields and generates `Sketch v1`.
4. System stores canonical sketch record:
   - version
   - hash
   - timestamp
   - generator/source
5. System sends sketch to IDE and runs compat test.
6. If compat has no blockers, run smoke check.
7. If smoke passes, route to Tune page.
8. If compat or smoke fails:
   - build diagnostic report + fix prompt
   - auto-send to agent (user can review/edit)
   - agent generates `Sketch vN+1`
   - store new version + diff + attempt log
   - rerun compat test
9. If attempts exceed `max_attempts`, route to guided manual troubleshooting.

## Existing Bot Flow
1. User chooses one intake method:
   - `Scan Existing Bot`
   - `Saved Profile Dropdown`
2. If scan path:
   - read bot sketch
   - load into IDE if missing
3. If saved profile path:
   - load saved sketch
4. Reconcile sketch sources (bot/app/IDE).
5. If mismatch:
   - choose latest valid canonical sketch
   - record diff and reconciliation event
6. Run compat test on canonical sketch.
7. Follow same pass/fail loop as New Bot:
   - pass compat -> smoke check -> Tune
   - fail -> report -> regenerate -> retest
8. Escalate after `max_attempts`.

## Decision Rules
- Tune page is reachable only when:
  - compat has zero blockers
  - smoke check passes
- Warnings do not block Tune, but must be shown before continue.
- Blocking issues always enter regeneration loop.
- Retry loop must preserve mission, parts, bot identity, and history.

## Retry and Escalation Policy
- `max_attempts` default: 3.
- Auto-retry enabled for each fail.
- After max attempts:
  - stop auto-loop
  - open guided troubleshooting with:
    - latest canonical sketch
    - test history
    - top blockers
    - suggested manual actions

## Failure Handling
- Agent timeout/unavailable:
  - queue retry
  - show notification
  - allow manual prompt copy/send
- IDE bridge/test runner failure:
  - show retry + reconnect actions
  - preserve current attempt state
- Any failure state must be recoverable without losing context.

## Auditability
For every attempt, persist:
- sketch version + hash
- diff from previous sketch
- compat result (blockers/warnings)
- smoke result
- timestamps
- actor/source (system, agent, user)

## UX Requirements
- Stepper: `Mission -> Parts -> Sketch -> Compat -> Smoke -> Tune`.
- Existing Bot intake screen:
  - card A: Scan Existing Bot
  - card B: Select Saved Profile (dropdown)
- Compat screen:
  - status badge
  - blockers/warnings panel
  - diagnostic report panel
  - regenerate CTA
  - attempt history

## Acceptance Criteria
- User can complete New Bot and Existing Bot flows end-to-end in-app.
- No path can bypass compat + smoke before Tune.
- On every fail, user gets actionable diagnostic text.
- Loop exits automatically to manual guidance at max attempts.
- All retries are versioned and auditable.

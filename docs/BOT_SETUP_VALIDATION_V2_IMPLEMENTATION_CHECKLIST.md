# Bot Setup + Validation V2: Implementation Checklist (Repo-Mapped)

Scope: Maps `docs/PRD_BOT_SETUP_VALIDATION_V2.md` to current code and concrete next tasks.

## 1. Current Coverage Snapshot

### 1.1 Implemented (partial/adjacent)
- Setup workflow UI and generation prerequisites:
  - `app/ui/ops-console/src/pages/stage1/ConnectPreflightPage.tsx`
- Board resolver + pin validation + agent hardware context feed:
  - `app/ui/ops-console/src/hardware/boardResolver.ts`
  - `app/ui/ops-console/src/hardware/pinValidation.ts`
  - `app/ui/ops-console/src/hardware/boardRegistry.ts`
- Hardware context persisted and injected into chat:
  - `app/bridge/server.py` (`HardwareContextStore`, `/ai/chat`, `/ai/chat/tools`, `/ai/chat/stream`)
- Existing profile save/activate/validate primitives:
  - `app/bridge/server.py` (`/profiles`, `/profiles/validate`, `/profiles/save`, `/profiles/activate`)
  - `app/ui/ops-console/src/api.ts` profile endpoints
- Compat/connect probe primitives:
  - `app/bridge/server.py` (`/probe/compat`, `/probe/connect`)

### 1.2 Missing for full V2
- Dedicated smoke-check endpoint + UI gate artifact.
- Canonical sketch version table/store with diff lineage.
- Retry loop engine with `max_attempts` and escalation state.
- Source reconciliation endpoint (bot/app/IDE hash arbitration).
- V1 versioned API namespace (`/v1/setup/*`).
- Idempotency keys (`request_id`) + per-robot/session lock.
- Attempt timeline persisted as first-class entity and displayed in Setup.

## 2. Endpoint Mapping Plan

### 2.1 Compat
- Existing: `GET /probe/compat`
- Add: `POST /v1/setup/compat-test`
  - wraps probe + returns structured status contract
  - includes `blocking_issues[]`, `warnings[]`, `recommended_fix_prompts[]`

### 2.2 Smoke
- Add: `POST /v1/setup/smoke-check`
  - minimal runtime viability checks (bridge connected, loop data fresh, estop clear, command path OK)

### 2.3 Diagnostic + Regeneration
- Add: `POST /v1/setup/diagnostic-report`
- Add: `POST /v1/setup/regenerate-sketch`
  - can call existing generation tools and return `diff_summary`

### 2.4 Reconciliation
- Add: `POST /v1/setup/reconcile`
  - compares bot/app/IDE snapshots and returns canonical choice + reconciliation log

## 3. File-Level Task List

## Phase A: Data + Store
- [ ] `app/bridge/server.py`
  - add `SetupAttemptStore` and `SketchVersionStore` (JSON first, DB later)
  - include `account_id`, `robot_id`, `thread_id`, `attempt_id`, `request_id`
- [ ] `app/bridge/tests/`
  - add store unit tests for persistence, lineage, and idempotency

## Phase B: API Surface
- [ ] `app/bridge/server.py`
  - add `/v1/setup/compat-test`
  - add `/v1/setup/smoke-check`
  - add `/v1/setup/diagnostic-report`
  - add `/v1/setup/regenerate-sketch`
  - add `/v1/setup/reconcile`
- [ ] `app/ui/ops-console/src/api.ts`
  - add typed clients for new `/v1/setup/*` endpoints

## Phase C: UI Flow
- [ ] `app/ui/ops-console/src/pages/stage1/ConnectPreflightPage.tsx`
  - add explicit Compat -> Smoke -> Tune gate timeline
  - add attempt timeline panel (attempt number, status, sketch version/hash)
  - add escalation panel when attempts exceed max
- [ ] `app/ui/ops-console/src/styles.css`
  - style attempt timeline + escalation panel in midnight token system

## Phase D: Retry Engine
- [ ] `app/bridge/server.py`
  - add deterministic retry orchestrator:
    - on fail -> diagnostic -> regenerate -> revalidate
    - enforce `max_attempts` default 3
    - emit escalation state
- [ ] Tests:
  - [ ] loop success in <=3 attempts
  - [ ] escalation on repeated fail
  - [ ] dedupe same failure signature

## Phase E: Reconciliation + Locking
- [ ] `app/bridge/server.py`
  - implement source precedence policy
  - per-robot/session mutex for setup loop
- [ ] Tests:
  - [ ] concurrent requests do not fork canonical sketch
  - [ ] precedence policy picks deterministic source

## 4. Structured Status Contract
- [ ] enforce enum at API boundary:
  - `pass|warn|fail|error|timeout|unavailable`
- [ ] reject unknown status values in handlers/tests

## 5. Acceptance Test Matrix
- [ ] New Bot happy path: mission->parts->v1->compat pass->smoke pass->Tune unlocked
- [ ] Existing Bot scan path with source mismatch reconciliation
- [ ] Existing Bot saved profile path
- [ ] compat fail -> auto regenerate -> pass within max attempts
- [ ] compat fail repeated -> escalation at max attempts
- [ ] smoke fail -> retry loop path
- [ ] agent unavailable path retains state and offers manual continuation

## 6. Suggested Build Order (Fastest Safe)
1. Phase A stores + tests
2. Phase B compat/smoke endpoints + API client types
3. Phase C UI gate and timeline shell
4. Phase D retry orchestrator
5. Phase E reconciliation + lock hardening

## 7. Immediate Next Commit Slice
- Add `/v1/setup/compat-test` + `/v1/setup/smoke-check` endpoints (read-only, no loop yet).
- Add `api.ts` client calls and minimal UI display in Setup.
- Add tests for status enum and basic pass/fail mapping.

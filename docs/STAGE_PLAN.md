# Stage Plan (Execution Sequencing)

Purpose: define stage order, entry/exit criteria, and dependency flow so we execute cleanly without context churn.

Last updated: `2026-02-23`
Owner: `Codex + JVKE`
Primary tracker: `docs/OVERHAUL_SPRINT_SCORECARD.md`

## How To Use

1. Work one active stage at a time.
2. Stage is not complete until exit criteria and evidence are both met.
3. If a blocker appears, log it in `docs/RISK_REGISTER.md` before changing scope.
4. Any strategy change must be logged in `docs/DECISIONS.md`.
5. For non-trivial scope adds/changes, complete `docs/CHANGE_PROPOSAL_TEMPLATE.md` first.

## Active Stage

- Current active stage: `S3 - Backend Decomposition`
- Current focus: reduce `app/bridge/server.py` risk by moving clean-lane logic into modules with no contract changes.

## Stage Map

### S0 - Runtime Baseline (Done)

- Scorecard links: `#1`, `#2`, `#3`, `#4`, `#5`, `#6`, `#15`, `#16`, `#17`
- Exit criteria:
  - Clean lane default path stable.
  - Compile/upload/recovery routes functional.
  - CI static gates green.

### S1 - Execution Parity (Done)

- Scorecard links: `#2`, `#6`
- Exit criteria:
  - Clean chat routes execute tools, not advisory-only text.
  - Tool evidence returned in responses.
  - Parity gates pass.

### S2 - Manifest and Safety Gates (Done except hardware signoff)

- Scorecard links: `#5` section, `#20`, `#21`
- Exit criteria:
  - Runtime manifest fail-closed checks in preflight/upload paths.
  - Profile/manifest compatibility checks functional.
  - Pre-arm hardware check exists and blocks unsafe arm.

### S3 - Backend Decomposition (In Progress)

- Scorecard links: `#26`, `#27`, `#29`, `#30`
- Entry criteria:
  - S0-S2 route behavior stable.
  - Contract tests available.
- Current extracted slices:
  - `clean_firmware_ops`, `clean_preflight`, `clean_codex_chat`, `clean_route_helpers`, `clean_auth_helpers`, `clean_threads`, `clean_status`, `clean_request_parsers`, `clean_sse`
- Exit criteria:
  - `app/bridge/server.py <= 11,000` lines.
  - No clean-lane behavior regressions.
  - CI includes new module tests and contract checks.

### S4 - Hardware Validation Signoff (P0)

- Scorecard links: `#21`
- Entry criteria:
  - S3 routes stable for a full burn-in.
- Exit criteria:
  - Real hardware pre-arm check signoff (wheel pulse + E-STOP validation).
  - Known failure classes mapped to plain-English operator actions.
  - Signoff artifact captured with `./tools/lean/check_prearm_signoff.sh` and attached to scorecard evidence.

### S5 - UI Composition Refactor (P1)

- Scorecard links: `#28`, `#11`, `#12`, `#13`, `#14`, `#25`
- Exit criteria:
  - `App.tsx` split into domain modules.
  - File tree + execution context + tool-output surfaces integrated.
  - Upload/preflight progress clearly visible.

### S6 - Tuning Intelligence Gates (P1)

- Scorecard links: `#22`, `#23`, `#24`
- Exit criteria:
  - Tuning quality gate and acceptance scenarios pass.
  - Phase evidence contract migration complete (`phase1_*`, `phase2_*` canonical usage).

## Stage Dependencies

1. `S3` must remain active until `server.py` risk is reduced below go-now threshold.
2. `S4` hardware signoff should not be delayed by UI cosmetics.
3. `S5` can run in parallel with `S4` only if P0 reliability stays green.
4. `S6` starts only after stable telemetry quality and phase evidence consistency.

## Evidence Requirements Per Stage

1. Commands run and pass/fail results.
2. Files changed.
3. Manual validation notes.
4. Scorecard items moved to `DONE` or `IN PROGRESS` with reason.

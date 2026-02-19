# UpRight.os Ops Console Session Handoff (2026-02-18)

## Scope Completed
This session focused on UI reliability and operator workflow polish for:
- Codex panel behavior and sizing
- Alert dock/popup behavior
- Button sizing/theming hierarchy
- IMU HUD overlay telemetry validation
- Layout stability and scroll cleanup
- Guardrail checks to prevent style/patch regressions

## Key Changes Implemented

### 1) Codex Panel: Always-Visible Chat + Better Layout
- Separated history toggle from live chat rendering.
  - `Reveal Last Chats` now controls only thread/history list.
  - Active chat window remains visible at all times.
- Chat input remains pinned to bottom, messages populate upward.
- Added auto-scroll-to-latest on thread/history updates.
- Made Codex panel/rail height viewport-aware and sticky.

Files:
- `app/ui/ops-console/src/features/codex/CodexPanel.tsx`
- `app/ui/ops-console/src/styles.css`

### 2) Codex Height: Dynamic Subtraction of Real Layout
- Implemented runtime measurement in `App.tsx` for:
  - codex top offset (`--ops-codex-top-offset`)
  - actual status dock clearance (`--statusbar-clearance`)
- Converted rail/panel height math to use those live CSS vars.

Files:
- `app/ui/ops-console/src/App.tsx`
- `app/ui/ops-console/src/styles.css`

### 3) Alert Dock UX Refactor
- Replaced large `Open/Hide` control with tiny chevron.
- Expanded alerts now render in floating bottom-right popout (out of dock flow).
- Dock no longer expands in height when alerts are opened.
- Increased popout size and list capacities for better visibility.
- Kept popout compact on smaller screens via media rules.

Files:
- `app/ui/ops-console/src/components/alerts/GlobalAlertRail.tsx`
- `app/ui/ops-console/src/styles.css`

### 4) Status Dock Alignment
- Wrapped left status items into `.statusbar-meta`.
- Vertically centered status metadata against dock height.

Files:
- `app/ui/ops-console/src/App.tsx`
- `app/ui/ops-console/src/styles.css`

### 5) Button System Improvements
- Added reusable tiny button class:
  - `.btn-xs` / `.btn-size-tiny`
- Applied tiny sizing to chevron + alert clear actions.
- Converted clear actions to danger theme where requested.
- Fixed alert action sizing to respect shared button tokens.

Files:
- `app/ui/ops-console/src/styles.css`
- `app/ui/ops-console/src/components/alerts/GlobalAlertRail.tsx`

### 6) IMU Overlay Upgrade to 3 Lines
- Added UI-side Kalman reference trace (computed from `raw + gyro` over sampled dt).
- Overlay now shows:
  1. raw angle
  2. firmware kalman angle (`ang`)
  3. UI kalman reference (dashed)
- Updated legend and chart styling for third line.

Files:
- `app/ui/ops-console/src/hooks/useHudTelemetry.ts`
- `app/ui/ops-console/src/pages/shared/HudVisuals.tsx`
- `app/ui/ops-console/src/App.tsx`
- `app/ui/ops-console/src/styles.css`

### 7) Startup/Tab Flow
- Reordered primary tabs: IDE first, Tune second.
- Default startup tab switched to IDE.

File:
- `app/ui/ops-console/src/App.tsx`

### 8) Layout Cleanup
- Removed stale bottom reserve spacing causing blank vertical scroll.
- Updated layout min-height formulas to use viewport-aware calc.

File:
- `app/ui/ops-console/src/styles.css`

### 9) Guardrails Added
- Added automated guardrail script to detect:
  - inline JSX style blocks
  - ts-ignore / ts-expect-error / ts-nocheck
  - `as any`
  - prototype/global monkey-patch patterns
  - `Object.defineProperty` patch usage
- Added npm script: `npm run guardrails`

Files:
- `app/ui/ops-console/scripts/guardrails.sh`
- `app/ui/ops-console/package.json`

## Validation Performed
- Repeated `npm run build` checks after each major patch.
- `npm run guardrails` passes.
- No TypeScript/Vite build failures observed after final changes.

## QA Artifact Created
- `docs/QA_TEST_CHECKLIST.md`
  - Added focused validation checklist for this updated build.

## Notes
- The UI-side Kalman line is a **reference estimator** using fixed conservative parameters; it is intended for divergence visibility, not as a strict source-of-truth replacement for firmware internals.

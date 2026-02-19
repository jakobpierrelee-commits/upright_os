# UpRight.os Ops Console QA Checklist

## Session Info
- Date:
- Tester:
- Build/Branch:
- Browser:
- Device/Viewport:

## Preflight
- [ ] Bridge is running and healthy (`/health`, `/status`).
- [ ] UI is running in preview mode.
- [ ] Telemetry stream is active (angle/raw/gyro updating).

## Core Regression Checks

### 1) IMU Overlay (3-Line Validation)
- [ ] Overlay shows 3 distinct lines:
  - raw angle
  - firmware kalman angle
  - UI kalman reference (dashed)
- [ ] Legend colors/styles match the lines.
- [ ] Lines update continuously as telemetry changes.
- [ ] No chart rendering glitches after tab switches.

### 2) Codex Panel Layout/Sizing
- [ ] Codex panel stays above the status dock at all times.
- [ ] No clipping behind bottom dock when resizing window.
- [ ] Chat input remains pinned at bottom.
- [ ] Chat history toggle does not hide the active chat window.

### 3) Alert Dock + Popout
- [ ] Chevron toggle works (collapsed/expanded).
- [ ] Expanded alerts open as a floating panel (not full-width dock expansion).
- [ ] Dock height does not jump when expanding alerts.
- [ ] `Clear non-error` and `Clear all` are tiny + danger style.
- [ ] Alert list can scroll in expanded mode for long message sets.

### 4) Page Layout/Scroll
- [ ] No blank vertical scroll region at bottom of page.
- [ ] Status meta remains vertically centered in dock.
- [ ] IDE and Tune tab switching preserves layout integrity.

### 5) Tabs + Startup
- [ ] App opens on IDE tab by default.
- [ ] Tab order is IDE first, Tune second.

## Functional Smoke Checks
- [ ] Arm/Disarm actions still behave correctly.
- [ ] E-Stop latch/reset still behaves correctly.
- [ ] PID/MOTION/SETPOINT apply actions return expected status updates.
- [ ] Codex chat send still works and responses arrive.

## Issue Log
| ID | Area | Steps to Reproduce | Expected | Actual | Severity |
|----|------|--------------------|----------|--------|----------|
| 1  |      |                    |          |        |          |
| 2  |      |                    |          |        |          |
| 3  |      |                    |          |        |          |

## Exit Criteria
- [ ] No blocking layout bugs.
- [ ] No runtime crashes.
- [ ] No critical telemetry/HUD regressions.
- [ ] All high-severity issues logged with repro steps.

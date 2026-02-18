# Release Runbook

## Pre-Release
1. Firmware compile and smoke check.
2. app_bridge API smoke check.
3. Commissioning run passes all gates.

## Release Criteria
- No safety rule violations.
- Pass all KPI categories (recovery, hold, position).
- Export commissioning artifacts.

## Rollback
- Revert to last known-good tagged commit.
- Re-run commissioning before field use.

# Incident Playbook

## Trigger
Unexpected fault, runaway behavior, or control loss.

## Immediate Action
1. `DISARM` immediately.
2. Verify motors are zero output.
3. Capture last status and recent serial lines.

## Triage
1. Confirm state transition and fault source.
2. Validate power/serial integrity.
3. Re-run commissioning checks in order.

## Required Incident Bundle
- Last `STATUS` snapshot.
- Recent serial lines.
- Latest commissioning CSV + metrics JSON.
- Firmware/app commit hash.

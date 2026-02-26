# Pre-Arm Hardware Signoff

Purpose: produce a binary pass/fail pre-arm safety signoff artifact for a real hardware session.

## Scope

- Verifies stand confirmation, wheel pulse sanity (auto firmware probe or manual confirmation), and E-STOP latch/unlatch checks.
- Writes immutable JSON evidence under `.runlogs/prearm_signoff/`.

## Command

```bash
BOT_ON_STAND_OK=1 ./tools/lean/check_prearm_signoff.sh
```

## Optional Overrides

- `BASE=http://127.0.0.1:8797`
- `AUTO_WHEEL_PROBE=1` (default)
- `AUTO_ESTOP_PROBE=1` (default)
- `WHEEL_PROBE_RETRIES=3`
- `WHEEL_PROBE_PWM=110`
- `WHEEL_PROBE_MS=160`

Manual wheel confirmation mode:

```bash
BOT_ON_STAND_OK=1 AUTO_WHEEL_PROBE=0 LEFT_WHEEL_PULSE_OK=1 RIGHT_WHEEL_PULSE_OK=1 ./tools/lean/check_prearm_signoff.sh
```

## Acceptance Criteria

1. Script exits `0`.
2. Output contains `PASS`.
3. Artifact file exists in `.runlogs/prearm_signoff/prearm_signoff_*.json`.
4. Artifact shows:
   - `.prearm_check.ok == true`
   - `.prearm_safety.passed == true`
   - all `.prearm_check.checks[].status == "pass"`

## Failure Triage

1. Keep robot on stand, then rerun with same command once.
2. If fail persists, review failed check ids from script output.
3. Attach artifact file and `firmware last log` output to the scorecard evidence note.


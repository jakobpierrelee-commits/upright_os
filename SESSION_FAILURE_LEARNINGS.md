# Session Failure Learnings

## Why This Exists
This log captures failure modes from the initial build/tuning session and the engineering changes made to prevent recurrence.

## Failure Catalog and Fixes

1. Serial monitor chatter blocked command usability
- Symptom: continuous CSV made interactive control hard.
- Fix: explicit `LOGCSV 0/1` and burst-based logging workflow.

2. Wrong balance axis / sign confusion
- Symptom: robot interpreted posture incorrectly and faceplanted.
- Fix: explicit axis and polarity controls (`AXIS`, `SWAPAXIS`, `IMUPOL`, `MOTORPOL`) and persistent config.

3. Zero reference drift across reboots
- Symptom: repeated manual re-zero needed.
- Fix: EEPROM-backed config + `SAVECFG/LOADCFG`; commissioning includes `CAL ZERO`.

4. Single encoder behavior (right channel inactive)
- Symptom: `encR=0`, no dual-wheel odometry.
- Fix: temporary `ENCMODE LEFT` fallback; encoder checks evaluate by mode.
- Remaining gap: hardware or mapping fix for right encoder path.

5. False commissioning failures due to hand-holding noise
- Symptom: high mean/max angle and drift while manually stabilizing.
- Fix: explicit upright support posture, re-zero right before burst, and fixture discipline.

6. Upload/runtime instability with battery + USB combination
- Symptom: flash failures or inconsistent behavior while external power connected.
- Fix: standard operating rule: separate flash conditions from powered run conditions and verify mode transitions after reconnect.

7. Runner startup timeout on slow boot/help output
- Symptom: `Firmware did not become ready (no STATUS response)`.
- Fix: increased readiness timeout and confirmed boot output sequence.

8. “PASS but no motor motion” ambiguity
- Symptom: balance metrics passed with negligible command output.
- Fix: added separate deterministic motor pulse validation phase and metric (`motor_pulse_ok`).

9. Burst fallback necessity
- Symptom: `BURSTCSV` occasionally produced zero lines.
- Fix: fallback timed capture path with `LOGCSV 1` for robust data collection.

## Process Improvements Locked In
1. Separate checks for:
- Sensor/posture stability,
- Actuator responsiveness,
- Closed-loop balance quality.

2. Every run saves structured artifacts:
- CSV timeseries,
- JSON metrics.

3. Pass criteria require all of:
- encoder check,
- motor pulse check,
- burst metrics check.

## Open Risks
1. Right encoder path unresolved.
2. Bench support pass does not guarantee ground-contact nudge recovery.
3. Serial reset behavior can still affect host orchestration timing.

## Next Prevention Actions
1. Hardware fix for right encoder.
2. Add ground-contact scenario suite (nudge forward/backward/hold).
3. Build app bridge with explicit command ack/retry and session-state model.

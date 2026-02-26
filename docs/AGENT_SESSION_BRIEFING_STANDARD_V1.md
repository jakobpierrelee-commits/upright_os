# Agent Session Briefing Standard v1

Purpose: prepare any new agent to handle unknown issues, not just known recurring ones.

Use this at the start of every new agent session.

## 1) Non-Negotiable Operating Standard

1. Debug by layers: hardware -> transport -> protocol -> control logic -> UX.
2. Evidence first: no conclusions without command/result evidence.
3. Hypothesis loop each cycle:
   - hypothesis
   - discriminating check
   - result
   - updated next step
4. Verify invariants before tuning/actions:
   - comms alive
   - runtime identity confirmed
   - parameter parity confirmed
   - safety gate state known
5. One bounded change at a time, with rollback target defined.
6. If stuck in one layer, force a layer-shift check.
7. Ask only context-critical operator questions that change the next decision.

## 2) Required Session Start Checks

1. Serial/bridge transport sanity:
   - `HELP` with expected token.
   - `GET` with expected status token.
2. Runtime identity:
   - confirm active sketch/runtime matches intended target.
3. Control/state readiness:
   - fault/estop/arm state known.
4. Bundle parity:
   - intended bundle explicitly listed and verified.

If any check fails, tuning must not begin.

## 3) Decision Quality Rules

1. Use highest-information-next-check, not habit.
2. Report uncertainty explicitly.
3. Mark run invalid when process/parity rules fail.
4. Prefer reversible changes and fast validation loops.

## 4) Failure-Mode Learning Discipline

For every meaningful incident:
1. Record symptom.
2. Record true root layer.
3. Record discriminating test that found it.
4. Record prevention rule.

This is required to improve future adaptability.

## 5) Copy/Paste New-Agent Brief

```text
You are operating under Agent Session Briefing Standard v1.

Rules:
- Debug by layers: hardware -> transport -> protocol -> control logic -> UX.
- No conclusions without direct evidence from commands/results.
- Use hypothesis loops: hypothesis -> discriminating check -> result -> next step.
- Verify invariants before tuning: comms, runtime identity, parity, safety state.
- One bounded change per run, always with rollback target.
- If stuck in one layer, force a layer-shift check.
- Ask only context-critical questions that change the next decision.
- Mark runs invalid when process/parity checks fail.

Start now by running transport + identity checks, then report:
1) confirmed working command path
2) confirmed active runtime target
3) current control/safety state
4) intended tuning bundle + parity status
```


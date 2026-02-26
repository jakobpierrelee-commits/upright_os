# Codex Investigation: Testing & Iteration Tooling for UpRight.os

## Governing Documents
**Read these first and follow their rules throughout this task:**
- `/.codexrules` — Agent identity, behavior rules, domain expertise
- `/docs/PRD_CODEXRULES.md` — Full specification for the rules system

## Context
UpRight.os is a self-balancing robot platform with:
- **Firmware:** Arduino Nano running PID+Kalman balance controller (`tumbller_v06_nano_balance_v2.ino`)
- **Bridge:** Python serial gateway + API (`app/bridge/`)
- **Commissioning:** Automated 5-phase validation pipeline
- **UI:** React ops-console (`app/ui/ops-console/`)

The system already captures CSV telemetry bursts and scores metrics. We want to accelerate iteration without investing in full physics simulation.

## Proposals to Investigate

### 1. Trace Replay Testing
**Concept:** Feed recorded CSV telemetry through control math in Python to verify outputs match firmware behavior.
- Catches math bugs without modeling physics
- Enables regression testing against known-good sessions

### 2. Automated Parameter Sweep
**Concept:** Script that iterates gain combinations on real hardware:
`PID x y z` → wait for burst → score metrics → log → repeat
- Automates tuning exploration
- Builds dataset of gain→performance mappings

### 3. Control Math Unit Tests
**Concept:** Port Kalman filter and PID logic to Python, write unit tests with synthetic inputs.
- Validates edge cases (integrator windup, divide-by-zero, saturation)
- Enables CI without hardware

### 4. Interactive Gain Playground (Simple)
**Concept:** A minimal web-based or CLI tool where users can adjust Kp, Ki, Kd, Kv, Kx via sliders/inputs and instantly see how they affect a simulated response.
- **No physics engine required** — use a simplified 2D inverted pendulum model or just plot the PID transfer function response
- **Visual feedback** — show step response, overshoot, settling time as gains change
- **Learning tool** — helps operators build intuition before touching real hardware
- Could live in ops-console as a "Sandbox" tab or standalone HTML file

### 5. Voice Input for Codex Agent
**Concept:** Add a mic button to the CodexPanel so users can speak commands instead of typing.
- **Web Speech API** — uses built-in browser `SpeechRecognition` (Chrome/Edge/Safari), no external dependencies
- **Integration point:** `CodexPanel.tsx` already has `aiInput`/`setAiInput`/`sendAi` — voice just populates the input field
- **UX flow:**
  1. User clicks mic button → starts listening
  2. Speech transcribed → fills `aiInput` textarea
  3. User reviews transcript → clicks send (or auto-send option)
- **Bonus:** Add text-to-speech for assistant responses (optional)
- **Reference:** `app/ui/ops-console/src/features/codex/CodexPanel.tsx` lines 480-495 (send row)

## Your Task

1. **Investigate the codebase:**
   - Review `app/bridge/` for existing serial protocol and commissioning logic
   - Review `tumbller_v06_nano_balance_v2.ino` for control math to port
   - Check `tests/` for existing test patterns
   - Identify reusable infrastructure (CSV parsing, metric scoring, serial comms)

2. **Evaluate each proposal:**
   - Effort estimate (hours/days)
   - Dependencies on existing code
   - Expected ROI for iteration speed
   - Risk/complexity

3. **Decision:**
   - If **any proposal scores high ROI with reasonable effort**, generate a PRD following the format below.
   - If **none are worth it**, explain why and suggest alternatives.

## PRD Format (if proceeding)

```
# PRD: [Feature Name]

## Problem Statement
[What pain point does this solve?]

## Success Criteria
- [ ] Measurable outcome 1
- [ ] Measurable outcome 2

## Scope
### In Scope
- ...

### Out of Scope
- ...

## Technical Approach
[Architecture, key components, integration points]

## Implementation Plan
| Phase | Deliverable | Effort |
|-------|-------------|--------|
| 1     | ...         | Xh     |

## Risks & Mitigations
| Risk | Mitigation |
|------|------------|

## Exit Criteria
[How do we know this is done?]
```

## Constraints
- Follow existing code patterns in `app/bridge/`
- Do not introduce new dependencies without justification
- PRD must be executable in ≤2 sprints
- Prioritize tooling that works with real hardware over pure simulation

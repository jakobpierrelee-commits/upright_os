# PRD: Hardware-in-the-Loop Iteration Toolkit (Trace Replay + Parameter Sweep)

## Problem Statement
PID and motion tuning currently rely on manual command/testing loops. UpRight.os already has strong telemetry capture (`CSV` bursts, commissioning metrics, `observe_telemetry`, `read_burst_capture`), but we do not yet have a repeatable, automated loop for quickly comparing parameter changes against known-good behavior. This slows iteration and makes regressions hard to detect early.

## Success Criteria
- [ ] A scripted gain sweep can run on real hardware and produce ranked results (top configurations by stability score) in one command.
- [ ] A trace replay harness can run in CI against recorded CSV traces and fail when control-output deltas exceed thresholds.
- [ ] Control math unit tests cover Kalman update + PID edge cases (dt guards, integrator clamp, saturation) with deterministic fixtures.
- [ ] End-to-end tooling is usable by operators without introducing new runtime dependencies beyond current Python stdlib + existing project deps.

## Scope
### In Scope
- Proposal 1 (Trace replay): deterministic replay runner using recorded CSV bursts and a Python reference control path.
- Proposal 2 (Automated parameter sweep): hardware loop that applies candidate gains, runs short burst/observe windows, scores, logs, and ranks.
- Proposal 3 (Control math unit tests): firmware-parity unit tests for Kalman and PID primitives.
- Common scoring/report schema to compare runs over time.
- CLI-first implementation integrated with existing `tools/` patterns.

### Out of Scope
- Full physics simulation or digital twin.
- New firmware command protocol changes.
- Replacing current commissioning flow.
- Proposal 4 interactive playground UI in this PRD implementation window (kept as later follow-on).

## Technical Approach
Use existing infrastructure instead of introducing new systems:

- Reuse serial + command path:
  - `app/bridge/serial_gateway.py` (`NanoSerialGateway`, queueing, busy detection, health metrics).
  - `tools/commissioning_runner.py` command sequencing and burst collection patterns.
- Reuse telemetry parsing/scoring patterns:
  - `tools/commissioning_runner.py` (`CsvSample`, `evaluate()`).
  - `app/bridge/codex_tools.py` (`_tool_observe_telemetry`, `_tool_read_burst_capture`, FFT/peak detection helpers).
- Reuse existing fixtures/test style:
  - `app/bridge/tests/test_codex_t1_tools.py`, `app/bridge/tests/fixtures/*`.
- Firmware parity source:
  - `tumbller_v06_nano_balance_v2/tumbller_v06_nano_balance_v2.ino` (`kalmanUpdate`, loop PID + integrator clamp, output constrain).

Planned components:
1. `tools/trace_replay_runner.py`
- Inputs: CSV trace(s), baseline params, optional candidate params.
- Implements Python reference math path aligned with firmware update order.
- Outputs: JSON report with delta metrics (angle error trajectory, output mismatch, settle/overshoot proxies), pass/fail gates.

2. `tools/param_sweep_runner.py`
- Inputs: gain ranges/grids for `kp/ki/kd` (optionally `kv/kx`), trial duration, safety limits.
- Loop: apply command (`PID ...`), short stabilize wait, capture burst/observe, score, optional auto-rollback.
- Outputs: ranked CSV/JSON of config -> score/metrics; resume support via run manifest.

3. `app/bridge/tests/test_control_math_parity.py`
- Unit tests for Kalman + PID math primitives with deterministic fixtures.
- Explicit edge-case tests: tiny/zero `dt`, integrator windup clamp, saturation boundaries, derivative behavior.

4. Shared scoring utility
- New lightweight module (e.g. `app/bridge/control_metrics.py`) for consistent metric computation across replay and sweep.
- No new third-party dependencies.

### Proposal Evaluation Summary
| Proposal | Effort | Dependencies | ROI | Risk/Complexity |
|----------|--------|--------------|-----|-----------------|
| 1. Trace Replay Testing | 2-3 days | Existing CSV fixtures, firmware math extraction, scoring utility | High (fast regression detection in CI) | Medium (firmware-parity drift risk) |
| 2. Automated Parameter Sweep | 3-5 days | Serial gateway, safe command path, burst/observe scoring | Very High (major iteration speedup on real hardware) | Medium-High (hardware safety/timeouts) |
| 3. Control Math Unit Tests | 1-2 days | Firmware math parity module + pytest fixtures | High (prevents math regressions) | Low-Medium |
| 4. Interactive Gain Playground | 4-7 days | UI work, simulation model, visualization | Medium (learning value, lower immediate tuning throughput) | Medium |

Decision: Execute 1+2+3 in this PRD (high ROI, reasonable effort, hardware-first). Defer 4.

## Implementation Plan
| Phase | Deliverable | Effort |
|-------|-------------|--------|
| 1 | Extract firmware-parity math module + control math unit tests | 12h |
| 2 | Build trace replay runner + fixture-based regression tests | 16h |
| 3 | Build hardware parameter sweep runner with scoring/ranking and safety guardrails | 24h |
| 4 | Wire docs + runbook + acceptance scripts and sample outputs | 8h |

Total estimated effort: 60h (fits <= 2 sprints).

## Risks & Mitigations
| Risk | Mitigation |
|------|------------|
| Firmware and Python replay math drift apart over time | Add parity tests pinned to firmware equations and update checklist when firmware control loop changes |
| Sweep runner can destabilize robot with unsafe gain combos | Enforce bounded ranges, command allowlist, estop/mode checks, immediate rollback on fail criteria |
| Serial contention with bridge | Reuse gateway `is_busy` checks and run sweep in explicit maintenance mode |
| Noisy traces produce false regression failures | Use robust thresholds/tolerances and require repeated fail before gating |
| Operator adoption friction | Provide one-command defaults and simple ranked report output |

## Exit Criteria
Done when all are true:
- `trace_replay_runner` passes on known-good traces and catches seeded regressions.
- `param_sweep_runner` can execute at least 20 configs in one unattended run and produce ranked results.
- New control-math parity test suite runs in CI and passes.
- A short operator runbook exists with commands, safety constraints, and interpretation guidance.

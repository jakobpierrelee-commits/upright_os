# Risk Register

Purpose: track known failure modes, ownership, mitigations, and decision points.

Last updated: `2026-02-23`
Owner: `Codex + JVKE`

Status values: `Open`, `Mitigated`, `Monitoring`, `Closed`
Severity values: `High`, `Medium`, `Low`
Probability values: `High`, `Medium`, `Low`

## Active Risks

| ID | Risk | Severity | Probability | Status | Trigger / Signal | Mitigation | Scorecard Link |
|---|---|---|---|---|---|---|---|
| R-001 | `server.py` monolith causes hidden regressions during feature work | High | Medium | Monitoring | Route edits change unrelated behavior | Continue slice extraction with no-contract-change tests and CI gates | `#26`, `#27`, `#29`, `#30` |
| R-002 | Clean route/UI contract drift causes blocked actions or stale screens | High | Medium | Monitoring | UI shows connected but actions fail/outdated API | Keep `clean_api` gate, strict contract validators, and SSE checks in CI | `#20`, `#30` |
| R-003 | Bridge mode/process mismatch causes intermittent disconnects | High | Medium | Monitoring | Bridge down or flapping after tool actions | Standardize restart/runbook paths; use local bridge health checks before actions | `#1`, `#5`, `#17` |
| R-004 | Upload path can target wrong board/port in multi-device setups | High | Medium | Monitoring | Unexpected port switch or upload to wrong board | Keep detect/precheck flow, explicit board+bootloader selection, recovery guidance | `#7`, `#18`, `#25` |
| R-005 | Pre-arm hardware gate may fail due firmware/runtime sequencing | High | Medium | Open | `Pre-Arm failed`, `unsafe_state`, `fault` loops | Keep fail-closed, improve firmware handshake and test sequencing evidence | `#21` |
| R-006 | Codex login transient probe failures degrade UX | Medium | Medium | Mitigated | temporary login status errors | Use cached stale-login fallback for transient probe errors | `#26` |
| R-007 | UI megafiles slow safe iteration and increase regressions | Medium | High | Open | slow development cadence, coupling in `App.tsx` | Stage split by domain panels/hooks with no-behavior-change tests | `#28` |
| R-008 | Tuning suggestions may be low confidence without telemetry completeness | Medium | Medium | Open | vague or unsafe tuning output | Add tuning quality gate + scenario acceptance tests | `#22`, `#23` |

## Escalation Rules

1. Any `High` severity risk with `Open` status blocks unrelated scope expansion.
2. If a risk repeats twice in one session, create/update a decision record in `docs/DECISIONS.md`.
3. If mitigation touches behavior, add explicit acceptance checks before merge.

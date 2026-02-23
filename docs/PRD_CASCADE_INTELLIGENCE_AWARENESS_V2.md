# PRD: Cascade Intelligence + Environment Awareness V2

**Version:** 1.0
**Status:** Proposed
**Owner:** UpRight.os Agent Track
**Last Updated:** 2026-02-19
**Primary Branch:** `recover/uiux-restore-2026-02-19`

---

## 1. Objective

Build a production-grade assistant runtime that matches high-performing coding copilots on:

1. Mission memory continuity across long sessions.
2. Backend/environment awareness that adapts to telemetry remaps, strategy updates, and firmware evolution.
3. Strict safety and action policy enforcement.
4. Deterministic response quality under regression tests.

Target outcome: the in-app Codex assistant is reliable enough to be the default operator interface for tuning, diagnostics, and firmware workflows.

---

## 2. Problem Statement

Current runtime quality improved materially through prompt and history tuning, but is still below target under sustained adversarial evaluation.

Observed benchmark progression (100Q headless drill):

- 10/100 (baseline)
- 31/100 (prompt + continuity pass 1)
- 62/100 (continuity + memory pass 2)
- 70/100 (policy + contract hardening)

Remaining failures cluster in:

- memory recall under long thread pressure,
- strict project-specific factual adherence,
- contract-specific wording/response format misses.

Root issue: behavior still relies too heavily on model-only inference instead of deterministic system layers.

---

## 3. Product Principles (Non-Negotiable)

1. Safety over speed.
2. Verify before claim.
3. Deterministic contracts over implicit behavior.
4. Additive, reversible changes.
5. No silent fallback on state-critical operations.
6. No monkey patches.

---

## 3.1 Windsurf Rebuild Alignment (Explicit)

This iteration follows the same strategy a production Windsurf/Cascade rebuild would use:

1. Contracts-first:
- Assistant behavior, state, and safety are formal contracts before feature work.

2. Deterministic eval-first:
- 100Q behavioral eval is treated as a release gate, not an optional report.

3. Memory/control-plane separation:
- Mission memory is a durable subsystem, not only chat history context.

4. Policy middleware:
- Pre/post-generation policy enforcement is deterministic and testable.

5. Observability by default:
- Every turn emits traceable policy/evidence metadata for debugging.

6. Recoverability and safe rollback:
- Atomic state operations, explicit fallback rules, and no silent thread-state recovery.

7. Ship on thresholds:
- Merge/release conditioned on category and aggregate score floors.

---

## 4. Scope

### 4.1 In Scope

1. Durable mission memory subsystem independent of chat window length.
2. Adaptive capability/contract awareness fed from backend registries and docs contracts.
3. Response policy middleware (pre and post generation).
4. Evidence-backed claim validation for risky statements.
5. Continuous evaluation pipeline with release gates.

### 4.2 Out of Scope (This Iteration)

1. New control algorithms in firmware.
2. Replacing current model provider.
3. Full autonomous execution without operator confirmation gates.

---

## 5. Requirements

### R1. Durable Mission Memory Plane

Assistant must persist and use canonical mission facts separate from thread text.

Required capabilities:

- Structured store keyed by session/user/project.
- Canonical fields: branch, target, guardrail, priority, board_imu, telemetry_profile_version, strategy_pack_version.
- Explicit upsert/clear operations.
- Automatic injection on every relevant turn.
- Read-after-write consistency guarantees.

### R2. Adaptive Environment Awareness Plane

Assistant must track backend changes without manual prompt rewrites.

Required capabilities:

- Contract Registry source of truth (telemetry fields, command expectations, profile versioning).
- Strategy Registry for tuning heuristics and playbook variants.
- Capability Registry for available tools/endpoints and risk level.
- Runtime adapter layer translating legacy aliases and remapped fields.

### R3. Policy Middleware

Model output must pass deterministic policy checks before returning to UI.

Required checks:

- length/format constraints (one-sentence modes),
- high-risk action gating language,
- forbidden claim detection (executed action without evidence),
- project fact enforcement for known prompt classes,
- thread continuity metadata consistency.

### R4. Evidence-Coupled Claims

If assistant claims state/action, it must include or internally log source evidence.

Examples:

- telemetry claim -> last status timestamp + source,
- tool action claim -> tool audit record,
- thread claim -> thread_id continuity check.

### R5. Evaluation as Release Gate

Every merge affecting assistant behavior must run and publish evaluation artifacts.

Minimum gates:

- 100Q behavior drill,
- safety subset score,
- memory continuity subset score,
- no regression against prior baseline beyond agreed threshold.

---

## 6. System Architecture (Target)

### 6.1 Components

1. `MissionMemoryStore`
- persistent canonical memory (SQLite JSON table or dedicated JSON with checksum/rotation).

2. `AwarenessRegistry`
- unified view of:
  - telemetry contracts,
  - tool capabilities,
  - strategy packs,
  - firmware profile mappings.

3. `PromptAssembler`
- deterministic assembly order:
  1) immutable system policy,
  2) mission memory facts,
  3) awareness registry snapshot,
  4) bounded thread history,
  5) live context,
  6) user message.

4. `ResponsePolicyEngine`
- validates and normalizes model output before return.

5. `ClaimVerifier`
- checks evidence links for state/action claims.

6. `EvalHarness`
- executes benchmark suites and publishes machine-readable reports.

7. `ReleaseGateController`
- enforces CI thresholds (`overall`, `safety`, `memory`) before merge.

### 6.2 Data Flow

`UI request -> Thread resolver -> Mission memory load -> Awareness snapshot -> PromptAssembler -> Model -> PolicyEngine -> ClaimVerifier -> Response -> Persist + Audit`

---

## 7. Contracts

### 7.1 Mission Memory Contract

```json
{
  "branch": "recover/uiux-restore-2026-02-19",
  "target": "embedded vectoring reliability",
  "guardrail": "no monkey patches",
  "priority": "safety over speed",
  "board_imu": "Arduino Nano + MPU6050",
  "updated_at": 1771527687.0,
  "source": "user_asserted"
}
```

### 7.2 Awareness Snapshot Contract

```json
{
  "telemetry_contract": {"version": "v2", "required_v1": [...], "required_v2": [...]},
  "tool_capabilities": [{"name": "search_docs", "risk": "low"}],
  "strategy_pack": {"version": "2026.02", "profiles": ["balance_v2"]},
  "firmware_profiles": [{"id": "upright_nano_balance_v2", "status": "active"}]
}
```

### 7.3 Policy Decision Contract

```json
{
  "pass": true,
  "adjustments": ["trimmed_to_one_sentence"],
  "violations": [],
  "evidence_refs": ["tool_audit:12345"]
}
```

---

## 8. Implementation Plan

### Phase A (P0) - Deterministic Memory + Policy Base

1. Introduce `MissionMemoryStore` with tests.
2. Move current mission fact extraction to explicit persisted memory upsert.
3. Add `ResponsePolicyEngine` v1:
- one-sentence mode enforcement,
- high-risk gating phrase enforcement,
- forbidden-claim checks.
4. Add per-turn debug trace fields (thread_id, memory_version, policy_result).

Exit criteria:

- Memory recall subset >= 95%.
- No thread continuity regressions.

### Phase B (P1) - Adaptive Awareness Registry

1. Implement `AwarenessRegistry` loader from contracts/docs/runtime endpoints.
2. Add alias/remap adapter for telemetry and strategy keys.
3. Inject awareness snapshot into prompt pipeline with version tags.

Exit criteria:

- State-readiness subset >= 85%.
- Sketch/tooling factual subset >= 85%.

### Phase C (P2) - Claim Verifier + Normalization

1. Add evidence-linked claim verification.
2. Add response normalization for known prompt classes.
3. Add automated fallback behavior when evidence unavailable (admit uncertainty, request specific check).

Exit criteria:

- Safety subset >= 95%.
- Logic subset >= 95%.

### Phase D (P3) - Release Gate + Ops

1. Promote 100Q drill to mandatory CI gate for assistant-impacting PRs.
2. Publish trend dashboard artifact (`tests/results/agent_eval_trend.json`).
3. Add rollback criteria and canary release flow.

Exit criteria:

- Overall 100Q score >= 85% for 3 consecutive runs.

---

## 9. Success Metrics

Primary:

1. 100Q pass rate >= 85%.
2. Memory recall category >= 95%.
3. Safety category >= 95%.
4. Zero critical policy violations in production logs.

Secondary:

1. P95 response latency <= 12s under normal load.
2. Thread continuity failures <= 0.5% of turns.
3. False environment-limit claims == 0.

Release thresholds (mandatory):

1. Overall 100Q >= 85%.
2. Safety >= 95%.
3. Memory recall >= 95%.
4. No category below 85% for two consecutive candidate releases.

---

## 10. Testing Strategy

### 10.1 Required Test Suites

1. Unit tests:
- mission memory persistence,
- awareness registry parsing,
- policy engine rules,
- claim verifier evidence linking.

2. Integration tests:
- `/ai/chat/tools` with long-thread continuity,
- stale thread behavior,
- memory write/read across turns,
- telemetry alias remap compatibility.

3. Behavioral eval:

```bash
python3 scripts/agent_100q_drill.py --base http://127.0.0.1:8787
```

4. Regression gate:

```bash
python3 scripts/prd_traceability_check.py --run-tests --output traceability.json
python3 scripts/embedded_vectoring_smoke.py --base http://127.0.0.1:8787
```

5. Merge gate policy:
- PR cannot merge if any mandatory threshold in Section 9 fails.

---

## 11. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Prompt bloat reduces model focus | Lower factual accuracy | Keep injected memory/awareness compact + versioned summaries |
| Policy engine over-constrains useful output | Reduced operator utility | Class-based policies + allowlist exceptions with tests |
| Registry drift from backend truth | Incorrect guidance | Single source registries + checksum/version validation |
| High eval variance | Unstable release decisions | Require rolling 3-run average and category floors |

---

## 12. Rollout and Rollback

### Rollout

1. Ship Phase A behind feature flag (`assistant_policy_v2`).
2. Canary to internal sessions only.
3. Expand after category thresholds met.

### Rollback

1. Disable `assistant_policy_v2` flag.
2. Revert to previous prompt path.
3. Preserve new traces for postmortem.

---

## 13. Definition of Done

This PRD iteration is done when:

1. Overall 100Q >= 85% for 3 consecutive runs.
2. Memory recall failures reduced to zero in the 100Q suite.
3. Safety and logic categories each >= 95%.
4. Adaptive awareness updates work without manual prompt edits when telemetry/strategy mappings change.
5. CI gate is mandatory for assistant-impacting merges.

Additionally, done requires explicit evidence that each Windsurf rebuild alignment item in Section 3.1 is implemented and test-covered.

---

## 14. Changelog

| Date | Version | Changes |
|---|---|---|
| 2026-02-19 | 1.0 | Initial PRD for intelligence and environment-awareness hardening |

---

## 15. Appendix A - Execution Checklist (Strategy -> Code)

Use this checklist as the implementation control plane for this PRD.

| Strategy Item | Required Implementation | Primary Files | Endpoint/Surface | Required Tests | Gate |
|---|---|---|---|---|---|
| Contracts-first | Assistant/State/Safety contracts encoded and versioned | `app/bridge/server.py`, `docs/contracts/telemetry_contract_v2.md` | `/ai/chat/tools` | Contract parser + endpoint integration tests | Must pass |
| Deterministic eval-first | 100Q harness + CI-readable artifacts | `scripts/agent_100q_drill.py` | CLI (`tests/results/*.json`) | Harness smoke test + regression trend test | Must pass |
| Memory/control-plane separation | Durable mission memory store (non-thread-only) | `app/bridge/server.py` (MissionMemoryStore), `app/bridge/codex_agent.py` | `/ai/chat/tools` prompt assembly | Mission memory CRUD + long-thread recall tests | >=95% memory subset |
| Policy middleware | Pre/post output policy validation + normalization | `app/bridge/server.py` (policy), `app/bridge/codex_agent.py` | `/ai/chat/tools`, `/ai/chat` | One-sentence enforcement + forbidden-claim tests | Safety >=95% |
| Observability by default | Per-turn trace metadata and policy decisions | `app/bridge/server.py`, `app/bridge/codex_db.py` | `/tooling/traces`, logs | Trace schema + completeness tests | No missing critical fields |
| Recoverability | Atomic writes, no silent fallback, deterministic rollback | `app/bridge/server.py`, `app/bridge/tests/test_thread_api_integration.py` | Thread + apply paths | stale-thread, rollback, atomic persistence tests | Must pass |
| Ship on thresholds | Merge blocker on eval thresholds | `scripts/prd_traceability_check.py` + CI config | CI pipeline | threshold comparator tests | Overall >=85% |

### 15.1 Immediate Start Sequence (Next 1-2 Days)

1. Implement `MissionMemoryStore` persistence with checksum and rotation.
2. Inject memory snapshot on every `/ai/chat/tools` turn.
3. Add policy normalization layer for strict one-sentence modes.
4. Add category-level scoring output to 100Q harness.
5. Enforce provisional local gate: overall >=75% and safety >=90% before merge.

### 15.2 Definition of Ready for Any PR in This Track

1. References one or more rows in Section 15 with explicit IDs in PR description.
2. Includes tests listed in the matching row.
3. Includes updated benchmark artifact if assistant behavior changed.
4. Includes rollback note.

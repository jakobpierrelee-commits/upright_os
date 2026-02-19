# PRD: Embedded Vectoring (RAG + Agent Tooling)

**Version:** 1.1  
**Status:** Active (In Progress)  
**Owner:** UpRight.os Agent Track  
**Last Updated:** 2026-02-19  
**Primary Branch:** `recover/uiux-restore-2026-02-19`

---

## 1. Initial Goals (Unchanged)

The original objective remains:

1. Ground agent responses with project-specific docs/code context (RAG).
2. Keep tool execution safe (allowlists, confirmations, busy guards, bounded retries).
3. Preserve conversational continuity (thread/history persistence).
4. Expose transparent tool activity in UI (what ran, why, result).
5. Maintain low-friction local operation (SQLite-backed, minimal external dependencies).

Success condition is not "RAG exists"; success is an end-to-end, reliable operator workflow:

`chat request -> relevant context -> safe tool execution (when needed) -> clear UI feedback -> persisted audit trail`.

---

## 2. Current State Snapshot

### 2.1 Implementation Matrix

| Capability | Status | Notes | Key Files |
|---|---|---|---|
| RAG core (chunk/embed/search) | Implemented | Search path operational; SQLite-backed chunk storage | `app/bridge/codex_rag.py`, `app/bridge/codex_db.py` |
| `search_docs` tool wiring | Implemented | Tool exposed via executor | `app/bridge/codex_tools.py` |
| Agent loop with tool calls | Implemented | Iterative tool-call loop + cap | `app/bridge/codex_agent.py` |
| Tool safety allowlists | Implemented | Command/edit restrictions in place | `app/bridge/codex_tools.py` |
| Firmware upload confirmation gate | Implemented | UI confirmation modal present | `app/ui/ops-console/src/features/codex/UploadConfirmModal.tsx` |
| Serial busy protection (critical paths) | Implemented | Added busy guards + retry hint in rollback/experiment paths | `app/bridge/codex_tools.py`, `app/bridge/tests/test_codex_t2_tools.py` |
| Tool execution UI transparency | Implemented | Tool call cards shown in chat UI | `app/ui/ops-console/src/features/codex/ToolCallCard.tsx` |
| Thread/history persistence | Partial | Persisted thread store exists; robustness/ops hardening still evolving | `app/bridge/ai_threads.json`, `app/bridge/server.py` |
| RAG observability in UI | Partial | Backend endpoints exist; dedicated UI status/index affordances still limited | `app/bridge/server.py`, `app/ui/ops-console/src/api.ts` |
| Retrieval quality guardrails | Partial | Basic similarity thresholding exists; no stronger relevance eval loop yet | `app/bridge/codex_rag.py` |

### 2.2 Recent Developments Since v1.0

1. Busy-state safety hardening landed for key T2 tooling paths.
2. Busy-state tests expanded and passing.
3. Setup/deployment rig UX hardened to avoid layout growth from long diagnostics (fixed-height + internal scroll).
4. This PRD updated from "implemented" to an execution-accurate state model.

---

## 3. Architecture (Operational View)

### 3.1 Runtime Flow

1. User submits chat prompt in Codex panel.
2. Agent loop initializes with optional RAG context.
3. Model may request tool calls.
4. Tool executor enforces safety policy + serial busy checks.
5. Tool outputs are fed back to model for final response.
6. UI renders response + tool call cards.
7. Thread/history and audit data are persisted.

### 3.2 Core Components

| Component | Responsibility |
|---|---|
| `codex_agent.py` | Chat orchestration, tool-call loop, response assembly |
| `codex_tools.py` | Tool registry, safety enforcement, command execution |
| `codex_rag.py` | Corpus indexing, embedding/search, context packaging |
| `codex_db.py` | Structured persistence + audit/query support |
| `CodexPanel.tsx` | Operator chat surface + tool activity visibility |

---

## 4. Gaps To Close For "Pickup-and-Go" Reliability

### P0 (must close)

1. PRD-to-code traceability checks on each handoff (avoid optimistic drift).
2. Explicit RAG readiness surfacing in UI (index freshness + chunk/doc counts).
3. End-to-end regression gate command documented and run before handoff.

### P1 (next)

1. Retrieval quality harness (known queries + expected source hits).
2. Thread store hardening and backup/rotation strategy.
3. Better operator affordances for "why this tool ran" explanations.

### P2 (later)

1. Hybrid retrieval (semantic + keyword).
2. Source weighting/feedback loop.
3. Optional local embedding path for reduced API dependence.

---

## 5. Milestones

### M1: Stable Retrieval + Safe Tooling (current target)

- RAG search callable from tools.
- Tool loop reliable with busy guards on sensitive paths.
- UI displays tool outcomes with enough context for operator trust.
- Regression gate passes.

### M2: Operator Trust UX

- RAG status/index controls visible in UI.
- Retrieval evidence surfaced in agent responses.
- Thread/history management ergonomics improved.

### M3: Quality + Scale

- Retrieval quality benchmark in CI.
- Hybrid retrieval and dedupe improvements.
- Stronger failure recovery behavior.

---

## 6. Safe Pickup-and-Go Gate

Run this gate before handing off work or starting a new implementation sprint.

### 6.1 Branch/State Preconditions

```bash
git branch --show-current
git rev-parse --short HEAD
git status --short
```

Expected:
- On intended development branch.
- No unknown branch switches/reset activity.
- Runtime/generated artifacts may remain untracked but should be explicitly called out.

### 6.2 Traceability Check (automated)

```bash
python3 scripts/prd_traceability_check.py --output traceability.json
```

This generates a machine-readable JSON artifact mapping PRD capabilities -> source files -> tests -> status.

### 6.3 Regression Gate (minimum)

```bash
python3 -m pytest app/bridge/tests/test_codex_tools.py app/bridge/tests/test_codex_t2_tools.py -v
python3 -m pytest app/bridge/tests/test_codex_rag.py app/bridge/tests/test_codex_pr4_rag.py -v
cd app/ui/ops-console && npm test -- --run
```

Or run traceability check with tests:

```bash
python3 scripts/prd_traceability_check.py --run-tests --output traceability.json
```

### 6.4 Handoff Record Requirements

Each handoff must include:

1. Branch + commit SHA.
2. Exact files changed.
3. Exact test commands run + pass/fail counts.
4. Remaining P0/P1 risks.
5. Explicit "safe to continue from here: yes/no".

---

## 7. Risks and Controls

| Risk | Impact | Control |
|---|---|---|
| PRD drift from code reality | Wrong planning decisions | Require traceability matrix updates per sprint |
| Silent tool execution hazards | Unsafe robot/tooling behavior | Busy checks + allowlists + confirmation gates |
| Unclear model/tool provenance in UI | Operator distrust | Tool call cards + structured result payloads |
| Retrieval staleness | Low-quality answers | Explicit reindex flow + freshness indicators |
| Session-context confusion across branches | Lost time/regressions | Branch/state gate in every work cycle |

---

## 8. Definition of Done (for this PRD revision)

This PRD revision is considered complete when:

1. Document reflects actual implementation state (not aspirational-only).
2. Safe pickup-and-go gate is executable and validated in current branch.
3. Next P0 work is unambiguous for a fresh agent session.

---

## 9. Changelog

| Date | Version | Changes |
|---|---|---|
| 2026-02-19 | 1.0 | Initial PRD created from current codebase |
| 2026-02-19 | 1.1 | Reframed to execution-state PRD with gaps, milestones, and pickup-and-go verification gate |

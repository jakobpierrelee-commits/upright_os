# Delegation & Deployment Strategy

**Decision:** Whether to iterate on existing codebase or rebuild from scratch, and how to delegate across agents.

---

## Option Analysis

### Option A: Iterate on Existing
**Pros:**
- Preserves working safety features (PreArmSafetyGate, preflight)
- Keeps existing tests (55+ files)
- Lower risk — incremental changes
- Faster to first value

**Cons:**
- Technical debt accumulates
- server.py monolith slows development
- Some patterns are legacy

**Timeline:** 4-6 weeks to Phase 6

---

### Option B: Rebuild Core, Keep Firmware
**Pros:**
- Clean architecture from day one
- Modern patterns throughout
- Easier to maintain long-term
- Can incorporate all lessons learned

**Cons:**
- Higher upfront investment
- Risk of losing subtle safety behaviors
- Need to re-test everything

**Timeline:** 8-12 weeks to feature parity + Phase 6

---

### Option C: Hybrid (Recommended)
**Rebuild the layers that need it, keep the layers that work.**

| Layer | Action | Reason |
|-------|--------|--------|
| **Firmware** | Keep | Well-structured, versioned configs, working |
| **Serial Gateway** | Keep | Clean, 393 lines, works |
| **Safety (arm_safety.py)** | Keep | Critical, tested, don't touch |
| **Control Math** | Keep | Firmware-parity, correct |
| **Server.py** | Rebuild | 15k lines is unmaintainable |
| **Codex Agent** | Keep + Extend | Clean, just add tools |
| **Codex Tools** | Split + Extend | Too large, but logic is good |
| **Tuning Policy** | Keep + Extend | Foundation for new phases |
| **UI** | Rebuild progressively | Keep working, add new panels |
| **Database** | Keep + Extend | Schema is clean, just add tables |

---

## Recommended Deployment Strategy

### Phase Structure

```
Week 1: Foundation
├── Phase 0: Feature flags, migration strategy
└── Phase 1: TuningSession backend

Week 2: Core Features
├── Phase 1.5: UI Panel (can parallelize)
├── Phase 2: Step Response Analysis
└── Phase 3: D-Term Effectiveness

Week 3: Analysis Features
├── Phase 4: Noise Floor Spectrum
├── Phase 5: Session Continuity
└── Phase 6: Multi-Variable Handling

Week 4: Validation
├── Phase 6.5: Performance Validation
└── Integration testing on hardware

Week 5-6: Aerospace Features
├── Phase 7: Stability Margins
├── Phase 8: Monte Carlo
├── Phase 9: Regression Suite
└── Phase 10: Config Traceability

Week 7-8: Advanced Safety
├── Phase 11: Fault Injection
├── Phase 12: Safety Invariants
└── Phase 13: HIL Validation Gate

Week 9-10: ML Features
├── Phase 14: Neural Network Model
├── Phase 14.5: Model Lifecycle
├── Phase 15: Multi-Rule Comparison
└── Phase 16: FOPDT Model ID
```

---

## Agent Delegation Plan

### Agent Assignment Matrix

| Agent | Assigned Work | Why |
|-------|---------------|-----|
| **Cascade (Windsurf)** | Phases 0-6, 7-13, backend logic | Deep context, algorithm work |
| **Codex (Your AI)** | PRD review, architecture validation, testing strategy | Knowledge of codebase intent |
| **Augment Agent 1** | Server decomposition (parallel track) | Mechanical refactoring |
| **Augment Agent 2** | UI Panel (Phase 1.5) after backend ready | Frontend isolation |
| **Augment Agent 3** | Test generation, docs updates | Support work |

### Parallel Tracks

```
Track A (Cascade)              Track B (Augment)           Track C (Augment)
─────────────────              ────────────────            ────────────────
Phase 0: Flags                 Server decomp start         
Phase 1: Session DB      ────► Phase 1.5: UI Panel        Test generation
Phase 2: Step Response         Server decomp cont.         Doc updates
Phase 3: D-Term                routes/tuning.py done       
Phase 4: Noise Floor           routes/firmware.py done     
Phase 5: Session Cont.         Server decomp complete      
Phase 6: Multi-Variable        UI integration              
        │
        ▼
   [Merge + Integration Test]
```

---

## Concrete Handoff Specs

### Handoff to Augment: Server Decomposition

```markdown
# Server Decomposition Task

## Objective
Split server.py (15,350 lines) into focused route modules.

## Target Structure
app/bridge/
├── server.py (entry point, <500 lines)
├── routes/
│   ├── __init__.py
│   ├── tuning.py      # /pid, /motion, /limits, /setpoint
│   ├── firmware.py    # compile, upload, recovery
│   ├── codex.py       # AI chat, tools
│   ├── profiles.py    # Robot profiles
│   ├── commissioning.py
│   └── health.py      # /status, /health
├── core/
│   ├── control_state.py
│   ├── request_handler.py
│   └── middleware.py

## Rules
1. NO behavior changes — pure mechanical refactoring
2. All existing tests must pass
3. One route file per PR
4. Import from routes in main server.py

## Verification
pytest app/bridge/tests/ -v
```

### Handoff to Augment: UI Panel

```markdown
# Tuning Session Panel Task

## Objective
Create TuningSessionPanel.tsx for Phase 1.5

## Dependencies
- Phase 1 backend complete (TuningSession API exists)

## Endpoints to consume
GET  /api/tuning/session/active
POST /api/tuning/session/start
POST /api/tuning/session/compare
POST /api/tuning/session/end

## Component Structure
src/features/tuning/
├── TuningSessionPanel.tsx
├── BaselineComparisonCard.tsx
├── CandidateHistoryList.tsx
├── ForbiddenMovesBadges.tsx
└── TuningRecommendationCard.tsx

## Style Rules
- Use existing dark theme (no blue backgrounds)
- Follow patterns in CodexPanel.tsx
- Use strings.ts for all copy

## Verification
npm run test -- TuningSession
```

---

## Branch Strategy

```
main (protected)
├── develop
│   ├── feature/tuning-intelligence-phase-0
│   ├── feature/tuning-intelligence-phase-1
│   ├── feature/tuning-intelligence-phase-1.5
│   ├── refactor/server-decomposition
│   └── ...
```

### Merge Order
1. Phase 0 → develop (feature flags first)
2. Phase 1 → develop
3. Server decomposition → develop (after Phase 1 tests pass)
4. Phase 1.5 → develop (after Phase 1 merged)
5. Phases 2-6 → develop (sequential)
6. develop → main (after Phase 6.5 validation)

---

## Reset Points (If Needed)

### If Phase 1 Goes Wrong
- Rollback: `git revert` the Phase 1 commits
- Feature flag: Set `TUNING_V2_ENABLED=false`
- Data: New table is isolated, drop it

### If Server Decomposition Goes Wrong
- Rollback: Keep original `server.py` as `server_legacy.py`
- Switch back with symlink or import redirect

### If Full Rebuild Needed
1. Create `v2/` directory alongside existing code
2. Build new server with clean architecture
3. Feature flag switches between v1 and v2
4. Gradual migration of routes
5. Delete v1 when v2 is validated

---

## Immediate Next Steps

### Today
1. **You:** Give PRD to Codex for evaluation
2. **Cascade:** Start Phase 0 (feature flags)

### Tomorrow
3. **Cascade:** Start Phase 1 (TuningSession backend)
4. **Augment:** Start server decomposition (parallel)

### This Week
5. **Augment:** Start Phase 1.5 (UI Panel) once backend ready
6. **Cascade:** Continue Phases 2-4

---

## Go/No-Go Checklist

Before starting implementation:

- [x] PRD created and reviewed
- [x] Architecture audit complete
- [x] Operational phases added
- [x] Delegation strategy defined
- [ ] Codex evaluation received
- [ ] Branch created for Phase 0
- [ ] Feature flag infrastructure designed

---

## Your Decision Points

1. **Start now or wait for Codex review?**
2. **Use Augment for parallel tracks?**
3. **Server decomposition priority: parallel or after Phase 6?**
4. **Rebuild UI from scratch or extend existing?**

Let me know your decisions and I'll begin Phase 0 immediately.

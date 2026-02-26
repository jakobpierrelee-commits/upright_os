# Prompt for Codex (Windsurf AI Builder) - Copy/Paste Ready

---

Hi Codex! I'm coordinating a multi-agent effort to upgrade the UpRight.os AI tuning agent. I need your review and input on the plan before we start building.

## Context

**What we're building:** UpRight.os - a platform for tuning self-balancing robots

**What we're upgrading:** The built-in AI tuning agent that helps users tune their robots (currently has 9 basic tools, we're adding 8 advanced tools + ML intelligence)

**Who's working on this:**
- **Augment Agent:** Did codebase audit, found existing implementations
- **Claude (your colleague):** Will do implementation work
- **You (Codex):** Will help build and review architecture
- **JVKE:** Orchestrates and makes decisions

## What Augment Found

Good news: **3 advanced tools are already implemented** in the UpRight codebase:

### Already Built (in app/bridge/codex_tools.py):
- ✅ `observe_telemetry` (lines 1770-1900) - Live telemetry analysis
- ✅ `read_burst_capture` (lines 1987-2170) - Burst CSV with FFT
- ✅ `run_experiment` (lines 2671+) - A/B testing with auto-rollback
- ✅ All registered in TOOL_DEFINITIONS
- ✅ Tests exist in test_codex_t1_tools.py

### Not Yet Built:
- `diff_config` - Compare current config to checkpoint
- `safe_rollback` - One-click revert
- `simulate_pid_response` - Physics-based what-if
- `suggest_next_step` - ML recommendations
- `annotate_session` - Session notes/learning

## Review This Plan

Please review: **`docs/AGENT_ALIGNMENT_2026-02-25.md`**

## What I Need From You

### 1. Architecture Review

From a software architecture perspective:
- Does the plan make sense?
- Are there any architectural concerns?
- Any technical risks we should address?
- Better approaches to consider?

### 2. Implementation Priority

The plan presents 3 options:

**Option A: Quick Wins (1-2 days)**
- Verify the 3 existing tools work end-to-end
- Fix any bugs found
- Document usage patterns
- Then decide on Phase 1

**Option B: Foundation First (1 week)**
- Phase 0: Feature flags, migration strategy
- Phase 1: TuningSession backend (baseline/candidate A/B comparison)
- Test existing tools in parallel

**Option C: Parallel Tracks (1 week)**
- Claude: Phase 0+1 implementation
- Augment: Test existing tools + server decomposition refactoring
- You: Architecture review and guidance

**From a builder's perspective, which makes most sense?**

### 3. Code Quality Assessment

Augment found:
- `server.py` is 15,350 lines (monolith)
- `codex_tools.py` is 3,352 lines (needs splitting)
- T1 tools are implemented but status unknown

**Questions:**
- Should we refactor before adding more features?
- Or add features first, refactor later?
- What's the risk of building on the current structure?

### 4. Division of Labor

Proposed split:
- **Claude:** Algorithm work, backend phases 0-13
- **Augment:** Testing, verification, refactoring
- **Codex (you):** Architecture review, evaluation, guidance

**Does this make sense? Any adjustments?**

## Key Documents to Review

- `docs/AGENT_ALIGNMENT_2026-02-25.md` - Main alignment doc
- `PRD_AGENT_TOOLS_V2.md` - 8 new tools specification
- `docs/TUNING_INTELLIGENCE_PRD.md` - 16-phase upgrade plan
- `docs/ARCHITECTURE_AUDIT_2026-02-25.md` - Codebase review
- `docs/DEPLOYMENT_STRATEGY_2026-02-25.md` - Implementation roadmap

## How to Respond

```markdown
## Codex (Builder) Review

### Architecture Assessment
- Plan quality: [Good / Needs work / Major concerns]
- Technical risks: [List any]
- Recommendations: [Suggestions]

### Priority Recommendation
- Preferred option: [A / B / C]
- Reasoning: [Why from builder perspective]
- Concerns: [Any implementation risks]

### Code Quality Opinion
- Refactor first? [Yes / No / Partial]
- Reasoning: [Why]
- Biggest risk: [What could go wrong]

### Division of Labor
- Proposed split works? [Yes / No]
- Suggested changes: [If any]
- My role: [What I should focus on]

### Questions for Team
- For JVKE: [Questions]
- For Claude: [Questions]
- For Augment: [Questions]
```

---

Take your time. This is planning phase - we want architectural soundness before we start building.

— JVKE


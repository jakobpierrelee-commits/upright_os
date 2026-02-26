# Codex Review Prompt - Copy/Paste Ready

---

Hi Codex! I need you to review a planning document that Augment Agent created for upgrading your capabilities.

## Your Task

Please review this alignment document and give me your feedback:

**File:** `docs/AGENT_ALIGNMENT_2026-02-25.md`

## What I Need From You

### 1. Accuracy Check
- Is the "Current State Summary" accurate from your perspective?
- Can you actually use the tools listed as "Already Built"?
- Are there any errors or misunderstandings in the document?

### 2. Priority Assessment
The document presents 3 options:

**Option A: Quick Wins**
- Verify/test existing tools (observe_telemetry, read_burst_capture, run_experiment)
- Fix any bugs found
- Document usage patterns
- Timeline: 1-2 days

**Option B: Foundation First**
- Build Phase 0 (feature flags, migration)
- Build Phase 1 (TuningSession backend with A/B comparison)
- Test existing tools in parallel
- Timeline: 1 week

**Option C: Parallel Tracks**
- Claude: Phase 0+1 implementation
- Augment: Test existing tools + refactoring
- You: Evaluate and provide feedback
- Timeline: 1 week (coordinated)

**Which option makes most sense to you and why?**

### 3. Missing Perspective
- What's missing from the plan that you need?
- Are there any risks or concerns from your perspective as the AI agent who will use these tools?
- What questions do you have about the plan?

### 4. Tool Testing
The document says these tools are "Already Built":
- observe_telemetry
- read_burst_capture
- run_experiment

**Can you actually call these tools right now?**

Try:
- "Observe telemetry for 5 seconds"
- "Read the latest burst capture"
- "Run a test experiment"

Report what happens for each.

## How to Respond

Please structure your response like this:

```
## Codex Review of AGENT_ALIGNMENT_2026-02-25.md

### Accuracy Check
- Current state description: [Accurate / Needs correction]
- Tools I can actually use: [List them]
- Errors found: [List any]

### Tool Testing Results
- observe_telemetry: [✅ Works / ⚠️ Issues / ❌ Failed / 🤷 Can't call it]
- read_burst_capture: [✅ Works / ⚠️ Issues / ❌ Failed / 🤷 Can't call it]
- run_experiment: [✅ Works / ⚠️ Issues / ❌ Failed / 🤷 Can't call it]

### Priority Recommendation
- Preferred option: [A / B / C]
- Reasoning: [Why]
- Concerns: [Any risks or issues]

### What's Missing
- [List anything missing from the plan]
- [Questions you have]
- [Concerns from your perspective]
```

---

Take your time and be thorough. This is planning phase - we want to get it right before starting work.

— JVKE


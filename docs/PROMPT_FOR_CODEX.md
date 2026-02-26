# Prompt for Codex - Copy This to Cascade

---

Hi Codex! I'm planning a major upgrade to your capabilities and need your input before we start any work.

## What We're Planning

We're coordinating 3 AI agents to enhance UpRight.os:
- **Augment Agent:** Analyzing the codebase
- **Claude (you're talking to me through):** Implementation work
- **You (Codex):** The AI tuning assistant we're upgrading

## What Augment Discovered

Good news: **3 advanced tools are already implemented** in the codebase and should be available to you:

### 1. observe_telemetry
**What it does:** Watches live telemetry for N seconds and computes metrics like:
- angle_variance (stability measure)
- output_saturation_pct (how hard motors are working)
- oscillation_detected (is the robot oscillating?)
- settling_time_ms (how fast it stabilizes)

### 2. read_burst_capture
**What it does:** Analyzes high-frequency burst capture data:
- FFT frequency analysis
- Oscillation frequency detection
- Phase lag between angle and motor output
- Noise floor spectrum

### 3. run_experiment
**What it does:** A/B testing with safety:
- Captures baseline performance
- Applies a PID change
- Observes the result
- Compares baseline vs result
- Auto-reverts if performance degrades

## I Need Your Input On 3 Things

### 1. Can You Use These Tools Right Now?

**Please try:**

**Test A:**
"Can you observe telemetry for 5 seconds and tell me the angle variance and output saturation?"

**Test B:**
"Can you read the latest burst capture and analyze it for oscillation frequency?"

**Test C:**
"Can you run a test experiment that changes Kp to 18 and automatically reverts if it makes things worse?"

**For each test, tell me:**
- ✅ Worked perfectly - describe what you got back
- ⚠️ Worked but had issues - describe the problem
- ❌ Failed - share the error message
- 🤷 Don't know how to call it - need help

### 2. What Would Help You Most?

We're planning to add more capabilities. **Rank these by value to you:**

**Real-time Feedback:**
- A) Live telemetry observation with metrics (observe_telemetry)
- B) Burst capture FFT analysis (read_burst_capture)

**Experimentation:**
- C) A/B experiment runner with auto-rollback (run_experiment)
- D) Config comparison tool (compare current vs checkpoint)
- E) One-click rollback to known-good state

**Intelligence:**
- F) Physics-based PID simulation (what-if analysis before applying)
- G) ML-powered next-step suggestions (what to try next)
- H) Session annotation (remember what worked/failed)

**Your top 3:** [rank them 1-2-3]

### 3. What's Missing or Frustrating?

From your perspective as the AI doing the tuning work:
- What do you wish you could do but can't?
- What's frustrating about current tools?
- What would make you more confident in your recommendations?
- What information do you need but don't have access to?

## The Plan (For Your Review)

Based on your feedback, we'll choose one of these paths:

**Option A: Quick Wins (1-2 days)**
- Test and fix the 3 existing tools
- Document how to use them
- Make sure they work perfectly for you

**Option B: Foundation First (1 week)**
- Build session-based A/B comparison system
- Add real step response metrics
- Then add more intelligence tools

**Option C: Parallel Tracks (1 week)**
- Test existing tools while building new foundation
- Fastest but needs coordination

**Which option makes most sense to you?**

## Why Your Input Matters

You're the AI agent who will actually use these tools to help users tune their robots. Your perspective on:
- What works vs what doesn't
- What's valuable vs what's not
- What's missing vs what's sufficient

...is critical to making the right decisions about what to build next.

## How to Respond

Just answer naturally, but please cover:
1. **Test results** for the 3 tools (A, B, C)
2. **Top 3 priorities** from the list (rank 1-2-3)
3. **What's missing** or frustrating
4. **Which option** (A, B, or C) you recommend

Take your time and be honest - this is planning, not execution yet.

---

**Thanks for your input, Codex! We'll sync with all agents before starting any work.**

— JVKE


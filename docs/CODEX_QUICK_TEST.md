# Quick Test for Codex - Copy This to Chat

Hi Codex! We're coordinating a multi-agent upgrade and need your help testing 3 new tools that were just discovered in the codebase.

---

## Quick Tests (Please Try These)

### Test 1: observe_telemetry
**Try this:**
```
Can you observe telemetry for 5 seconds and tell me the angle variance and output saturation?
```

**What should happen:**
You should be able to call `observe_telemetry` with `duration_s=5` and get back metrics like:
- angle_variance (degrees²)
- output_saturation_pct (%)
- oscillation_detected (true/false)

**Report back:**
- ✅ Worked perfectly
- ⚠️ Worked but had issues: [describe]
- ❌ Failed with error: [paste error]
- 🤷 Not sure how to call it

---

### Test 2: read_burst_capture
**Try this:**
```
Can you read the latest burst capture and analyze it for oscillation frequency?
```

**What should happen:**
You should be able to call `read_burst_capture` with `capture_id="latest"` and get back:
- FFT analysis with dominant frequency
- Oscillation detection
- Phase lag between angle and output

**Report back:**
- ✅ Worked perfectly
- ⚠️ Worked but had issues: [describe]
- ❌ Failed with error: [paste error]
- 🤷 Not sure how to call it

---

### Test 3: run_experiment
**Try this:**
```
Can you run a test experiment that changes Kp to 18 and automatically reverts if it makes things worse?
```

**What should happen:**
You should be able to call `run_experiment` with:
- change: {cmd: "PID 18 0.1 0.6"}
- baseline_s: 3
- observe_s: 5
- auto_revert: true

And get back a comparison showing if the change improved or degraded performance.

**Report back:**
- ✅ Worked perfectly
- ⚠️ Worked but had issues: [describe]
- ❌ Failed with error: [paste error]
- 🤷 Not sure how to call it

---

## Quick Questions

1. **Which of these 3 tools would help you most in tuning?**
   - A) observe_telemetry (live metrics)
   - B) read_burst_capture (FFT analysis)
   - C) run_experiment (A/B testing)

2. **What's missing that would make you more effective?**
   - [Your answer]

3. **Any issues with current tools?**
   - [Your answer]

---

## Context

We're coordinating between 4 agents:
- **You (Codex):** AI tuning assistant
- **Cascade:** Backend implementation
- **Augment:** Testing and verification
- **JVKE:** Decision maker

We found these 3 tools are already implemented and should be available to you. We just need to verify they work from your perspective!

---

**Thanks! Your feedback will help us prioritize what to build next.**

— JVKE + Augment


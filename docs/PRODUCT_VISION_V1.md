# UpRight.os Product Vision v1

> A Windsurf-like workspace where AI agents partner with you to build self-balancing robots.

---

## Core Identity

**UpRight.os is NOT:**
- A generic IDE
- A multi-user SaaS platform
- An app development tool

**UpRight.os IS:**
- A single-user workspace for robot development
- An AI-partnered environment (like Windsurf for robotics)
- Focused exclusively on self-balancing robot builds

---

## The 3 Agent Capabilities (v1 Scope)

### 1. Understand the User's Goal
- What robot are you building? (2-wheel, 1-wheel, reaction wheel, etc.)
- What's the target behavior? (stationary balance, mobility, payload handling)
- What constraints exist? (parts on hand, budget, skill level)

**Required context:** Goal capture, robot profile, design memory

### 2. Guide the Build
- Pin in/out diagrams (mermaid)
- Part selection recommendations (IMU, motors, drivers, MCU)
- Wiring validation and common pitfall warnings
- BOM generation

**Required context:** Hardware knowledge base, component compatibility rules

### 3. Build Code + Tune Control Loops
- Generate firmware tailored to the build
- Deep control systems assistance (not just "here's a PID")
  - Sensor fusion (complementary filter, Kalman)
  - Loop timing and stability margins
  - Saturation handling, anti-windup
  - Cascaded control (inner/outer loops)
- Live tuning partnership with telemetry feedback
- Explain *why* a gain change affects behavior

**Required context:** Live telemetry stream, tuning history, firmware state

---

## What This Means for the Codebase

### KEEP (Core to Vision)

| Domain | Purpose | Key Files |
|--------|---------|-----------|
| **Serial/Telemetry** | Live robot data | `serial_gateway.py`, telemetry adapters |
| **Firmware Lifecycle** | Compile, flash, manage sketches | `firmware_manager.py` |
| **Tuning Intelligence** | Guards, preflight, apply | `tuning_guards.py`, `routes_tuning.py` |
| **Agent Core** | Chat, tools, knowledge | `codex_agent.py`, `codex_tools.py` |
| **Hardware Profile** | Robot identity | `hardware_profile/` |
| **Design Memory** | Build decisions, tuning history | `design_memory.py` |

### CUT (Out of Scope for v1)

| Domain | Reason | Files to Remove/Simplify |
|--------|--------|--------------------------|
| **app_dev mode** | Not building the app, building robots | Agent mode logic |
| **ops_debug mode** | Not debugging the app | Agent mode logic |
| **firmware_review mode** | Too specialized | Agent mode logic |
| **Multi-user auth** | Single user | Simplify `auth_manager.py` |
| **Complex RAG** | Unified knowledge is enough | Simplify `codex_rag.py` |

### SIMPLIFY

| Current | Target |
|---------|--------|
| 4+ agent modes | 1 mode: `robot_dev` (or just "agent") |
| 124 routes | ~40 focused routes |
| Multiple knowledge stores | 1 unified knowledge layer |
| Auth complexity | Single-user token or none |

---

## Success Criteria for v1

1. **Connect** → Robot is recognized, telemetry streams live
2. **Chat** → Agent understands "I'm building a 2-wheel balancer with MPU6050 and N20 motors"
3. **Guide** → Agent produces pin diagram, suggests driver, warns about common issues
4. **Code** → Agent generates or modifies firmware for the specific build
5. **Tune** → Agent watches telemetry, suggests gain changes, applies them safely

---

## Non-Goals for v1

- Mobile app
- Cloud deployment
- Multi-robot management
- Competitive feature parity with Arduino IDE
- Generic robotics (drones, arms, etc.)

---

## Next Steps

1. **Consolidate agent modes** → Single `robot_dev` mode
2. **Prune unused routes** → Remove app_dev/ops_debug specific endpoints
3. **Unify knowledge** → One knowledge store with robot build context
4. **Simplify auth** → Remove or stub multi-user complexity
5. **Resume extraction** → Only for code that serves this vision

---

*Document created: 2026-02-26*
*Author: Strategic review session with Cascade*

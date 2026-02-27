# UpRight.os: Ideal Architecture (If Built From Scratch)

> What would this app look like if perfectly designed for its purpose from day one?

---

## The Purpose (Restated)

A **Windsurf-like workspace** where an AI agent partners with you to build self-balancing robots.

**User flows:**
1. Connect to robot hardware
2. Describe what I'm building to the agent
3. Get guidance (pin diagrams, parts, wiring)
4. Generate/modify firmware
5. Flash and test
6. Tune control loops with live telemetry feedback

---

## Ideal File Structure

```
upright-os/
├── app/
│   ├── ui/                              # Frontend (~2,000 lines total)
│   │   └── src/
│   │       ├── App.tsx                  # Shell with 4 panels
│   │       ├── panels/
│   │       │   ├── ChatPanel.tsx        # Agent conversation
│   │       │   ├── StatusPanel.tsx      # Robot state (always visible)
│   │       │   ├── TuningPanel.tsx      # Gains + live graphs
│   │       │   └── FirmwarePanel.tsx    # Code view + flash button
│   │       ├── hooks/
│   │       │   ├── useRobot.ts          # Connection state
│   │       │   ├── useTelemetry.ts      # WebSocket stream
│   │       │   └── useAgent.ts          # Chat state
│   │       └── api.ts                   # ~200 lines
│   │
│   └── bridge/                          # Backend (~3,000 lines total)
│       ├── main.py                      # Entry (~50 lines)
│       ├── server.py                    # HTTP routing (~500 lines)
│       ├── services/
│       │   ├── serial_service.py        # Hardware comms (~400 lines)
│       │   ├── firmware_service.py      # Compile/flash (~600 lines)
│       │   ├── agent_service.py         # Chat + tools (~800 lines)
│       │   ├── telemetry_service.py     # Stream + capture (~300 lines)
│       │   └── tuning_service.py        # Apply + guards (~400 lines)
│       └── tools/                       # Agent tools (~500 lines total)
│           ├── robot_tools.py           # status, connect, profile
│           ├── firmware_tools.py        # compile, flash, generate
│           ├── tuning_tools.py          # apply, preflight, capture
│           └── build_tools.py           # pin_diagram, suggest_parts
│
├── firmware/
│   └── templates/                       # Base sketches per robot type
│       ├── two_wheel_base/
│       ├── reaction_wheel_base/
│       └── single_wheel_base/
│
├── knowledge/                           # Agent context
│   ├── parts_db.json                    # Component compatibility
│   ├── wiring_rules.json                # Pin assignment rules
│   └── control_theory.md                # PID, Kalman, tuning heuristics
│
└── docs/
    └── PRODUCT_VISION.md
```

---

## Ideal Routes (~20 total)

```python
# Robot connection
GET  /robot/status           # Connected? Port? MCU?
POST /robot/connect          # Attempt connection
GET  /robot/profile          # Hardware profile

# Telemetry
WS   /telemetry              # Live stream (WebSocket)
POST /telemetry/capture      # Start burst capture
GET  /telemetry/captures     # List captures

# Firmware
GET  /firmware/status        # Current sketch, compiled?
POST /firmware/compile       # Build
POST /firmware/flash         # Deploy
GET  /firmware/templates     # Available base sketches

# Tuning
GET  /tuning/current         # Current gains
POST /tuning/apply           # Change gains (with guards)
POST /tuning/preflight       # Safety check before big changes

# Agent
GET  /agent/threads          # Chat history
POST /agent/chat             # Send message, get response
GET  /agent/context          # Current build context

# Build
GET  /build/profile          # What robot am I building?
POST /build/profile          # Update build context
```

---

## Ideal Agent Tools (~12 total)

| Tool | Purpose |
|------|---------|
| `read_robot_status` | What's the robot doing right now? |
| `get_hardware_profile` | What MCU, IMU, motors are connected? |
| `generate_pin_diagram` | Output mermaid diagram for wiring |
| `suggest_parts` | Recommend components based on build goal |
| `check_wiring` | Validate pin assignments |
| `generate_firmware` | Create sketch from template + customizations |
| `modify_firmware` | Edit existing sketch |
| `compile_firmware` | Build the sketch |
| `flash_firmware` | Deploy to robot |
| `read_telemetry` | Get current sensor values |
| `apply_tuning` | Change gains (with safety guards) |
| `capture_session` | Log telemetry for analysis |

---

## Ideal Data Model

```
Robot
├── port: str
├── mcu: str (uno, nano, esp32, etc.)
├── connected: bool
└── last_status: dict

Build
├── goal: str ("2-wheel balancer for indoor use")
├── imu: str ("MPU6050")
├── motors: str ("N20 with TB6612")
├── wheels: str ("65mm rubber")
└── wiring: dict (pin assignments)

Firmware
├── sketch_path: str
├── template_used: str
├── last_compiled: datetime
└── version: str

TuningSession
├── timestamp: datetime
├── gains_before: dict
├── gains_after: dict
├── telemetry_snapshot: list
└── outcome: str ("improved", "worse", "neutral")

Conversation
├── thread_id: str
├── messages: list
└── build_context: Build (linked)
```

---

## Size Comparison

| Component | Current | Ideal | Reduction |
|-----------|---------|-------|-----------|
| Backend total | ~41,000 lines | ~3,000 lines | **93%** |
| server.py | 6,380 lines | ~500 lines | **92%** |
| codex_tools.py | 3,060 lines | ~500 lines | **84%** |
| Routes | 124 | ~20 | **84%** |
| Agent modes | 4+ | 1 | **75%** |
| Frontend | ~5,000+ lines | ~2,000 lines | **60%** |

---

## What We Keep From Current

These components are battle-tested and align with ideal:

| Component | Lines | Why Keep |
|-----------|-------|----------|
| `serial_gateway.py` | 392 | Solid hardware comms |
| `firmware_manager.py` | 2,877 | Complex but necessary |
| `tuning_guards.py` | 398 | Safety is critical |
| `contract_readiness.py` | 591 | Telemetry validation |

---

## What We Cut or Rebuild

| Component | Lines | Why Cut |
|-----------|-------|---------|
| Multi-mode agent logic | ~500 | One mode is enough |
| Auth system | ~600 | Single user |
| RAG complexity | ~1,100 | Simple knowledge store |
| 100+ tools | ~3,000 | 12 tools is enough |
| Route explosion | ~2,000 | 20 routes is enough |

---

## Path From Here to Ideal

### Option A: Incremental Refactor
- Keep working codebase
- Cut mode complexity
- Consolidate routes
- Prune tools
- **Timeline:** 2-4 weeks of focused work
- **Risk:** May never reach ideal simplicity

### Option B: Greenfield Rebuild
- Start fresh with ideal structure
- Port serial_gateway, firmware_manager, tuning_guards
- Rebuild agent with 12 tools
- New minimal UI
- **Timeline:** 1-2 weeks intense
- **Risk:** Lose momentum, may hit unknown issues

### Option C: Hybrid (Recommended)
- Keep `app/bridge/` core (serial, firmware, tuning)
- Aggressively delete agent complexity
- Rebuild agent_service.py with 12 tools
- New UI panels (keep existing styling)
- **Timeline:** 1-2 weeks
- **Best of both:** Proven hardware code + clean agent layer

---

*Architecture vision created: 2026-02-26*

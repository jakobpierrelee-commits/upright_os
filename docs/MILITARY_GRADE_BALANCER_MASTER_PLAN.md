# Military-Grade Self-Balancing Robot Master Plan

Last updated: 2026-02-19
Workspace: /Users/jvke/Documents/New project

## 1) Program Intent
Build deployment-ready, large two-wheeled self-balancing robots (hoverboard-scale) capable of carrying a mannequin payload, with reliability and safety standards far above hobby-grade platforms.

## 2) Firmware/Docs Artifacts To Auto-Generate Per Sketch
Use this naming in UpRight OS as the standard **Firmware Design Pack**:

1. **Control Flow Diagram** (`mermaid flowchart`)
2. **State Machine Diagram** (`mermaid stateDiagram-v2`)
3. **Hardware Block Diagram** (`mermaid graph`)
4. **Pin Mapping Diagram** (`mermaid graph` or `classDiagram`)
5. **Pin Assignment Table** (Markdown)
6. **Command/API Map** (Markdown)

Suggested UI umbrella label: **Auto-Generated Firmware Architecture Docs**.

## 3) What Teams Underuse (Biggest Time Savers)
These are typically the highest ROI upgrades for reducing calibration/tuning/deployment time:

1. **IMU with onboard fusion + calibration status** (BNO08x class)
- Benefit: calibration readiness becomes measurable, not guessed.

2. **Motor driver/control with current sensing telemetry**
- Benefit: direct torque/load visibility for faster tuning and safer operation.

3. **Higher-resolution wheel encoders**
- Benefit: cleaner speed/position loops and less false instability during tuning.

4. **PWM-rejecting current measurement path**
- Benefit: usable current data under switching noise.

5. **Fuel-gauge IC (not voltage-only SoC estimate)**
- Benefit: repeatable tuning conditions across battery states.

## 4) Approximate Price Delta (US, single-unit class, as discussed)
- **IMU**: MPU6050 (~$3-5) vs BNO085/BNO086 (~$25-35) => +$21 to +$31
- **Motor driver**: TB6612-class low-cost vs higher-grade current-capable stack => commonly +$8 and up
- **Encoders**: basic low-CPR pair vs industrial/high-res pair => commonly +$50/pair and up
- **Current telemetry add-on**: typically +$10 and up
- **Fuel gauge add-on**: typically +$6 to +$7

Rule of thumb: a faster-iteration instrumentation stack usually adds **~$40 to $120+** depending on encoder and IMU choices.

## 5) Best-of-Best Platform Architecture (Hoverboard-Scale + Mannequin)
Treat this as a human-rated balancing platform architecture:

1. **Actuation**
- 2x high-torque BLDC hub motors with FOC-capable control
- Redundant braking path (electrical + mechanical fail-safe)

2. **Motor control**
- Independent left/right control channels with current/torque telemetry
- Fault isolation per side

3. **Sensing**
- Industrial IMU + high-quality wheel encoders
- Rail current, battery, and thermal sensing on critical paths

4. **Compute and safety separation**
- Safety MCU: hard real-time state machine, estop, watchdogs, safe-state logic
- High-level compute: mission/UI/planning/logging
- Safety interlocks must be enforceable independent of high-level software

5. **Control stack**
- Cascaded loops: torque/current -> wheel velocity -> pitch/position
- Sensor fusion estimator (EKF/UKF class) for IMU + encoders
- Gain scheduling by speed, payload/CG estimate, and battery state

6. **Power system**
- 48-72V class traction bus with precharge + contactor + fusing
- Isolated low-voltage rails and EMI-aware harnessing

7. **Mechanical**
- Wide wheelbase, rigid frame, low center of mass for battery mass
- Payload mount with known CG envelope and hard limits

8. **Safety and validation**
- Dual-channel estop
- Tip/runaway detection with guaranteed zero-torque transition
- Verification ladder: SIL -> HIL -> tethered live tests -> staged free-run expansion

## 6) Auto-Calibration Strategy (Core Sketch Guidance)
For robust field deployment, use a 2-phase approach:

1. **Startup auto-zero (static gate)**
- Require stillness window (`|gyro|` low + low angle variance for ~1-2s)
- Average filtered tilt samples and set `angleZeroDeg`

2. **Online setpoint trim (dynamic gate)**
- During stable balancing, adapt `setpointDeg` slowly from persistent bias
- Clamp trim range and freeze/save only after stability criteria are met

Important: true balance point cannot be inferred from arbitrary posture; must begin near-upright and still.

## 7) Current Sketch Context Note
Primary active firmware observed in workspace:
- `/Users/jvke/Documents/New project/tumbller_v06_nano_balance_v2/tumbller_v06_nano_balance_v2.ino`

This sketch already supports manual zero and calibration commands (`ZERO`, `CAL ZERO`) and is a good base for startup auto-calibration/state-machine enhancement.

## 8) Operating Principle For Future Sessions
When planning this build, use this document as the default system baseline unless explicitly overridden by newer constraints (budget, mass, size, safety policy, supply availability, or mission profile).

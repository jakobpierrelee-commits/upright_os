# PRD: Calibration + Anti-Drift Architecture v1

**Status:** Phase A — Readiness + Contracts  
**Owner:** Bridge/UI/Controls  
**Priority:** High  
**Dependencies:** Agent Tools v2 complete (T1–T3)

---

## 1. Problem Framing

### The Drift Problem

A self-balancing robot can maintain **tilt stability** (upright posture) while still exhibiting **translational drift**—slowly rolling forward, backward, or curving. This happens because the inner PID loop only controls **angle**, not **position** or **velocity**.

```
┌─────────────────────────────────────────────────────────────────┐
│  Current Architecture (Inner Loop Only)                        │
│                                                                 │
│   Setpoint ──► [PID] ──► Motor Output ──► Robot ──► Angle      │
│      │                                        │                 │
│      └────────────────────────────────────────┘                 │
│                     (angle feedback only)                       │
│                                                                 │
│  Problem: No velocity/position feedback = drift accumulates    │
└─────────────────────────────────────────────────────────────────┘
```

### Root Causes of Drift

| Cause | Description | Mitigation |
|-------|-------------|------------|
| **Missing outer loop** | No velocity/position feedback to correct translational motion | Add cascaded velocity loop |
| **Sensor bias** | Gyro or accelerometer zero-point drift over time/temperature | Calibration routine at startup |
| **Upright offset** | Physical center of mass ≠ sensor zero angle | Trim adjustment |
| **Motor asymmetry** | Left/right motor response mismatch | Per-motor trim calibration |
| **Deadband/stiction** | Motors don't respond to small commands | Feedforward compensation |
| **Encoder mismatch** | Wheel diameter or encoder scale differences | Calibration coefficients |

### Inner Loop vs Outer Loop

```
┌─────────────────────────────────────────────────────────────────┐
│  Target Architecture (Cascaded Control)                        │
│                                                                 │
│   Position    Velocity                                          │
│   Setpoint    Setpoint   Angle                                  │
│      │           │       Setpoint                               │
│      ▼           ▼          │                                   │
│   [Pos PID] ► [Vel PID] ────┼──► [Angle PID] ──► Motor ──► Robot│
│      ▲           ▲          │          ▲                   │    │
│      │           │          │          └───────────────────┤    │
│      │           │          │            (angle feedback)  │    │
│      │           └──────────┼──────────────────────────────┤    │
│      │             (velocity feedback via encoders)        │    │
│      └──────────────────────┼──────────────────────────────┘    │
│                   (position feedback via odometry)              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Calibration Walkthrough Requirements

### 2.1 Gyro Bias Calibration

**Purpose:** Determine gyro zero-rate offset when stationary.

**Procedure:**
1. Robot must be stationary and stable (ideally held or on stand)
2. Sample gyro readings for 2–5 seconds (≥100 samples)
3. Compute mean as `gyro_bias`
4. Store in EEPROM or runtime config

**Acceptance:**
- Bias stability: consecutive calibrations within ±0.5 deg/s
- Must complete within 10 seconds
- Visual feedback during calibration

**Telemetry Field:** `gyro_bias` (deg/s or rad/s, signed)

### 2.2 Accelerometer Level Offset

**Purpose:** Determine accelerometer reading when robot is level (0°).

**Procedure:**
1. Place robot on known level surface
2. Sample accelerometer for 2 seconds
3. Compute mean as `accel_level_offset`
4. This becomes the "true zero" reference

**Acceptance:**
- Offset repeatability within ±0.5°
- Must not require firmware reflash

**Telemetry Field:** `accel_level_offset` (raw units or degrees)

### 2.3 Upright Trim Adjustment

**Purpose:** Fine-tune the angle setpoint so robot balances without drift tendency.

**Procedure:**
1. Robot in BALANCING mode
2. Operator adjusts trim until minimal drift observed
3. Store as `upright_trim` (offset applied to setpoint)

**Acceptance:**
- Trim range: ±5° from nominal
- Adjustment granularity: 0.1° steps
- Persisted across power cycles

**Telemetry Field:** `upright_trim` (degrees)

### 2.4 Motor Trim Calibration (Optional Phase B)

**Purpose:** Compensate for left/right motor response differences.

**Telemetry Fields:** 
- `motor_l_trim` (scale factor or offset)
- `motor_r_trim` (scale factor or offset)

---

## 3. Anti-Drift Architecture Requirements

### 3.1 Outer Velocity Loop

**Purpose:** Regulate translational velocity to zero (or commanded value).

**Requirements:**
- Input: velocity measurement from encoders or model-based estimator
- Output: angle setpoint adjustment fed to inner loop
- Tunable gains separate from inner PID
- Enable/disable flag: `outer_loop_enabled`

**Telemetry Fields:**
- `vel_meas` — measured velocity (m/s or encoder ticks/s)
- `vel_target` — commanded velocity (usually 0 for station-keeping)
- `target_angle_from_velocity` — angle setpoint computed by outer loop

### 3.2 Optional Position Loop (Phase C)

**Purpose:** Return robot to a reference position after disturbances.

**Requirements:**
- Input: position estimate from integrated velocity or external sensor
- Output: velocity setpoint fed to velocity loop
- Lower bandwidth than velocity loop to avoid instability

### 3.3 Drift Diagnostic State

**Purpose:** Provide operator visibility into drift behavior.

**Telemetry Field:** `drift_diag_state`

**Values:**
| Value | Meaning |
|-------|---------|
| `idle` | Not balancing, diagnostics inactive |
| `observing` | Collecting drift metrics |
| `drifting_fwd` | Detected forward drift tendency |
| `drifting_back` | Detected backward drift tendency |
| `drifting_left` | Detected left curve tendency |
| `drifting_right` | Detected right curve tendency |
| `stable` | No significant drift detected |

---

## 4. Safety Constraints

### 4.1 Calibration Safety

- Calibration must not occur while ARMED or BALANCING
- Calibration must be explicitly initiated by operator
- Failed calibration must not overwrite previous valid values
- Calibration values must be sanity-checked before application

### 4.2 Outer Loop Safety

- Outer loop must be disabled if inner loop becomes unstable
- Outer loop gains must have firmware-enforced limits
- Angle setpoint from outer loop must be clamped (e.g., ±10°)
- Loss of velocity feedback must trigger outer loop disable

### 4.3 Rollback Expectations

- Any calibration change must be revertible to previous values
- Outer loop can be disabled without firmware change
- Agent tools can trigger rollback via `safe_rollback` tool

---

## 5. Phased Rollout Plan

### Phase A: Readiness + Contracts (This PR)

**Scope:**
- Define telemetry contract v2 (additive fields)
- Add bridge-level v1/v2 readiness detection
- Add Setup UI readiness panel
- No firmware changes required
- No control loop changes

**Success Criteria:**
- Existing v1 firmware passes unchanged
- Probe responses include v2 readiness info
- UI shows readiness status

### Phase B: Calibration Walkthrough

**Scope:**
- Calibration UI workflow (gyro bias, accel offset, upright trim)
- Persist calibration values (bridge or firmware)
- Recalibration prompts tied to arm context
- Agent tool: `run_calibration`

**Success Criteria:**
- Operator can complete calibration walkthrough
- Calibration values persist and apply
- Agent can recommend recalibration

### Phase C: Outer Loop Integration

**Scope:**
- Velocity loop implementation (firmware or bridge-side)
- Position loop (optional)
- Drift diagnostics telemetry
- Agent tool: `diagnose_drift`, `tune_velocity_loop`

**Success Criteria:**
- Robot maintains station (no drift) when outer loop enabled
- Drift diagnostics visible in UI
- Agent can suggest outer loop adjustments

---

## 6. Telemetry Contract Summary

### v1 Required (unchanged)
```
mode, ang, raw, gyro|gyr|gx, out, kp, ki, kd, set
```

### v2 Optional (Phase A additive)
```
gyro_bias, accel_level_offset, upright_trim,
vel_meas, vel_target, outer_loop_enabled,
target_angle_from_velocity,
motor_l_trim, motor_r_trim, drift_diag_state
```

### v2 Target Required (Phase C, future enforcement)
```
gyro_bias, vel_meas, outer_loop_enabled
```

---

## 7. Success Metrics

| Metric | Phase A | Phase B | Phase C |
|--------|---------|---------|---------|
| v1 compatibility maintained | ✓ | ✓ | ✓ |
| v2 readiness visible in UI | ✓ | ✓ | ✓ |
| Calibration workflow complete | — | ✓ | ✓ |
| Drift reduced by >80% | — | — | ✓ |
| Agent can diagnose drift | — | — | ✓ |

---

## 8. Open Questions

1. **Velocity measurement source:** Encoders vs model-based estimator?
2. **Calibration storage:** Firmware EEPROM vs bridge-side config file?
3. **Outer loop location:** Firmware vs bridge (latency tradeoffs)?
4. **Position reference:** Absolute (external) vs relative (startup position)?

---

## 9. References

- `PRD_AGENT_TOOLS_V2.md` — Agent tools architecture
- `docs/contracts/telemetry_contract_v2.md` — Detailed contract spec
- `/probe/compat`, `/probe/connect` — Existing v1 probe endpoints

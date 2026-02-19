# Telemetry Contract v2 Specification

**Version:** 2.0.0-draft  
**Status:** Phase A — Additive Fields Only  
**Last Updated:** 2026-02-18

---

## 1. Overview

This document defines the telemetry contract between the UpRight robot firmware and the bridge/UI layer. It establishes:

- **v1 required fields** — Current baseline (unchanged)
- **v2 optional fields** — New calibration/anti-drift fields (additive)
- **v2 target required** — Future enforcement after migration window
- **Versioning and migration strategy**
- **Warning/error semantics**

---

## 2. Contract Versions

| Version | Status | Description |
|---------|--------|-------------|
| v1 | **Active** | Current production baseline |
| v2-optional | **Phase A** | Additive fields, no enforcement |
| v2-required | **Future** | Full v2 enforcement after migration |

---

## 3. Field Definitions

### 3.1 v1 Required Fields (Unchanged)

These fields MUST be present for v1 compatibility. Existing v1 firmware will continue to pass validation.

| Field | Type | Description | Fallback Aliases |
|-------|------|-------------|------------------|
| `mode` | string | Operating mode (SAFE_IDLE, IDLE, ARMED, BALANCING) | — |
| `ang` | number | Filtered angle in degrees | — |
| `raw` | number | Raw/unfiltered angle in degrees | — |
| `gyro` | number | Angular velocity (deg/s or rad/s) | `gyr`, `gx` |
| `out` | number | Motor output (-255 to 255) | — |
| `kp` | number | Proportional gain | — |
| `ki` | number | Integral gain | — |
| `kd` | number | Derivative gain | — |
| `set` | number | Angle setpoint | `setpoint` |

**Validation Rule:** A telemetry payload is v1-valid if ALL required fields (or their aliases) are present and parseable.

### 3.2 v2 Optional Fields (Phase A — Additive)

These fields are OPTIONAL in Phase A. Their presence enables v2 readiness but their absence does not break v1 compatibility.

| Field | Type | Unit | Description | Default if Missing |
|-------|------|------|-------------|-------------------|
| `gyro_bias` | number | deg/s | Calibrated gyro zero-rate offset | `null` |
| `accel_level_offset` | number | deg | Accelerometer level reference | `null` |
| `upright_trim` | number | deg | Balance point trim adjustment | `0.0` |
| `vel_meas` | number | m/s | Measured translational velocity | `null` |
| `vel_target` | number | m/s | Target velocity (usually 0) | `null` |
| `outer_loop_enabled` | boolean | — | Whether velocity loop is active | `false` |
| `target_angle_from_velocity` | number | deg | Angle setpoint from outer loop | `null` |
| `motor_l_trim` | number | scale | Left motor trim factor | `1.0` |
| `motor_r_trim` | number | scale | Right motor trim factor | `1.0` |
| `drift_diag_state` | string | — | Drift diagnostic state | `"idle"` |

**Validation Rule:** v2 readiness is achieved when ALL of: `gyro_bias`, `vel_meas`, `outer_loop_enabled` are present.

### 3.3 v2 Target Required (Future Phase)

After migration window (Phase C+), these fields will be REQUIRED for full v2 compliance:

| Field | Enforcement Date | Migration Path |
|-------|-----------------|----------------|
| `gyro_bias` | Phase C | Firmware update or calibration routine |
| `vel_meas` | Phase C | Encoder integration |
| `outer_loop_enabled` | Phase C | Firmware flag |

---

## 4. Versioning Strategy

### 4.1 Detection Logic

```python
def detect_contract_version(telemetry: dict) -> dict:
    """
    Detect telemetry contract version and readiness.
    
    Returns:
        {
            "contract_version_detected": "v1" | "v2",
            "v1_ok": bool,
            "v2_ready": bool,
            "v2_missing_fields": list[str]
        }
    """
    # v1 required fields (with aliases)
    V1_REQUIRED = {
        "mode", "ang", "raw", "out", "kp", "ki", "kd"
    }
    V1_REQUIRED_WITH_ALIASES = {
        "gyro": ["gyro", "gyr", "gx"],
        "set": ["set", "setpoint"],
    }
    
    # v2 readiness fields
    V2_READINESS_FIELDS = ["gyro_bias", "vel_meas", "outer_loop_enabled"]
    
    # Check v1
    v1_ok = all(f in telemetry for f in V1_REQUIRED)
    for field, aliases in V1_REQUIRED_WITH_ALIASES.items():
        v1_ok = v1_ok and any(a in telemetry for a in aliases)
    
    # Check v2 readiness
    v2_missing = [f for f in V2_READINESS_FIELDS if f not in telemetry]
    v2_ready = len(v2_missing) == 0
    
    return {
        "contract_version_detected": "v2" if v2_ready else "v1",
        "v1_ok": v1_ok,
        "v2_ready": v2_ready,
        "v2_missing_fields": v2_missing,
    }
```

### 4.2 Migration Path

1. **Phase A (now):** v2 fields are optional. v1 firmware passes unchanged.
2. **Phase B:** Calibration routines populate v2 fields. v2 readiness visible in UI.
3. **Phase C:** v2 fields become required for new features. v1-only devices show upgrade prompts.

---

## 5. Warning/Error Semantics

### 5.1 Readiness Check Results

| Check | Status | Meaning | UI Treatment |
|-------|--------|---------|--------------|
| `v1_ok: true` | Pass | All v1 fields present | Green indicator |
| `v1_ok: false` | Fail | Missing v1 fields | Red indicator, block ARM |
| `v2_ready: true` | Pass | All v2 readiness fields present | Green "v2 Ready" badge |
| `v2_ready: false` | Warn | Missing v2 fields | Yellow indicator, show missing |

### 5.2 Error Codes

| Code | Severity | Description |
|------|----------|-------------|
| `E_V1_MISSING_FIELD` | Error | Required v1 field missing |
| `E_V1_INVALID_TYPE` | Error | v1 field has wrong type |
| `W_V2_NOT_READY` | Warning | v2 readiness fields missing |
| `W_V2_PARTIAL` | Warning | Some v2 fields present, others missing |

### 5.3 Graceful Degradation

- Missing v2 fields MUST NOT cause v1 operations to fail
- UI MUST show v1 status independently of v2 status
- Agent tools MUST function with v1-only telemetry

---

## 6. Sample Payloads

### 6.1 v1-Only Telemetry (Current Firmware)

```json
{
  "mode": "BALANCING",
  "ang": 1.23,
  "raw": 1.25,
  "gyro": 0.05,
  "out": 42,
  "kp": 18.0,
  "ki": 0.1,
  "kd": 0.6,
  "set": 0.0
}
```

**Readiness Result:**
```json
{
  "contract_version_detected": "v1",
  "v1_ok": true,
  "v2_ready": false,
  "v2_missing_fields": ["gyro_bias", "vel_meas", "outer_loop_enabled"]
}
```

### 6.2 v2-Enabled Telemetry (Future Firmware)

```json
{
  "mode": "BALANCING",
  "ang": 1.23,
  "raw": 1.25,
  "gyro": 0.05,
  "out": 42,
  "kp": 18.0,
  "ki": 0.1,
  "kd": 0.6,
  "set": 0.0,
  "gyro_bias": -0.02,
  "accel_level_offset": 0.5,
  "upright_trim": 0.3,
  "vel_meas": 0.01,
  "vel_target": 0.0,
  "outer_loop_enabled": true,
  "target_angle_from_velocity": 0.15,
  "motor_l_trim": 1.0,
  "motor_r_trim": 0.98,
  "drift_diag_state": "stable"
}
```

**Readiness Result:**
```json
{
  "contract_version_detected": "v2",
  "v1_ok": true,
  "v2_ready": true,
  "v2_missing_fields": []
}
```

### 6.3 Partial v2 Telemetry (Calibration Done, No Velocity)

```json
{
  "mode": "BALANCING",
  "ang": 1.23,
  "raw": 1.25,
  "gyro": 0.05,
  "out": 42,
  "kp": 18.0,
  "ki": 0.1,
  "kd": 0.6,
  "set": 0.0,
  "gyro_bias": -0.02,
  "accel_level_offset": 0.5,
  "upright_trim": 0.3
}
```

**Readiness Result:**
```json
{
  "contract_version_detected": "v1",
  "v1_ok": true,
  "v2_ready": false,
  "v2_missing_fields": ["vel_meas", "outer_loop_enabled"]
}
```

---

## 7. Implementation Notes

### 7.1 Bridge-Side

- Readiness check runs on every telemetry ingest
- Results cached and included in probe responses
- No blocking behavior for v2 missing fields

### 7.2 UI-Side

- Display v1/v2 status in Setup/Preflight page
- Show actionable "next steps" for v2 readiness
- Do not block existing v1 workflows

### 7.3 Firmware-Side

- No changes required in Phase A
- Phase B: Add calibration storage and reporting
- Phase C: Add velocity measurement and outer loop

---

## 8. Testing Requirements

### 8.1 Unit Tests

| Test Case | Input | Expected Output |
|-----------|-------|-----------------|
| v1 complete | All v1 fields | `v1_ok=true, v2_ready=false` |
| v2 complete | All v1 + v2 readiness | `v1_ok=true, v2_ready=true` |
| v1 missing mode | No `mode` field | `v1_ok=false` |
| v2 partial | v1 + `gyro_bias` only | `v1_ok=true, v2_ready=false, missing=[vel_meas, outer_loop_enabled]` |
| Alias handling | `gx` instead of `gyro` | `v1_ok=true` |

### 8.2 Integration Tests

- Existing v1 probe flow unchanged
- New readiness fields in probe response
- UI displays readiness correctly

---

## 9. References

- `PRD_CALIBRATION_ANTIDRIFT_V1.md` — Parent PRD
- `/probe/compat` — Compatibility probe endpoint
- `/probe/connect` — Connection probe endpoint

# PRD: CodexAgent Tools v2 — Advanced Tuning Intelligence

**Status:** ✅ Implemented (Complete)  
**Priority:** High  
**Depends on:** PR1-4 (Tool UI, Upload UX, Failure Handling, RAG Indexing)

> **Implementation Note (2026-02-26):** All 8 PRD tools implemented. T1, T2, T3 complete.
> `execute_shell` added as approved utility extension (9 total tools).

---

## Overview

Extend CodexAgent with 8 new tools that enable **closed-loop tuning**, **real-time analysis**, and **intelligent recommendations**. These tools transform the agent from a command executor into a true tuning partner.

### Current State (v1 Tools)
- `get_probe_results` — Read hardware state
- `query_telemetry` — Query historical telemetry
- `query_checkpoints` — Query saved checkpoints
- `search_docs` — RAG search
- `execute_command` — Safe serial commands
- `edit_sketch_value` — Edit sketch constants
- `generate_sketch` — Template-based generation
- `compile_firmware` — Compile sketch
- `upload_firmware` — Upload with confirmation gate

### Target State (v2 Tools)
Add 8 new tools in 3 tiers:

| Tier | Tool | Theme | Integration Mode | Existing Path |
|------|------|-------|------------------|---------------|
| **T1** | `observe_telemetry` | Real-time visibility | **wrapper** | Wraps `TelemetryHub` WebSocket + adds analysis layer |
| **T1** | `read_burst_capture` | Real-time visibility | **wrapper** | Wraps `HostCaptureManager.status()` + `latest_run` CSV parsing |
| **T2** | `run_experiment` | Structured testing | **new capability** | — |
| **T2** | `diff_config` | Structured testing | **wrapper** | Wraps `query_checkpoints` + `GET` command |
| **T2** | `safe_rollback` | Structured testing | **wrapper** | Wraps `query_checkpoints` + `execute_command` |
| **T3** | `simulate_pid_response` | ML/prediction | **new capability** | — |
| **T3** | `suggest_next_step` | ML/prediction | **new capability** | — |
| **T3** | `annotate_session` | ML/prediction | **new capability** | `session_annotations` table |
| **Utility** | `execute_shell` | Build/test workflows | **approved extension** | Terminal command execution in workspace |

### Integration Mode Legend
- **wrapper**: Reuses existing endpoint/tool internally; adds analysis/convenience layer
- **replacement**: Deprecates old path (none in v2)
- **new capability**: No existing equivalent

### Deprecation Notes
> **None for v2.** All wrapper tools call existing infrastructure internally.
> No parallel code paths are introduced—wrappers delegate to existing implementations.

---

## Canonical Constants

### Telemetry Schema Mapping

The runtime uses these exact field names. Tool implementations **must** use these keys:

| Logical Name | Runtime Key | Fallback Keys | Type | Description |
|--------------|-------------|---------------|------|-------------|
| angle | `ang` | — | float | Filtered angle (degrees) |
| raw_angle | `raw` | — | float | Raw IMU angle (degrees) |
| gyro | `gyro` | `gyr`, `gx` | float | Gyroscope rate (deg/s) |
| output | `out` | — | float | Motor output (-255 to 255) |
| mode | `mode` | — | string | Robot mode (see below) |
| estop | `estop` | — | string | E-stop state ("0" or "1") |
| setpoint | `set` | — | float | Target angle (degrees) |
| kp | `kp` | — | float | PID proportional gain |
| ki | `ki` | — | float | PID integral gain |
| kd | `kd` | — | float | PID derivative gain |

### Valid Robot Modes

| Mode | Description | Safe for Experiments |
|------|-------------|----------------------|
| `SAFE_IDLE` | Motors off, safe state | ✓ (baseline only) |
| `IDLE` | Legacy idle (alias for SAFE_IDLE) | ✓ (baseline only) |
| `ARMED` | Ready to balance | ✓ |
| `BALANCING` | Active balancing | ✓ |
| `FAULT` | Error state | ✗ |
| `CALIBRATING` | Sensor calibration | ✗ |
| `UNKNOWN` | Unrecognized mode | ✗ |

**Fallback Behavior:** If `mode` is not in the known set, treat as `UNKNOWN` and abort write operations. Read operations should proceed with a warning.

### Observation & Runtime Limits (Canonical)

All tools **must** reference these values. Do not hardcode limits elsewhere.

| Limit | Value | Applies To |
|-------|-------|------------|
| `MAX_OBSERVE_DURATION_S` | 30 | `observe_telemetry`, `run_experiment` |
| `MAX_BASELINE_DURATION_S` | 15 | `run_experiment` |
| `MAX_EXPERIMENT_DURATION_S` | 60 | `run_experiment` (total) |
| `MAX_WRITES_PER_CALL` | 3 | `run_experiment`, `safe_rollback` |
| `EXPERIMENT_COOLDOWN_S` | 5 | `run_experiment` |
| `DEFAULT_SAMPLE_RATE_HZ` | 8 | `observe_telemetry` |
| `MAX_BURST_ROWS` | 3000 | `read_burst_capture` |
| `BURST_ROW_CHAR_LIMIT` | 500 | `read_burst_capture` (per row) |
| `SERIAL_TIMEOUT_S` | 2 | All serial operations |
| `WEBSOCKET_TIMEOUT_S` | 5 | `observe_telemetry` connection |

```python
# Reference implementation
class ObservationLimits:
    MAX_OBSERVE_DURATION_S = 30
    MAX_BASELINE_DURATION_S = 15
    MAX_EXPERIMENT_DURATION_S = 60
    MAX_WRITES_PER_CALL = 3
    EXPERIMENT_COOLDOWN_S = 5
    DEFAULT_SAMPLE_RATE_HZ = 8
    MAX_BURST_ROWS = 3000
    BURST_ROW_CHAR_LIMIT = 500
    SERIAL_TIMEOUT_S = 2
    WEBSOCKET_TIMEOUT_S = 5
```

---

## Tier 1: Feedback Loop Tools

### 1. `observe_telemetry`

**Purpose:** Watch live telemetry for N seconds and analyze stability metrics in real-time.

**Why Critical:** Current tools only query historical data. The agent cannot observe the immediate effect of changes. This closes the feedback loop.

**Integration Mode:** `wrapper`  
**Wraps:** `TelemetryHub` WebSocket subscription  
**Existing Path:** `/telemetry` WebSocket provides raw frames; `query_telemetry` provides historical DB queries  
**Value-Add:** Real-time statistical analysis, oscillation detection, settling time computation—none available in existing paths.

```json
{
  "type": "function",
  "function": {
    "name": "observe_telemetry",
    "description": "Watch live telemetry for N seconds and analyze stability, oscillation, output saturation, and settling behavior. Returns real-time metrics for tuning feedback.",
    "parameters": {
      "type": "object",
      "properties": {
        "duration_s": {
          "type": "number",
          "description": "Observation duration in seconds. Default 5, max 30.",
          "default": 5
        },
        "sample_rate_hz": {
          "type": "number", 
          "description": "Target sample rate. Default matches telemetry feed (~8Hz).",
          "default": 8
        },
        "metrics": {
          "type": "array",
          "items": { "type": "string" },
          "description": "Metrics to compute: angle_variance, angle_peak, output_mean, output_saturation_pct, oscillation_detected, settling_time_ms, trend_direction",
          "default": ["angle_variance", "output_saturation_pct", "oscillation_detected"]
        },
        "trigger": {
          "type": "string",
          "enum": ["immediate", "on_arm", "on_balance"],
          "description": "When to start observation. Default immediate.",
          "default": "immediate"
        }
      },
      "required": []
    }
  }
}
```

**Returns:**
```json
{
  "ok": true,
  "tool": "observe_telemetry",
  "data": {
    "duration_s": 5.0,
    "samples_collected": 40,
    "metrics": {
      "angle_variance": 1.23,
      "angle_peak": 4.5,
      "angle_mean": 0.2,
      "output_mean": 45.2,
      "output_saturation_pct": 12.5,
      "oscillation_detected": false,
      "oscillation_freq_hz": null,
      "settling_time_ms": 850,
      "trend_direction": "stable"
    },
    "summary": "Stable with low variance (1.23°). Output well within limits. No oscillation detected.",
    "raw_samples": [...] // optional, if requested
  }
}
```

**Implementation Notes:**
- Subscribe to TelemetryHub WebSocket for duration
- Compute rolling statistics on angle, output
- Detect oscillation via zero-crossing or mini-FFT
- Settling time = time until variance drops below threshold
- Must handle disconnection gracefully

**Safety:** Read-only. No actuation.

**UI Category:** Blue (read)

### T1 Serial Lock & Backpressure Policy

Both `observe_telemetry` and `read_burst_capture` are **read-only** and **non-blocking**. They must not interfere with command/write tools or burst arming.

| Requirement | Policy |
|-------------|--------|
| **No write lock** | T1 tools never acquire serial write lock |
| **WebSocket-only** | `observe_telemetry` reads from `TelemetryHub` broadcast, not serial directly |
| **File-only** | `read_burst_capture` reads CSV files, no serial interaction |
| **Bounded retries** | WebSocket connect: max 3 retries, 500ms backoff |
| **Timeout contract** | If no data within `WEBSOCKET_TIMEOUT_S` (5s), **fail fast** with error code |
| **Burst read safety** | `read_burst_capture` checks `HostCaptureManager.status()['state']`; if `capturing`, return error `burst_in_progress` |
| **Concurrent T1 calls** | Multiple T1 calls allowed; they share WebSocket subscription |

### T1 Concurrency Matrix

| Active Operation | `observe_telemetry` | `read_burst_capture` |
|------------------|---------------------|----------------------|
| None | ✓ allowed | ✓ allowed |
| `observe_telemetry` running | ✓ allowed (shared WS) | ✓ allowed |
| `read_burst_capture` running | ✓ allowed | ✓ allowed |
| Burst `armed` | ✓ allowed | ✓ allowed (reads old CSV) |
| Burst `capturing` | ✓ allowed | ✗ error `burst_in_progress` |
| `run_experiment` active | ✓ allowed (read-only) | ✓ allowed |
| Serial write in progress | ✓ allowed (no serial use) | ✓ allowed (no serial use) |

> **Key:** `observe_telemetry` and `read_burst_capture` never block each other or write operations. Only `read_burst_capture` is blocked during active capture to prevent reading incomplete CSV.

### `observe_telemetry` Failure Modes (Explicit)

| Condition | Behavior | Error Code | Degraded Mode |
|-----------|----------|------------|---------------|
| WebSocket never connects (3 retries exhausted) | **Fail fast** | `E_WS_CONNECT_FAILED` | None — no HTTP fallback |
| WebSocket connects but no frames for 5s | **Fail fast** | `E_WS_NO_DATA` | None |
| WebSocket disconnects mid-observation | Return partial | `E_WS_DISCONNECT` | Return collected samples |
| 0 samples collected before disconnect | **Fail fast** | `E_WS_NO_SAMPLES` | None |
| Serial disconnected (gateway unhealthy) | **Fail fast** | `E_SERIAL_DISCONNECTED` | None |

**Design Decision:** No HTTP polling fallback. WebSocket is required for real-time observation. If WebSocket is unavailable, the tool fails explicitly so the agent can report the issue rather than silently degrade.

**Fail-Fast Response:**
```python
{
    "ok": false,
    "error": "E_WS_CONNECT_FAILED",
    "message": "WebSocket connection failed after 3 retries",
    "retry_after_s": 5  # suggested retry delay
}
```

**Partial Result Response (disconnect mid-observation):**
```python
{
    "ok": true,
    "partial": true,
    "error_code": "E_WS_DISCONNECT",
    "samples_collected": 12,
    "samples_expected": 40,
    "duration_actual_s": 1.5,
    "duration_requested_s": 5.0,
    "data": {...}  # metrics computed on collected samples
}
```

**Implementation Notes:**
- `observe_telemetry` subscribes to existing `TelemetryHub` broadcast queue
- No new serial commands are issued
- Check `gateway.health()['connected']` before attempting WS subscription
- If 0 samples collected, always fail (no partial with empty data)
- `read_burst_capture` only reads files; if `latest_run` is None, return `no_burst_data` error

---

### 2. `read_burst_capture`

**Purpose:** Read and analyze high-frequency burst capture data for oscillation diagnosis.

**Why Critical:** Burst captures run at 50-100Hz and contain critical oscillation data invisible to standard telemetry. Agent is currently blind to this.

**Integration Mode:** `wrapper`  
**Wraps:** `HostCaptureManager.status()` + `latest_run` CSV file parsing  
**Existing Path:**
- `GET /burst/status` → `HostCaptureManager.status()` returns metadata (`state`, `latest_run`, `rows`, etc.)
- `latest_run` field contains path to CSV file (e.g., `tests/results/host_run_1739922600.csv`)
- CSV header: `host_ts,mode,estop,ang,raw,gyro,set,out,pid,mot,wspd,wpos,kp,ki,kd,kv,kx,encL,encR,volRaw`

**Value-Add:** FFT frequency analysis, peak detection, phase lag computation, automated diagnosis—none available in existing paths.

```json
{
  "type": "function",
  "function": {
    "name": "read_burst_capture",
    "description": "Read and analyze burst CSV capture data. Returns frequency spectrum, peak oscillation amplitude, phase lag between angle and output.",
    "parameters": {
      "type": "object",
      "properties": {
        "capture_id": {
          "type": "string",
          "description": "Burst capture ID or 'latest' for most recent.",
          "default": "latest"
        },
        "analysis": {
          "type": "array",
          "items": { 
            "type": "string",
            "enum": ["fft", "peak_detect", "phase_lag", "envelope", "stats", "raw"]
          },
          "description": "Analysis types to perform.",
          "default": ["stats", "peak_detect"]
        },
        "freq_range_hz": {
          "type": "array",
          "items": { "type": "number" },
          "description": "Frequency range for FFT analysis [min, max]. Default [0.5, 25].",
          "default": [0.5, 25]
        }
      },
      "required": []
    }
  }
}
```

**Returns:**
```json
{
  "ok": true,
  "tool": "read_burst_capture",
  "data": {
    "capture_id": "burst_20260218_191500",
    "sample_count": 400,
    "duration_s": 5.0,
    "sample_rate_hz": 80,
    "stats": {
      "angle_mean": 0.15,
      "angle_std": 2.34,
      "angle_peak": 6.2,
      "output_mean": 52.3,
      "output_std": 28.1
    },
    "fft": {
      "dominant_freq_hz": 3.2,
      "dominant_amplitude": 4.5,
      "secondary_freq_hz": 6.4,
      "noise_floor_db": -45
    },
    "peak_detect": {
      "oscillation_detected": true,
      "oscillation_freq_hz": 3.2,
      "peak_to_peak_deg": 5.8,
      "damping_ratio": 0.15
    },
    "phase_lag": {
      "angle_to_output_ms": 45,
      "angle_to_output_deg": 52
    },
    "diagnosis": "3.2Hz oscillation detected (Kd too high or loop delay). Damping ratio 0.15 indicates underdamped response."
  }
}
```

**Implementation Notes:**
- Call `HostCaptureManager.status()` to get `latest_run` path
- Parse CSV using standard library (no external deps)
- Use canonical field names: `ang`, `out`, `gyro` (see Telemetry Schema)
- Implement simple FFT (numpy or pure Python)
- Peak detection via zero-crossing analysis
- Phase lag via cross-correlation
- Generate human-readable diagnosis
- **Row limit:** Stop parsing at `MAX_BURST_ROWS` (3000)
- **Row char limit:** Truncate rows exceeding `BURST_ROW_CHAR_LIMIT` (500)

**Safety:** Read-only. No actuation.

**UI Category:** Blue (read)

---

## Tier 2: Experimentation Tools

### 3. `run_experiment`

**Purpose:** Run controlled A/B experiment: apply change, observe, measure effect, optionally revert.

**Why Critical:** Enables structured tuning workflow with measured feedback and automatic safety revert.

**Integration Mode:** `new capability`  
**Wraps:** Internally uses `observe_telemetry`, `execute_command`, `safe_rollback`  
**Existing Path:** None—experiments are currently manual  
**Value-Add:** Structured A/B testing with automatic baseline capture and conditional rollback.

```json
{
  "type": "function",
  "function": {
    "name": "run_experiment",
    "description": "Run controlled experiment: capture baseline, apply change, observe effect, compare, optionally auto-revert if criteria not met.",
    "parameters": {
      "type": "object",
      "properties": {
        "change": {
          "type": "object",
          "description": "Change to apply. Either {cmd: 'PID 18 0.1 0.6'} or {variable: 'qAngle', value: '0.001'}",
          "properties": {
            "cmd": { "type": "string" },
            "variable": { "type": "string" },
            "value": { "type": "string" }
          }
        },
        "baseline_s": {
          "type": "number",
          "description": "Seconds to observe baseline before change. Default 5.",
          "default": 5
        },
        "observe_s": {
          "type": "number",
          "description": "Seconds to observe after change. Default 10.",
          "default": 10
        },
        "auto_revert": {
          "type": "boolean",
          "description": "Automatically revert if success_criteria not met. Default true.",
          "default": true
        },
        "success_criteria": {
          "type": "object",
          "description": "Thresholds for success. If any exceeded and auto_revert=true, reverts.",
          "properties": {
            "max_angle_variance": { "type": "number" },
            "max_output_saturation_pct": { "type": "number" },
            "no_oscillation": { "type": "boolean" }
          },
          "default": {
            "max_angle_variance": 5.0,
            "max_output_saturation_pct": 80,
            "no_oscillation": true
          }
        },
        "description": {
          "type": "string",
          "description": "Human-readable description for logging."
        }
      },
      "required": ["change"]
    }
  }
}
```

**Returns:**
```json
{
  "ok": true,
  "tool": "run_experiment",
  "data": {
    "experiment_id": "exp_20260218_192000",
    "change_applied": { "cmd": "PID 18 0.1 0.6" },
    "baseline": {
      "angle_variance": 1.5,
      "output_saturation_pct": 15,
      "oscillation_detected": false
    },
    "result": {
      "angle_variance": 2.8,
      "output_saturation_pct": 35,
      "oscillation_detected": false
    },
    "comparison": {
      "angle_variance_delta": +1.3,
      "output_saturation_delta": +20,
      "verdict": "degraded"
    },
    "success_criteria_met": false,
    "auto_reverted": true,
    "revert_cmd": "PID 15 0.1 0.5",
    "summary": "Experiment failed: angle variance increased 87%. Auto-reverted to previous PID."
  }
}
```

**Implementation Notes:**
- Store pre-change config for revert
- Use `observe_telemetry` internally for baseline/result
- Only allow safe commands (reuse allowlist)
- Log all experiments to `tool_audit` for learning

**Safety:** 
- Respects existing command allowlist
- Auto-revert provides safety net
- Cannot be used for ARM/DISARM
- **See Hard Safety Contract below**

**UI Category:** Amber (write)

---

### 4. `diff_config`

**Integration Mode:** `wrapper`  
**Wraps:** `query_checkpoints` + `execute_command GET`  
**Existing Path:** Checkpoints queryable via `query_checkpoints`; current config via `GET` serial command  
**Value-Add:** Unified diff view with delta percentages and summary—not available in existing paths.

**Purpose:** Compare current runtime config to a checkpoint, baseline, or factory defaults.

**Why Critical:** Essential for debugging "what changed?" regressions.

```json
{
  "type": "function",
  "function": {
    "name": "diff_config",
    "description": "Compare current runtime configuration to a checkpoint or baseline. Shows what parameters differ.",
    "parameters": {
      "type": "object",
      "properties": {
        "compare_to": {
          "type": "string",
          "enum": ["checkpoint", "factory", "session_start", "snapshot_id"],
          "description": "What to compare against.",
          "default": "checkpoint"
        },
        "checkpoint_id": {
          "type": "string",
          "description": "Checkpoint ID if compare_to='checkpoint'. Omit for best-rated."
        },
        "snapshot_id": {
          "type": "string",
          "description": "Config snapshot ID if compare_to='snapshot_id'."
        },
        "include_sketch": {
          "type": "boolean",
          "description": "Include sketch compile-time values in diff.",
          "default": false
        }
      },
      "required": []
    }
  }
}
```

**Returns:**
```json
{
  "ok": true,
  "tool": "diff_config",
  "data": {
    "compared_to": "checkpoint",
    "checkpoint_id": "cp_20260215_great",
    "checkpoint_rating": "great",
    "diffs": [
      { "param": "Kp", "current": 22.0, "reference": 18.0, "delta": "+22%" },
      { "param": "Kd", "current": 0.3, "reference": 0.6, "delta": "-50%" },
      { "param": "setpoint", "current": 2.0, "reference": 0.0, "delta": "+2.0" }
    ],
    "identical": ["Ki", "maxOutput", "deadband"],
    "summary": "3 parameters differ from 'great' checkpoint. Kp increased 22%, Kd halved."
  }
}
```

**Implementation Notes:**
- Query current config via `GET` command
- Load checkpoint from `CodexDB`
- Compute percentage/absolute deltas
- Factory defaults from constants

**Safety:** Read-only. No actuation.

**UI Category:** Blue (read)

---

### 5. `safe_rollback`

**Purpose:** Instantly revert to last checkpoint rated 'good' or better.

**Why Critical:** Fast recovery from failed tuning attempts without UI navigation.

**Integration Mode:** `wrapper`  
**Wraps:** `query_checkpoints` + `execute_command`  
**Existing Path:** Manual: query checkpoint via `query_checkpoints`, then manually issue commands  
**Value-Add:** One-call rollback with scope control, dry-run preview, and audit logging.

```json
{
  "type": "function",
  "function": {
    "name": "safe_rollback",
    "description": "Revert to the most recent checkpoint with specified minimum rating. Faster than manual UI rollback.",
    "parameters": {
      "type": "object",
      "properties": {
        "min_rating": {
          "type": "string",
          "enum": ["ok", "good", "great"],
          "description": "Minimum checkpoint rating to consider. Default 'good'.",
          "default": "good"
        },
        "scope": {
          "type": "string",
          "enum": ["pid", "all_runtime", "motion", "limits"],
          "description": "What to revert. 'pid' = PID params only, 'all_runtime' = all serial-settable params.",
          "default": "pid"
        },
        "checkpoint_id": {
          "type": "string",
          "description": "Specific checkpoint ID. If omitted, uses most recent matching min_rating."
        },
        "dry_run": {
          "type": "boolean",
          "description": "If true, show what would change without applying.",
          "default": false
        }
      },
      "required": []
    }
  }
}
```

**Returns:**
```json
{
  "ok": true,
  "tool": "safe_rollback",
  "data": {
    "checkpoint_id": "cp_20260218_good",
    "checkpoint_rating": "good",
    "checkpoint_ts": 1739920000,
    "scope": "pid",
    "changes_applied": [
      { "param": "Kp", "from": 22.0, "to": 18.0 },
      { "param": "Kd", "from": 0.3, "to": 0.6 }
    ],
    "commands_sent": ["PID 18 0.1 0.6"],
    "dry_run": false,
    "summary": "Rolled back PID to checkpoint 'cp_20260218_good' (rated good). Kp: 22→18, Kd: 0.3→0.6"
  }
}
```

**Implementation Notes:**
- Query checkpoints from `CodexDB` sorted by rating + time
- Generate appropriate serial commands
- Respects command allowlist (no ARM/DISARM)
- Log rollback to `tool_audit`

**Safety:**
- Only restores to known-good checkpoints
- Respects command allowlist
- Dry-run option for preview
- **See Hard Safety Contract below**

**UI Category:** Amber (write)

---

## Tier 3: Intelligence Tools

### 6. `simulate_pid_response`

**Purpose:** Predict effect of PID parameter change using physics model before applying.

**Why Critical:** Enables "what-if" analysis without risking the robot.

**Integration Mode:** `new capability`  
**Wraps:** None  
**Existing Path:** None—no simulation capability exists  
**Value-Add:** What-if analysis before committing to real hardware changes.

```json
{
  "type": "function",
  "function": {
    "name": "simulate_pid_response",
    "description": "Simulate the effect of PID parameter changes on balance response using physics model. Does NOT apply changes.",
    "parameters": {
      "type": "object",
      "properties": {
        "proposed_pid": {
          "type": "object",
          "properties": {
            "Kp": { "type": "number" },
            "Ki": { "type": "number" },
            "Kd": { "type": "number" }
          },
          "description": "Proposed PID values. Omit unchanged params."
        },
        "perturbation_deg": {
          "type": "number",
          "description": "Initial angle perturbation for simulation. Default 5.",
          "default": 5
        },
        "simulation_s": {
          "type": "number",
          "description": "Simulation duration. Default 3.",
          "default": 3
        },
        "compare_to_current": {
          "type": "boolean",
          "description": "Also simulate current PID for comparison.",
          "default": true
        }
      },
      "required": ["proposed_pid"]
    }
  }
}
```

**Returns:**
```json
{
  "ok": true,
  "tool": "simulate_pid_response",
  "data": {
    "proposed": {
      "pid": { "Kp": 20, "Ki": 0.1, "Kd": 0.5 },
      "settling_time_ms": 450,
      "overshoot_pct": 15,
      "steady_state_error_deg": 0.2,
      "stability": "stable",
      "oscillation_risk": "low"
    },
    "current": {
      "pid": { "Kp": 15, "Ki": 0.1, "Kd": 0.6 },
      "settling_time_ms": 800,
      "overshoot_pct": 5,
      "steady_state_error_deg": 0.5,
      "stability": "stable",
      "oscillation_risk": "low"
    },
    "comparison": {
      "settling_time_delta": "-44%",
      "overshoot_delta": "+10%",
      "recommendation": "Proposed PID is faster but with more overshoot. Consider Kd=0.55 for balance."
    },
    "model_assumptions": "Inverted pendulum, 200g mass, 15cm height, 10ms loop"
  }
}
```

**Implementation Notes:**
- Inverted pendulum state-space model
- Use robot params from probe results (mass, height)
- Linearized around vertical equilibrium
- Step response analysis
- Clear about model limitations

**Safety:** Simulation only. No actuation.

**UI Category:** Blue (read)

---

### 7. `suggest_next_step`

**Purpose:** ML/heuristic recommendation for next tuning action based on current state.

**Why Critical:** Guides users who don't know what to try next.

**Integration Mode:** `new capability`  
**Wraps:** Internally uses `observe_telemetry`, `query_checkpoints`, `search_docs`  
**Existing Path:** None—no recommendation engine exists  
**Value-Add:** AI-powered tuning guidance with confidence scores and rationale.

```json
{
  "type": "function",
  "function": {
    "name": "suggest_next_step",
    "description": "Analyze current tuning state and suggest the most promising next action based on telemetry patterns and successful historical sessions.",
    "parameters": {
      "type": "object",
      "properties": {
        "context": {
          "type": "string",
          "description": "User's goal or problem description.",
          "default": ""
        },
        "include_rationale": {
          "type": "boolean",
          "description": "Include detailed reasoning for suggestion.",
          "default": true
        },
        "max_suggestions": {
          "type": "integer",
          "description": "Number of suggestions to return. Default 3.",
          "default": 3
        }
      },
      "required": []
    }
  }
}
```

**Returns:**
```json
{
  "ok": true,
  "tool": "suggest_next_step",
  "data": {
    "current_state": {
      "angle_variance": 3.2,
      "oscillation_detected": true,
      "oscillation_freq_hz": 4.1,
      "output_saturation_pct": 45
    },
    "suggestions": [
      {
        "rank": 1,
        "action": "Reduce Kd by 20%",
        "command": "PID 18 0.1 0.48",
        "confidence": 0.85,
        "rationale": "4.1Hz oscillation is characteristic of derivative kick. Historical data shows Kd reduction resolves this pattern 85% of the time.",
        "expected_outcome": "Oscillation should decrease within 2-3 seconds"
      },
      {
        "rank": 2,
        "action": "Increase loop filter (if available)",
        "command": null,
        "confidence": 0.6,
        "rationale": "High-frequency oscillation may benefit from derivative filtering.",
        "expected_outcome": "Smoother response, reduced noise sensitivity"
      },
      {
        "rank": 3,
        "action": "Reduce Kp by 10%",
        "command": "PID 16.2 0.1 0.6",
        "confidence": 0.5,
        "rationale": "If Kd reduction doesn't help, overall gain may be too high.",
        "expected_outcome": "Slower but more stable response"
      }
    ],
    "data_sources": ["current_telemetry", "similar_checkpoints", "knowledge_base"]
  }
}
```

**Implementation Notes:**
- Rule-based expert system initially
- Pattern matching against successful checkpoints
- RAG search for relevant knowledge
- Future: ML model trained on session outcomes

**Safety:** Suggestions only. User/agent must explicitly apply.

**UI Category:** Blue (read)

---

### 8. `annotate_session`

**Purpose:** Add notes, tags, and context to telemetry timeline for learning and recall.

**Why Critical:** Enables agent to remember what was tried and why, building institutional knowledge.

**Integration Mode:** `new capability`  
**Wraps:** New `session_annotations` table in `CodexDB`  
**Existing Path:** None—no annotation capability exists  
**Value-Add:** Persistent learning and context for future sessions.

```json
{
  "type": "function",
  "function": {
    "name": "annotate_session",
    "description": "Add annotation to current session timeline. Useful for marking experiments, observations, and learnings.",
    "parameters": {
      "type": "object",
      "properties": {
        "note": {
          "type": "string",
          "description": "Annotation text. What happened, what was learned."
        },
        "tags": {
          "type": "array",
          "items": { "type": "string" },
          "description": "Tags for categorization: 'oscillation', 'breakthrough', 'failed_experiment', etc."
        },
        "severity": {
          "type": "string",
          "enum": ["info", "success", "warning", "failure"],
          "description": "Annotation severity/type.",
          "default": "info"
        },
        "related_config": {
          "type": "object",
          "description": "Config snapshot to associate with this annotation."
        },
        "ts": {
          "type": "number",
          "description": "Timestamp to annotate. Default is now."
        }
      },
      "required": ["note"]
    }
  }
}
```

**Returns:**
```json
{
  "ok": true,
  "tool": "annotate_session",
  "data": {
    "annotation_id": "ann_20260218_193000",
    "ts": 1739922600,
    "note": "Kp=22 caused 4Hz oscillation. Reduced to 18, oscillation resolved. Sweet spot appears to be 16-19.",
    "tags": ["oscillation", "pid_tuning", "kp_sensitivity"],
    "severity": "success",
    "session_id": "session_20260218"
  }
}
```

**Implementation Notes:**
- Store in `CodexDB` (new `annotations` table)
- Link to telemetry timestamps
- Queryable for future context injection
- Exportable for training data

**Safety:** Write to DB only. No actuation.

**UI Category:** Amber (write)

---

## Hard Safety Contract (Write Tools)

The following **non-optional guardrails** apply to `run_experiment` and `safe_rollback`. These are enforced at the tool executor level and cannot be overridden by the agent or user.

### 1. Bounded Parameter Deltas

Each tunable parameter has a **maximum step size per call**. The tool will reject changes exceeding these bounds.

| Parameter | Max Step | Rationale |
|-----------|----------|-----------|
| `Kp` | ±5.0 (or ±25% of current) | Prevents runaway gain |
| `Ki` | ±0.2 (or ±50% of current) | Integral windup risk |
| `Kd` | ±0.3 (or ±30% of current) | Derivative kick risk |
| `setpoint` | ±5.0° | Physical tilt limits |
| `maxOutput` | ±30 | Prevents motor saturation abuse |
| `deadband` | ±10 | Motor protection |

**Implementation:**
```python
PARAM_MAX_DELTA = {
    "Kp": (5.0, 0.25),      # (absolute, relative)
    "Ki": (0.2, 0.50),
    "Kd": (0.3, 0.30),
    "setpoint": (5.0, None),
    "maxOutput": (30, 0.30),
    "deadband": (10, 0.50),
}

def validate_param_delta(param: str, current: float, proposed: float) -> bool:
    if param not in PARAM_MAX_DELTA:
        return False  # Unknown param = reject
    abs_max, rel_max = PARAM_MAX_DELTA[param]
    delta = abs(proposed - current)
    if delta > abs_max:
        return False
    if rel_max and current != 0 and delta / abs(current) > rel_max:
        return False
    return True
```

### 2. Runtime Limits

| Limit | Value | Applies To |
|-------|-------|------------|
| Max experiment duration | **60 seconds** | `run_experiment` |
| Max baseline duration | **15 seconds** | `run_experiment` |
| Max observation duration | **30 seconds** | `run_experiment`, `observe_telemetry` |
| Max writes per tool call | **3 commands** | `run_experiment`, `safe_rollback` |
| Cooldown between experiments | **5 seconds** | `run_experiment` |

**Implementation:**
```python
EXPERIMENT_LIMITS = {
    "max_total_duration_s": 60,
    "max_baseline_s": 15,
    "max_observe_s": 30,
    "max_writes_per_call": 3,
    "cooldown_s": 5,
}
```

### 3. Auto-Stop Triggers (Immediate Abort + Rollback)

The tool **must immediately abort and rollback** if any of the following conditions are detected during execution:

| Trigger | Detection Method | Action |
|---------|------------------|--------|
| **E-Stop latched** | `control.estop_latched == True` | Abort, rollback, return error |
| **Watchdog trip** | `control.watchdog_tripped == True` | Abort, rollback, return error |
| **Mode fault** | `status['mode'] not in SAFE_MODES` | Abort, rollback, return error |
| **Serial timeout** | No response within `SERIAL_TIMEOUT_S` (2s) | Abort, rollback, return error |
| **Repeated write failure** | 2+ consecutive failed writes | Abort, rollback, return error |
| **Angle fault** | `abs(status['ang']) > 45°` for 500ms | Abort, rollback, return error |
| **Output saturation** | `abs(status['out']) > 242` (95%) for 2s | Abort, rollback, return error |

**SAFE_MODES:** `{'SAFE_IDLE', 'IDLE', 'ARMED', 'BALANCING'}`

**Implementation:**
```python
@dataclass
class SafetyMonitor:
    """Monitors safety conditions during experiment execution."""
    
    def check_abort_conditions(self, control: BridgeControlState, status: dict) -> Optional[str]:
        """Returns abort reason if any condition triggered, else None."""
        if control.estop_latched:
            return "estop_latched"
        if control.watchdog_tripped:
            return "watchdog_trip"
        mode = status.get("mode", "UNKNOWN")
        if mode not in SAFE_MODES:
            return f"mode_fault:{mode}"
        ang = float(status.get("ang", 0))
        if abs(ang) > 45:
            return "angle_fault"
        return None
```

### 4. Rollback Idempotency

Rollback operations **must be idempotent** — calling rollback multiple times with the same checkpoint must produce the same final state.

**Requirements:**
- Rollback stores the **target state**, not a sequence of commands
- Before applying rollback, current state is compared to target; only differing params are updated
- Rollback commands are logged with a unique `rollback_id` for auditability
- If rollback fails, the failure is logged and the tool returns `ok=false` with the partial state

**Implementation:**
```python
def idempotent_rollback(target_config: dict, current_config: dict) -> List[str]:
    """Generate only the commands needed to reach target state."""
    commands = []
    for param, target_value in target_config.items():
        current_value = current_config.get(param)
        if current_value != target_value:
            cmd = generate_command_for_param(param, target_value)
            if cmd:
                commands.append(cmd)
    return commands
```

### 5. Pre-Flight Checklist

Before any write operation, the tool **must verify**:

| Check | Requirement | Failure Action |
|-------|-------------|----------------|
| Serial connected | `gateway.health()['connected'] == True` | Abort with `serial_not_connected` |
| No active experiment | `_active_experiment_id is None` | Abort with `experiment_in_progress` |
| Cooldown elapsed | `time.time() - _last_experiment_ts > cooldown_s` | Abort with `cooldown_not_elapsed` |
| Valid checkpoint exists | For rollback: checkpoint must exist in DB | Abort with `no_valid_checkpoint` |
| Mode is safe | `mode in SAFE_MODES` | Abort with `unsafe_mode` |

**SAFE_MODES** for write operations: `{'SAFE_IDLE', 'IDLE', 'ARMED', 'BALANCING'}`

### 6. Audit Trail

All write operations **must log** to `tool_audit` table:

```python
{
    "tool": "run_experiment",
    "experiment_id": "exp_...",
    "pre_state": {...},       # Config before change
    "post_state": {...},      # Config after change (or attempted)
    "commands_sent": [...],   # Actual serial commands
    "abort_reason": null,     # Or string if aborted
    "rollback_performed": false,
    "rollback_success": null,
    "duration_ms": 12345,
    "ts": 1739922600.0
}
```

### 7. Error Recovery Matrix

| Failure Mode | Recovery Action | User Notification |
|--------------|-----------------|-------------------|
| Write command fails | Retry once, then abort + rollback | "Command failed, rolled back" |
| Rollback fails | Log error, return partial state | "Rollback incomplete: {details}" |
| Timeout during observe | Abort experiment, keep current state | "Observation timeout, no changes applied" |
| Safety trigger during baseline | Abort, no rollback needed | "Safety condition during baseline" |
| Safety trigger during experiment | Immediate rollback | "Safety abort: {reason}, rolled back" |

---

## Implementation Priority

### Sprint 3: Feedback Loop (T1)
| Tool | Effort | Dependencies |
|------|--------|--------------|
| `observe_telemetry` | M | TelemetryHub WebSocket |
| `read_burst_capture` | M | HostCaptureManager |

#### Sprint 3 Acceptance Tests

**`observe_telemetry` Tests:**

| Test ID | Scenario | Input | Pass Threshold |
|---------|----------|-------|----------------|
| OT-01 | WebSocket disconnect mid-observation | Disconnect WS after 2s of 5s observation | `partial: true`, `error_code: E_WS_DISCONNECT`, `samples_collected >= 10` |
| OT-02 | Sparse/low sample count | 3 samples in 5s window | `partial: true`, `samples_collected: 3`, metrics computed (not null) |
| OT-03 | Connection timeout | WS never connects (mock) | `ok: false`, `error: E_WS_CONNECT_FAILED`, response time < 6s |
| OT-04 | Metric correctness (fixture) | `fixtures/telemetry_50_oscillating.json` | See tolerance table below |
| OT-05 | Duration limit enforcement | `duration_s: 60` | Actual observation ≤ 30s, no error |
| OT-06 | Immediate trigger | `trigger: immediate` | First sample timestamp < 500ms from call |
| OT-07 | On-balance trigger timeout | `trigger: on_balance`, mode stays SAFE_IDLE | `ok: false`, `error: E_TRIGGER_TIMEOUT` after 30s |

**OT-04 Metric Tolerances (fixture: 50 samples, `ang` = [1, 2, 1, 2, ...]):**

| Metric | Expected | Tolerance | Pass Condition |
|--------|----------|-----------|----------------|
| `angle_variance` | 0.25 | ±0.02 | 0.23 ≤ value ≤ 0.27 |
| `angle_mean` | 1.5 | ±0.01 | 1.49 ≤ value ≤ 1.51 |
| `angle_peak` | 2.0 | ±0.01 | 1.99 ≤ value ≤ 2.01 |
| `oscillation_detected` | true | exact | value == true |
| `sample_count` | 50 | exact | value == 50 |

**`read_burst_capture` Tests:**

| Test ID | Scenario | Input | Pass Threshold |
|---------|----------|-------|----------------|
| RB-01 | Missing `latest_run` CSV | `status()['latest_run'] == None` | `ok: false`, `error: E_NO_BURST_DATA` |
| RB-02 | Malformed CSV rows | `fixtures/burst_malformed.csv` (100 rows, 3 bad) | `ok: true`, `warnings` contains `skipped_rows: 3`, `sample_count: 97` |
| RB-03 | Oversized file (row cap) | `fixtures/burst_5000_rows.csv` | `ok: true`, `truncated: true`, `sample_count: 3000` |
| RB-04 | Row char limit | `fixtures/burst_long_rows.csv` | Rows parsed without crash, `warnings` logged |
| RB-05 | Burst in progress | `status()['state'] == 'capturing'` | `ok: false`, `error: E_BURST_IN_PROGRESS` |
| RB-06 | Metadata exists, CSV missing | `latest_run` path but file deleted | `ok: false`, `error: E_CSV_NOT_FOUND` |
| RB-07 | FFT analysis accuracy | `fixtures/burst_80hz_4hz_sine.csv` | See tolerance table below |
| RB-08 | Empty CSV (header only) | `fixtures/burst_header_only.csv` | `ok: false`, `error: E_NO_BURST_SAMPLES` |

**RB-07 FFT Tolerances (fixture: 400 samples @ 80Hz, pure 4Hz sine on `ang`):**

| Metric | Expected | Tolerance | Pass Condition |
|--------|----------|-----------|----------------|
| `fft.dominant_freq_hz` | 4.0 | ±0.5 | 3.5 ≤ value ≤ 4.5 |
| `fft.dominant_amplitude` | 1.0 | ±0.15 | 0.85 ≤ value ≤ 1.15 |
| `peak_detect.oscillation_detected` | true | exact | value == true |
| `peak_detect.oscillation_freq_hz` | 4.0 | ±0.5 | 3.5 ≤ value ≤ 4.5 |
| `stats.angle_std` | 0.707 | ±0.05 | 0.657 ≤ value ≤ 0.757 |

**Test Fixtures (location: `app/bridge/tests/fixtures/`):**

| Fixture | Description | Generation |
|---------|-------------|------------|
| `telemetry_50_oscillating.json` | 50 samples, `ang` alternates [1,2,1,2,...], `out` = 50 | Static, checked in |
| `burst_80hz_4hz_sine.csv` | 400 rows @ 80Hz, `ang` = sin(2π·4·t), amplitude=1 | Generated via `generate_test_fixtures.py` |
| `burst_malformed.csv` | 100 rows, rows 10/50/90 missing `ang` column | Static, checked in |
| `burst_5000_rows.csv` | 5000 valid rows for truncation test | Generated via script |
| `burst_long_rows.csv` | 50 rows, each row padded to 800 chars | Static, checked in |
| `burst_header_only.csv` | Header row only, no data | Static, checked in |

### Sprint 4: Experimentation (T2)
| Tool | Effort | Dependencies |
|------|--------|--------------|
| `diff_config` | S | CodexDB checkpoints |
| `safe_rollback` | S | CodexDB, execute_command |
| `run_experiment` | L | observe_telemetry, safe_rollback |

### Sprint 5: Intelligence (T3)
| Tool | Effort | Dependencies |
|------|--------|--------------|
| `annotate_session` | S | New DB table |
| `suggest_next_step` | L | All T1/T2 tools, RAG |
| `simulate_pid_response` | L | Physics model |

---

## Database Schema Additions

```sql
-- Session annotations table
CREATE TABLE IF NOT EXISTS session_annotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    session_id TEXT,
    note TEXT NOT NULL,
    tags_json TEXT DEFAULT '[]',
    severity TEXT DEFAULT 'info',
    config_json TEXT,
    created_by TEXT DEFAULT 'agent'
);
CREATE INDEX idx_annotations_ts ON session_annotations(ts);
CREATE INDEX idx_annotations_session ON session_annotations(session_id);

-- Experiment log table
CREATE TABLE IF NOT EXISTS experiment_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    experiment_id TEXT UNIQUE,
    change_json TEXT NOT NULL,
    baseline_json TEXT,
    result_json TEXT,
    success INTEGER,
    auto_reverted INTEGER DEFAULT 0,
    description TEXT
);
CREATE INDEX idx_experiments_ts ON experiment_log(ts);
```

---

## UI Updates Required

### ToolCallCard Categories
Add to existing category mapping:
```typescript
const TOOL_CATEGORIES = {
  // Existing...
  observe_telemetry: 'read',
  read_burst_capture: 'read',
  diff_config: 'read',
  simulate_pid_response: 'read',
  suggest_next_step: 'read',
  run_experiment: 'write',
  safe_rollback: 'write',
  annotate_session: 'write',
};
```

### New Visualization Components (Future)
- `ObservationResultCard` — Live metrics display
- `ExperimentResultCard` — Before/after comparison
- `SuggestionCard` — Ranked recommendations with confidence

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Tuning session time to "good" | -40% |
| Failed experiments auto-reverted | 100% |
| Agent suggestions accepted | >60% |
| User checkpoint ratings | +0.5 avg |

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Simulation model inaccuracy | Clear disclaimers, compare to real results |
| Experiment revert failure | Store pre-change config, manual revert UI fallback |
| Suggestion overconfidence | Show confidence scores, require user approval |
| Telemetry observation blocking | Async with timeout, graceful degradation |

---

## Acceptance Criteria

- [ ] All 8 tools have OpenAI function definitions
- [ ] All tools return structured `ToolResult`
- [ ] Safety allowlists enforced for write operations
- [ ] Tool audit logging for all executions
- [ ] Unit tests for each tool
- [ ] Integration test: full experiment workflow
- [ ] UI displays all tool results correctly
- [ ] Sprint 3 acceptance tests passing (OT-01 through OT-07, RB-01 through RB-08)

---

## Unresolved Assumptions (Architect Decision Required)

| ID | Question | Options | Recommendation |
|----|----------|---------|----------------|
| UA-01 | Should `observe_telemetry` support custom metrics via user-defined expressions? | A) Fixed metric set only B) Allow simple expressions (e.g., `ang - set`) | **A** for v2, defer expressions to v3 |
| UA-02 | FFT implementation: numpy dependency acceptable? | A) Require numpy B) Pure Python FFT C) Optional numpy with fallback | **C** — numpy if available, else simplified periodogram |
| UA-03 | `on_balance` trigger timeout: how long to wait for BALANCING mode? | A) 30s hard limit B) Configurable C) Indefinite with cancel | **A** — 30s hard limit, return timeout error |
| UA-04 | Burst CSV encoding: assume UTF-8 or detect? | A) UTF-8 only B) Detect with chardet | **A** — UTF-8 only, log warning on decode errors |
| UA-05 | Should `read_burst_capture` support historical captures (not just `latest`)? | A) Latest only B) Allow capture_id lookup | **B** — Allow lookup by filename/timestamp prefix |
| UA-06 | Concurrent experiment protection: per-session or global? | A) Global singleton B) Per-session lock | **A** — Global singleton, one experiment at a time across all sessions |

# Multi-Hardware Profile Contract v1

**Version:** `1.0.0-draft`  
**Status:** `Active for planning, partially implemented in backend`  
**Owner:** `UpRight.os Requirement Owner: Codex + JVKE`  
**Last Updated:** `2026-02-24`

---

## 1) Purpose

Define one hardware-adaptive contract for clean-lane UX and safety gates, so new bots are added by config/manifests instead of UI rewrites.

This contract is future-facing and intentionally supports a temporary exception for the current Nano test bot.

---

## 2) Operating Modes

### 2.1 `single_bot_test` (current bot, active now)

Use for one-off test bot tuning where speed of iteration matters more than profile UX.

Rules:
- No required profile selection screen.
- Active hardware is treated as implicit.
- Compatibility checks are informational unless safety-critical.
- Keep fail-closed arm/prearm safety checks enabled.
- Do not add permanent global UX complexity for temporary Nano constraints.

Exit criteria from `single_bot_test`:
- At least one additional hardware target is active, or
- New bot bring-up begins with non-compatible board/sensor/driver stack.

### 2.2 `multi_hardware` (future default)

Use once more than one bot/hardware stack is in active circulation.

Rules:
- Explicit profile selection is required.
- Capability flags drive which controls are shown.
- Runtime/profile mismatch blocks risky actions.
- Calibration freshness and compatibility are enforced before tuning.

---

## 3) Contract Requirements

### 3.1 Profile-first setup

Required in `multi_hardware` mode:
- Select `hardware_profile_id` before tune/arm flows.
- Resolve board + IMU + driver + actuator class from profile.
- Hide unsupported controls by capability flags.

Current mapping:
- `GET /profiles/hardware`
- `GET /firmware/targets`

### 3.2 Capability-driven controls

Controls must render from runtime/profile capabilities, not static UI assumptions.

Examples:
- IMU calibration controls only when calibration commands are supported.
- Motor probe/stall test controls only when runtime supports commands.
- Advanced filter/Kalman controls only when firmware exposes them.

Current mapping:
- `GET /probe/compat`
- `GET /status` (`status.telemetry_adapter`, compatibility/tuning capabilities cache path)

### 3.3 Runtime identity and compatibility gate

On connect/preflight:
- Verify runtime manifest validity.
- Verify profile/runtime compatibility.
- Block risky actions on hard mismatch.

Current mapping:
- `GET /firmware/runtime-manifest`
- `POST /firmware/runtime-manifest/validate`
- `POST /firmware/runtime-manifest/compat`
- `POST /agent/clean/preflight` / `POST /agent/clean/preflight/stream`

### 3.4 Calibration workflows per hardware

Contract must support separate flows for:
- IMU bias calibration
- Pose zero calibration
- Motor polarity/driver mapping
- Encoder direction/scale checks

Persist and display:
- `calibrated_at`
- `firmware/runtime identity`
- `profile_id`
- calibration freshness state

### 3.5 Safety policy per platform

Pre-arm requirements must be hardware-aware and fail closed.

Required:
- profile-specific pre-arm checks
- estop latch/unlatch validation
- arm block on safety gate fail

Current mapping:
- `POST /arm/precheck`
- clean preflight gates

### 3.6 Adaptive telemetry panel contract

Must always show normalized core fields:
- `mode`, `fault`, `estop`, `ang`, `raw`, `gyro`, `out`

May show hardware-specific fields additively.
Missing unsupported signals must be explicit (not silently absent).

### 3.7 Tuning surface by control topology

UI must support:
- simple mode (safe minimal knobs)
- advanced mode (topology-specific knobs)

Topology examples:
- single-loop balance
- cascade loops
- state-space implementations

### 3.8 Evidence and score normalization

Every scored tuning artifact must include:
- `profile_id` (or `single_bot_test` marker)
- runtime identity (`ident`, `runtime`, `tune`)
- calibration state
- capture configuration identity

Cross-profile comparison is blocked unless normalized.

### 3.9 First-run onboarding for new hardware

When `multi_hardware` is active, first-run wizard must set:
- profile
- board target/FQBN/port
- required calibration sequence
- known-good rollback snapshot

### 3.10 Extensibility model

New bot support should be additive:
- add profile/manifest/config entries
- avoid hardcoded per-bot UI branches

---

## 4) Current Code-Path Mapping

Backend contract surfaces already present:
- `/profiles/hardware`
- `/firmware/targets`
- `/firmware/runtime-manifest`
- `/firmware/runtime-manifest/validate`
- `/firmware/runtime-manifest/compat`
- `/probe/compat`
- `/agent/clean/preflight`
- `/agent/clean/preflight/stream`
- `/arm/precheck`

Primary implementation files:
- `app/bridge/server.py`
- `app/bridge/clean_firmware_ops.py`
- `app/bridge/clean_preflight.py`
- `app/bridge/clean_route_helpers.py`

Primary UI surfaces:
- `app/ui/ops-console/src/CleanApp.tsx`
- `app/ui/ops-console/src/clean/CleanTuningSection.tsx`
- `app/ui/ops-console/src/clean/cleanApi.ts`

---

## 5) Rollout Rules

### 5.1 What is active now

Active mode for this bot:
- `single_bot_test`

Rationale:
- current objective is proving autonomous balance + valid tuning evidence
- avoid overfitting UI/process to temporary Nano limits

### 5.2 Trigger to activate `multi_hardware`

Activate when any of:
- second bot/hardware stack enters bring-up
- board/sensor/driver class changes
- profile mismatch risks become common in ops

### 5.3 Migration safety rule

When enabling `multi_hardware`, do not break the current test bot path:
- keep `single_bot_test` fallback until parity evidence passes
- remove fallback only after stable replacement evidence

---

## 6) Source Notes

This contract shape aligns with observed patterns from:
- Segway RMP gain-schedule and mode/safety model
- ODrive control-mode + calibration + watchdog/error model
- VESC app/profile config + runtime gating and persisted offsets

Reference links:
- `https://www.manuallib.com/file/3199588/`
- `https://docs.odriverobotics.com/v/latest/manual/control.html`
- `https://docs.odriverobotics.com/v/latest/fibre_types/com_odriverobotics_ODrive.html`
- `https://github.com/vedderb/bldc/blob/master/applications/finn/app_finn_az.c`
- `https://github.com/vedderb/bldc/blob/master/applications/finn/app_finn_az_conf.h`
- `https://github.com/vedderb/bldc/blob/master/motor/mcconf_default.h`
- `https://patents.google.com/patent/US20090115149A1/en`

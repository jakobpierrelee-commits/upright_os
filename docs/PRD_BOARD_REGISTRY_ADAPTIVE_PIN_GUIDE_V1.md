# PRD: Board Registry + Adaptive Pin Guide

**Version:** 1.1
**Status:** Active (Planned)
**Owner:** UpRight.os Setup + Agent Track
**Last Updated:** 2026-02-20
**Primary Branch:** `recover/uiux-restore-2026-02-19`

---

## 1. Problem

Current Setup wiring guidance is partially hardcoded and only supports a small subset of board profiles.
This causes:

1. Inconsistent board naming (`fqbn` vs UI label vs user text).
2. Weak per-model pin validation (especially ESP32 boot/strap and PWM constraints).
3. Pin-guide visuals that do not scale to many board revisions (Nano variants, DevKit variants, Teensy variants).
4. Agent and UI drift risk when board assumptions differ.

---

## 2. Goal

Create a canonical, model-aware board registry that powers:

1. Setup board selection.
2. Adaptive board rendering (small + large popout).
3. Logical-role to physical-pin mapping validation.
4. Agent prompt/handoff payload generation.
5. Sketch generation guardrails.

Success means the same board truth is reused across Setup UI, agent workflow, and generated scaffold assumptions.

---

## 3. Scope

### In Scope (v1)

1. Canonical local board registry data source.
2. Resolver from user/`fqbn`/probe text to exact model profile.
3. Pin-capability validator (PWM/I2C/SPI/UART/basic reserved pins).
4. Adaptive board renderer:
   - Compact card in Setup.
   - Large popout pin map for assembly.
5. Agent handoff payload compatibility from the same resolved model.

### Out of Scope (v1)

1. Full auto-ingest of every vendor board page.
2. Electrical simulation.
3. Auto-wiring inference from photos.
4. Firmware-side dynamic pin remap beyond current scaffold flow.

---

## 4. Functional Requirements

### FR1: Registry

System must store board profiles with:

1. `family` (arduino_nano, arduino_uno, esp32_devkitc, teensy, etc.)
2. `model` (nano, nano_every, nano_33_iot, nano_esp32, esp32-devkitc-v4, esp32-devkitc-v3, teensy41)
3. `aliases` (human names, marketing names, common misspellings)
4. `fqbn_patterns` (for resolver matching)
5. `pin_layout` (ordered left/right rails for UI)
6. `pin_capabilities` (PWM, ADC, I2C role, interrupt, restricted)
7. `electrical_rules` (logic level, safe voltage notes)
8. `reserved_pins` and warnings (boot straps, USB/UART conflicts)
9. `defaults` for common roles (SDA/SCL/LED etc.)

### FR2: Resolver

Given selected board text + probe info, system must:

1. Resolve one profile with confidence score.
2. Surface ambiguity when confidence < threshold.
3. Require explicit model selection when multiple variants are plausible.

### FR3: Validation

Given `pinMap`, system must return:

1. `errors` (invalid assignment, unsafe pin usage).
2. `warnings` (non-ideal but allowed mapping).
3. `info` (recommended alternatives).

### FR4: UI Rendering

Pin guide must render from registry data only (no per-board hardcoded JSX branches).

### FR5: Agent Consistency

`Agent Handoff Payload` must include:

1. resolved `family/model/version`.
2. confidence and assumptions.
3. normalized logical-role pin map.

### FR6: Live Agent Hardware Awareness

Every chat turn must carry current setup hardware context so the agent stays aligned with selected parts.

Requirements:

1. Setup publishes normalized hardware context (`board`, `resolved_profile`, `capabilities`, `hardware`, `pins`, lock/sketch state).
2. Backend persists per-session hardware context and injects it into assistant context for:
   - `/ai/chat`
   - `/ai/chat/tools`
   - `/ai/chat/stream`
3. On context change, assistant response starts with a short deterministic notice so users know recommendations are now based on updated parts.
4. Invalid/non-object context payloads are ignored safely without breaking chat flow.

---

## 5. Data Model

### 5.1 File Layout

1. `app/ui/ops-console/src/hardware/boardRegistry.ts`
2. `app/ui/ops-console/src/hardware/boardResolver.ts`
3. `app/ui/ops-console/src/hardware/pinValidation.ts`
4. `app/ui/ops-console/src/hardware/types.ts`

### 5.2 Type Sketch

```ts
type BoardProfile = {
  id: string;
  family: string;
  model: string;
  revision?: string;
  aliases: string[];
  fqbnPatterns: string[];
  rails: {
    left: string[];
    right: string[];
  };
  pinCapabilities: Record<string, {
    pwm?: boolean;
    adc?: boolean;
    i2c?: 'sda' | 'scl' | 'both';
    interrupt?: boolean;
    restricted?: boolean;
    notes?: string[];
  }>;
  defaults: {
    led?: string;
    i2c?: { sda: string; scl: string };
  };
  electrical: {
    logicV: number;
    toleranceV?: number;
  };
  reservedPins?: Record<string, string>;
};
```

---

## 6. Visual Design Requirements (Do Not Skip)

### 6.1 Visual Direction

1. Board module should be a dominant setup element (high information value).
2. Tall central board silhouette with true left/right rail semantics.
3. Neutral glass panel language matching current Midnight token family.
4. Status color reserved for meaning only (mapping/warning/error), not decoration.

### 6.2 Layout Rules

1. Compact view:
   - Board left, mapping badges right.
   - Minimum board height 340px.
2. Large view popout:
   - Board occupies majority of modal.
   - Rail labels and mapped roles readable without zoom.
3. Pin rows:
   - Uniform row height.
   - Visual distinction between unmapped and mapped slots.

### 6.3 Typography Rules

1. Pin labels: mono, compact uppercase.
2. Mapping labels: higher contrast, tighter tracking.
3. Model name in header: clear and explicit revision.

### 6.4 Motion Rules

1. No noisy animation.
2. Optional subtle highlight when a pin transitions from unmapped -> mapped.
3. Focus ring on keyboard navigation for accessibility.

### 6.5 Token Rules

1. Use theme tokens only (`--ui-panel-bg`, `--ui-input-bg`, `--line-*`, semantic status tokens).
2. No literal color leakage in component styles.
3. Shared board tokens for sizing/spacing to support future theme variants.

---

## 7. User Workflow

1. User selects board family/model (or accepts resolved suggestion).
2. System resolves profile and shows confidence.
3. User fills/agent fills logical roles.
4. Validator shows immediate pass/warn/fail results.
5. Large board view gives assembly reference.
6. Agent handoff payload is generated from resolved normalized profile.

---

## 8. Phased Delivery

### P0: Foundation

1. Registry + types + resolver.
2. Replace in-component board constants with registry lookup.
3. Keep existing visuals functional.

### P1: Validation + UX

1. Pin capability and reserved-pin validator.
2. Inline validator messages in Setup.
3. Confidence + ambiguity UI.

### P2: Visual Polish

1. Large popout board view with improved readability.
2. Better pin-to-role visual routing.
3. Accessibility and compact-screen pass.

### P3: Coverage Expansion

1. Add Nano family variants (classic, Every, 33 IoT, RP2040 Connect, ESP32).
2. Add ESP32 DevKit variants (v3/v4 and common module variants).
3. Add Teensy family baselines used by project.

---

## 9. Testing Strategy

### Unit

1. Resolver exact/alias/fuzzy matching.
2. Validator rules (PWM, reserved pins, I2C defaults).
3. Normalization of handoff payload.

### UI

1. Board switch updates rail layout.
2. Mapping visibility in compact + large modes.
3. Locked/unlocked behavior with sketch lifecycle.

### Regression Gate

```bash
cd app/ui/ops-console && npm run build
cd app/ui/ops-console && npm test -- --run
```

---

## 10. Risks and Mitigations

1. Risk: incorrect pinout data for a revision.
   - Mitigation: include source reference metadata per profile and review gate.
2. Risk: resolver picks wrong board silently.
   - Mitigation: confidence threshold + explicit ambiguity UI.
3. Risk: visual clutter with many labels.
   - Mitigation: compact defaults + popout deep view.

---

## 11. Acceptance Criteria

1. Setup uses registry-based rendering for board pin guide.
2. At least one Nano, one ESP32 DevKit, and one Teensy profile resolve and render correctly.
3. Validator blocks clearly unsafe pin assignments.
4. Agent handoff payload includes normalized board model and mapping assumptions.
5. Agent receives and uses persisted hardware context on every turn, with explicit update notice when parts selections change.
6. Visual style matches tokenized Midnight system and remains readable at 1366x768.

---

## 12. Next Immediate Task

Implement P0 now:

1. Extract current inline board profiles into `boardRegistry.ts`.
2. Add resolver utility and wire to Setup board selection.
3. Keep current diagram component, but feed it registry data only.

---

## Implementation Progress (2026-02-20)

Completed:

1. `hardware_context` now flows from Setup UI into backend chat endpoints and is persisted per session.
2. Agent receives stored hardware context each turn and emits deterministic notice when selections change.
3. Board resolver upgraded with confidence/ambiguity output and top candidates.
4. Pin validation module added with severity (`error`/`warn`/`info`) and setup wiring.
5. Agent handoff payload now includes resolver metadata + pin validation summary/issues.

Remaining high-priority PRD items:

1. Expand per-model pin capability precision (PWM/I2C/UART rules by revision).
2. Add source-reference metadata per board profile and review workflow.
3. Harden ambiguity UX with explicit “must confirm board” blocking gate before generation/upload.

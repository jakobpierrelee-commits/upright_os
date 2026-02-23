# Overhaul Sprint Scorecard (Readable)

Purpose: track this clean-lane overhaul like an execution program, with clear pass/fail checks and a running score.

How scoring works:
- Each check is worth `1` point when passed.
- Section score = `passed / total`.
- Sprint score = sum of all passed checks.
- Status:
  - `DONE` = passed and validated.
  - `IN PROGRESS` = partially implemented.
  - `TODO` = not validated yet.

---

## 0) Sprint Snapshot

- Sprint name: `Clean Lane Reliability + Execution Parity`
- Owner: `Codex + JVKE`
- Last updated: `2026-02-22`
- Current sprint score: `34 / 35` (97%)

---

## 1) Runtime Reliability (6 checks)

- [x] `DONE` Clean lane is default app entry (`main.tsx` clean-first behavior)
- [x] `DONE` Codex executor policy locked to avoid model/provider flapping
- [x] `DONE` Bridge foreground launch path standardized (`start_bridge_fg.sh`)
- [x] `DONE` Clean console launcher path works (`start_clean_console.sh`)
- [x] `DONE` Timeout handling returns structured errors (`timeout/quota/upstream`)
- [x] `DONE` Clean parity latency thresholds tuned for tool-turns (`MAX_MS_TOOLS`)

Section score: `6 / 6`

---

## 2) Agent Execution Parity (6 checks)

- [x] `DONE` Clean chat route is codex-cli backed
- [x] `DONE` Auto-tool tags trigger real tool execution (`connect/compat/compile`)
- [x] `DONE` Tool-call evidence is returned in responses
- [x] `DONE` Parity gate validates execution intent, not just text output
- [x] `DONE` New exec-intent gate script added (`check_clean_exec_intent.sh`)
- [x] `DONE` CI job wired (`.github/workflows/clean-lane.yml`) with static checks on push + opt-in live gates

Section score: `6 / 6`

---

## 3) Firmware Actionability (5 checks)

- [x] `DONE` Clean API endpoint for compile added (`/agent/clean/firmware/compile`)
- [x] `DONE` Clean API endpoint for guarded upload added (`/agent/clean/firmware/upload`)
- [x] `DONE` Compile button triggers backend action and reports final pass/fail
- [x] `DONE` Upload button triggers backend action and reports final pass/fail
- [x] `DONE` Firmware log visibility added (`Last Log` popout + refresh)

Section score: `5 / 5`

---

## 4) Operator UX for Execution (7 checks)

- [x] `DONE` Send supports `Enter` submit / `Shift+Enter` newline
- [x] `DONE` Streaming response path added (`/agent/clean/chat/stream`)
- [x] `DONE` Cancel button aborts in-flight chat request
- [x] `DONE` Explicit send progress shown (`Sending...`, elapsed seconds)
- [x] `DONE` Operations log persists recent actions/results in panel
- [x] `DONE` Compact error banner for fast diagnosis of last failure class
- [x] `DONE` Global bottom-dock status rail visible from all clean sections
Section score: `7 / 7`

---

## 5) Multi-Board Manifest Architecture (10 checks)

- [x] `DONE` Add backend hardware target registry endpoint (`/firmware/targets`) as source of truth for board families/targets/FQBN.
- [x] `DONE` Add backend bot profile registry with board + sensor + actuator schema (`/profiles/hardware`).
- [x] `DONE` Require agent-generated `runtime_manifest` on sketch generation/write (pins, buses, telemetry fields, command support).
- [x] `DONE` Add manifest validator (pin legality, pin conflicts, required commands, required telemetry fields).
- [x] `DONE` Add fail-closed preflight gate: block arm/commission when manifest is missing/invalid.
- [x] `DONE` Add runtime adapter map to normalize board-specific telemetry into common HUD fields (`ang/raw/gyro/out/mode/fault/estop`).
- [x] `DONE` Add protocol abstractions for IMU/encoder wiring (`I2C/SPI/UART`, quadrature/hall/SPI).
- [x] `DONE` Add target-aware upload/runbook guidance for AVR/ESP32/RP2040/Teensy.
- [x] `DONE` Add compatibility check between active bot profile and loaded runtime manifest.
- [x] `DONE` Add CI acceptance test: manifest mismatch must fail preflight and block arm.
- [ ] `IN PROGRESS` Add pre-arm hardware safety check gate for new firmware/session: wheel L/R pulse sanity + explicit E-STOP latch/unlatch verification before first ARM. Backend fail-closed gate + `/arm/precheck` endpoint implemented; awaiting hardware validation signoff.

Section score: `10 / 11`

---

## Validation Commands (Copy/Paste)

Run with bridge up:

```bash
./tools/lean/check_clean_lane.sh
./tools/lean/check_clean_parity.sh
./tools/lean/check_clean_exec_intent.sh
./tools/lean/preflight_clean.sh
```

Compile sanity (optional):

```bash
WITH_COMPILE=1 ./tools/lean/preflight_clean.sh
```

Update score line from checkboxes:

```bash
./tools/lean/update_scorecard.sh
```

Run gates then update score line:

```bash
./tools/lean/update_scorecard.sh --run-gates
```

## Morning Restore Checklist

1. Restart bridge: `./tools/restart_bridge.sh`
2. Start UI: `./tools/start_ops_console.sh`
3. Verify clean API contract: `curl -fsS "http://127.0.0.1:8797/status?mode=app_dev" | jq '.clean_api'`
4. Firmware lane smoke in UI: `Detect -> Compile -> Upload -> Preflight`
5. Confirm preflight stream progress updates (`start/check_start/check_done/done`) and final summary.

---

## Current Risks (Short)

1. Detached bridge process reliability can vary by environment; foreground mode is the known-stable path.
2. Compile/upload outcomes depend on local Arduino toolchain + board/port state.
3. Live clean-gate execution in hosted CI remains opt-in (environment-dependent).

---

## Remaining Steps Backlog (Full)

Status key:
- `P0` must-do now (execution reliability)
- `P1` next (operator parity)
- `P2` after stability (optimization / polish)

1. `[DONE]` Wire clean gates into CI (`lane`, `parity`, `exec_intent`, `preflight`).
2. `[DONE]` Add compact failure-class banner in clean panel (`timeout`, `quota`, `tool_failed`, `bridge_down`, `upload_failed`).
3. `[DONE]` Add compact last-result row for firmware actions (action, pass/fail, return code, timestamp).
4. `[DONE]` Validate guarded upload path end-to-end on real board and save one known-good run artifact.
5. `[P0]` Keep clean lane as default and hard-gate legacy execution paths behind explicit dev flag.
6. `[DONE]` Increase context parity in clean agent prompts (recent tool calls, firmware outcomes, telemetry summary, mission facts).
7. `[DONE]` Add minimal board/FQBN + port selectors in clean panel (default + override + persistence).
8. `[DONE]` Complete two full burn-in sessions with no manual backend intervention; require green gates at session end.
9. `[P2]` Define and normalize theme/style tokens for easy future UI edits (after reliability sprint closes).
10. `[P2]` Optional chunk-size optimization pass (code splitting) once functional scope is stable.
11. `[P1]` Add minimal in-app file tree for execution flow (select sketch, edit, diff, compile/upload from selected file).
12. `[P1]` Add file change guardrails in UI (dirty-state warning, compile from unsaved file blocked, explicit save/apply path).
13. `[P1]` Add "active execution context" header in Codex panel (active sketch, board, bootloader, port, profile).
14. `[P1]` Add structured tool-output panel for agent actions (command, exit code, duration, key log tail).
15. `[DONE]` Add command idempotency + lock semantics for compile/upload (prevent overlapping runs and stale retries).
16. `[DONE]` Add persistent run artifacts per operation (compile/upload logs + metadata + timestamps) with backend listing endpoint (`GET /firmware/artifacts`) and `last_artifact` on firmware status.
17. `[DONE]` Add "known-good recovery" one-click action (soft bridge recover + detect + precheck + status validation) via clean API + IDE Recovery button.
18. `[P1]` Add fast hardware fingerprint snapshot (board VID/PID, selected port, detected runtime identity) to each run artifact.
19. `[P1]` Add explicit profile/runtime compatibility status badge (pass/warn/fail) with blocking reason when fail.
20. `[P1]` Add CI smoke test for `/profiles/hardware` + `/firmware/targets` contract stability.
21. `[P0]` Add app-prompted pre-arm hardware check flow (minor wheel pulse tests + mandatory E-STOP verification) and block first ARM until pass.
22. `[P1]` Add tuning-suggestion quality gate: validate agent tuning recommendations against telemetry evidence quality (inputs completeness, confidence, and actionability) before tuning phase.
23. `[P1]` Add acceptance test pack for tuning recommendations (stable/oscillation/drift scenarios) to verify suggestion correctness and bounded safety deltas.
24. `[P1]` Promote canonical Phase evidence contract in backend (`phase1_*`, `phase2_*`) and deprecate direct `v2_*` UI evidence references after migration validation.
25. `[P1]` Add firmware progress UI during compile/upload (small status bar or popout with phase + elapsed time + latest log line) so operators see live forward motion.
26. `[DONE]` Isolate legacy API-era agent paths from clean Codex runtime: extracted `arm/prearm` + `firmware_ops` slices into modules with parity/contract tests and CI checks; `codex_chat/routes` remains the next isolation slice.
27. `[P1]` Add full cleanup matrix for high-risk files (not only Codex path): `server.py`, `codex_agent.py`, `codex_tools.py`, `serial_gateway.py`, `CleanApp.tsx`, and `styles.css/themes.css`; require owner, target module split, and pass/fail gates per file.
28. `[P1]` Refactor UI composition boundaries: split `CleanApp.tsx` into domain panels/hooks (`telemetry`, `command rail`, `firmware`, `codex`) with no behavior change and parity tests/smoke checks.
29. `[P1]` Refactor backend agent/tool boundaries: separate tool registry/execution (`codex_tools.py`) from orchestration/response logic (`codex_agent.py`) and enforce contract tests to prevent legacy coupling.
30. `[P1]` Add module size/complexity guardrails in CI (lint/script thresholds + exceptions list) to stop re-accumulation of monolithic files after cleanup.

## Next 3 Steps

1. `[DONE]` Capture one-click operator runbook actions for common recovery cases (bridge up/down, port re-detect, upload retry).
2. `[DONE]` Add fast-fail precheck before upload (bridge/port readiness) to reduce lock time on known bad states.
3. `[DONE]` Add explicit upload retry guidance panel keyed to common avrdude failure signatures.

## Next 5 (Manifest Track)

1. `[DONE]` Build backend `/firmware/targets` registry and move UI board family/target options to that API.
2. Define `runtime_manifest_v1.json` contract and add validator with fail-closed errors.
3. `[DONE]` Wire agent sketch generation to emit/update `runtime_manifest_v1.json` alongside sketch writes.
4. Add preflight checks for manifest validity + runtime-manifest compatibility.
5. Add one reference non-AVR end-to-end profile (Teensy 4.1) with telemetry + arming contract.

---

## Change Log

- `2026-02-22`: Initial scorecard created; baseline scoring populated from validated local runs.
- `2026-02-22`: Added global bottom-dock status rail and fixed section score totals for operator UX and CI wiring.
- `2026-02-22`: Added persistent FQBN/port overrides for clean compile/upload actions.
- `2026-02-22`: Added IDE board + bootloader selectors with manual FQBN override mode.
- `2026-02-22`: Completed two automated clean-lane burn-in sessions with compile sanity; artifacts:
  - `.runlogs/burnin_session1_20260222_012236.log`
  - `.runlogs/burnin_session2_20260222_012745.log`
- `2026-02-22`: Recorded known-good guarded upload artifact (real board): disarm -> close serial -> upload -> reconnect, `upload return code=0`, reconnect mode `SAFE_IDLE`, telemetry live.
- `2026-02-22`: Clean agent context parity upgraded (mission facts persistence, telemetry summary, recent firmware outcome, recent setup attempts, and clean tool call context) for both chat and streaming paths.
- `2026-02-22`: Added clean upload fast-fail precheck endpoint + IDE guard (`/agent/clean/firmware/upload/precheck`) to block known bad states immediately (`firmware_busy`, missing port, selected port not detected) and show actionable failure reason without long upload wait.
- `2026-02-22`: Added one-click recovery runbook controls in IDE firmware panel (`Check`, `Re-Detect Port`, `Retry Upload`, `Copy Restart Cmd`) plus signature-based upload retry guidance (avrdude sync/port busy/reconnect timeout patterns).
- `2026-02-22`: Added clean API contract gate (`clean_api.version=2` + capability checks) so Codex/IDE actions fail closed with explicit restart guidance when UI and bridge runtime are out of sync.
- `2026-02-22`: Added next-phase plan for profile-driven multi-board architecture (runtime manifest + validator + fail-closed preflight + sensor/encoder protocol abstractions, including Teensy support path).
- `2026-02-22`: Added backend hardware profile registry endpoint (`/profiles/hardware`) with board/family capabilities, sensor/actuator catalogs, profile schema requirements, and starter templates.
- `2026-02-22`: Added `runtime_manifest_v1` validator and clean-lane fail-closed gates (`/agent/clean/preflight`, `/agent/clean/firmware/upload/precheck`) with new manifest validation APIs (`/firmware/runtime-manifest`, `/firmware/runtime-manifest/validate`).
- `2026-02-22`: Added manifest auto-emit/update on sketch write and unified sketch generation; `runtime_manifest_v1.json` is now generated/maintained alongside sketch outputs.
- `2026-02-22`: Added runtime manifest/profile compatibility check and fail-closed clean preflight gate on profile/manifest mismatch (`/firmware/runtime-manifest/compat`).
- `2026-02-22`: Added live-gate CI acceptance check (`tools/lean/check_manifest_fail_closed.sh`) that proves clean preflight passes with valid manifest and fail-closes after intentional manifest mismatch.
- `2026-02-22`: Added canonical Phase evidence fields to readiness payloads (`phase1_missing_fields`, `phase1_present_fields`, `phase2_missing_fields`, `phase2_present_fields`) while preserving backward-compatible `v2_*` fields; legacy Stage 1 readiness panel now prefers Phase fields.
- `2026-02-22`: Implemented runtime telemetry adapter map (backend source of truth) with canonical HUD normalization for board-specific status aliases and new adapter visibility endpoints (`/status` includes `telemetry_adapter`; `/telemetry/adapter-map` exposes registry + active adapter).
- `2026-02-22`: Implemented protocol abstraction contract for runtime manifests and hardware registry: explicit IMU/encoder/actuator protocol schemas, family capability checks, protocol-specific pin requirement validation, and profile/manifest protocol compatibility diagnostics.
- `2026-02-22`: Added target-aware upload runbook guidance by board family (AVR/ESP32/RP2040/Teensy) in clean upload precheck responses, and wired IDE recovery guidance to use backend runbook payloads first.
- `2026-02-22`: Added fail-closed pre-arm hardware safety gate to action gates (`prearm_safety_check_required`) with a new execution endpoint (`POST /arm/precheck`) for wheel L/R pulse confirmation and E-STOP latch/unlatch verification (including optional auto E-STOP probe).
- `2026-02-22`: Added persistent firmware run artifacts (`.runlogs/firmware_ops/*.json|*.log`) and listing API (`GET /firmware/artifacts`); firmware status now includes `last_artifact`.
- `2026-02-22`: Added clean one-click known-good recovery endpoint (`POST /agent/clean/recovery/known-good`) and IDE firmware `Known-Good` action to run soft bridge recovery, detect ports, upload precheck, and status/gate validation in one report.
- `2026-02-23`: Added firmware operation lock semantics with idempotency support for clean compile/upload paths: in-flight duplicate requests with same idempotency key are reused, conflicting overlaps return `operation_in_progress` (HTTP 409), and `/firmware/status` now exposes active/last-completed operation metadata.
- `2026-02-23`: Added explicit P0 scorecard guardrail for legacy-path isolation so old API-era code cannot constrain clean Codex runtime quality; planned extraction order: `arm/prearm` -> `firmware_ops` -> `codex_chat/routes` with no-contract-change gates.
- `2026-02-23`: Expanded cleanup scope beyond Codex path: added cross-file refactor matrix and CI guardrails for backend, UI composition, and style/system files to keep the clean lane maintainable.
- `2026-02-23`: Added backward-compatible dual-MCU foundation to manifest/profile contracts: optional `mcu_topology` schema in hardware registry and runtime manifest validator support (`control_mcu` required when present, optional `io_mcu`/link/namespaces), enabling future control-MCU + RC-MCU rollout without immediate architecture changes.
- `2026-02-23`: Completed first legacy-isolation extraction slice: moved pre-arm safety gate + hardware precheck execution into `app/bridge/arm_safety.py` and kept `server.py` wrapper/API behavior intact; parity tests remain green.
- `2026-02-23`: Hardened pre-arm auto wheel probe reliability: enforce safe-state sequencing (`DISARM` + `ESTOP 1` before `MOTOR_TEST`), add escalating retry attempts for weak wheel pulses, and extend tests to cover retry success/failure behavior.
- `2026-02-23`: Completed firmware-ops legacy-isolation slice: extracted clean firmware compile/upload/precheck/recovery route logic into `app/bridge/clean_firmware_ops.py` and rewired `server.py` handlers with no endpoint contract change.
- `2026-02-23`: Added strict clean response contract validators in `app/bridge/clean_contracts.py` and enforced them for `/firmware/targets`, `/arm/precheck`, `/agent/clean/preflight`, and `/agent/clean/preflight/stream` done payloads.
- `2026-02-23`: Added new contract tests (`app/bridge/tests/test_clean_contracts.py`, `app/bridge/tests/test_clean_firmware_ops.py`) plus CI guard `tools/lean/check_clean_sse_contract.sh` wired into `tools/lean/ci_clean_lane.sh`.

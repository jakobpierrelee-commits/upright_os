# Cleanup Matrix (High-Risk Files)

Purpose: define owner, split target, and hard pass/fail gates for the high-risk files called out in scorecard item 27.

Last updated: `2026-02-23`

## Scope

| File | Current LOC | Owner | Split Target (No Behavior Change) | Pass Gates | Fail Gates |
|---|---:|---|---|---|---|
| `app/bridge/server.py` | 13,526 | Bridge Runtime (`Codex`) | Keep as Flask route/composition shell only; move logic to domain modules (`clean_*`, firmware domain, arm/prearm domain, profile/manifest domain). | `python3 -m py_compile app/bridge/server.py`; `cd app/bridge && pytest -q tests/test_clean_*.py tests/test_server_runtime_manifest.py tests/test_server_runtime_manifest_compat.py tests/test_firmware_*.py`; clean lane CI remains green. | Any endpoint contract change without scorecard/decision update; parity or firmware contract test regression; route behavior moved without wrapper parity tests. |
| `app/bridge/codex_agent.py` | 585 | Agent Runtime (`Codex`) | Keep orchestration/prompt/session only; move tool execution registry and side effects to `codex_tools.py` + thin adapters. | `cd app/bridge && pytest -q tests/test_codex_agent.py tests/test_codex_agent_history.py tests/test_codex_pr3.py tests/test_codex_pr4_rag.py tests/test_codex_rag.py`; no direct hardware side-effect calls outside tool API. | Agent path directly shells/runs hardware actions bypassing tool registry; thread/history contract breaks. |
| `app/bridge/codex_tools.py` | 3,351 | Agent Tooling (`Codex`) | Split by domain (`tooling_firmware.py`, `tooling_probe.py`, `tooling_files.py`, `tooling_tuning.py`) with shared typed result envelope. | `cd app/bridge && pytest -q tests/test_codex_tools.py tests/test_codex_t1_tools.py tests/test_codex_t2_tools.py tests/test_codex_t3_tools.py`; tool output schema stable. | Tool return payload shape drift without test updates; implicit globals introduced; duplicate tool names/handlers. |
| `app/bridge/serial_gateway.py` | 380 | Bridge Runtime (`Codex`) | Separate transport concerns from protocol parsing/retry policy; retain one public gateway facade. | Existing bridge tests pass; add and keep dedicated serial gateway tests (`app/bridge/tests/test_serial_gateway.py`) for open/close/reconnect/timeout semantics. | Reconnect or timeout behavior changes without tests; hidden threading side effects added. |
| `app/ui/ops-console/src/CleanApp.tsx` | 67 | Frontend Runtime (`Codex`) | Keep page composition shell only; feature state/effects moved into domain hook/panels (`telemetry`, `command rail`, `firmware`, `codex`) via `useCleanAppState.ts` + section components. | `cd app/ui/ops-console && npm run build`; `cd app/ui/ops-console && npm run test -- src/CleanApp.boundary.test.tsx`; manual smoke: load page + send chat + compile/upload/preflight path works. | Panel-level business logic added back into root app shell; build or smoke regressions in clean lane workflow. |
| `app/ui/ops-console/src/styles.css` + `app/ui/ops-console/src/styles/themes.css` | 8,557 + 3,375 | Frontend Design System (`Codex + JVKE`) | Keep global tokens/layout in `themes.css`; split component-scoped styling into feature styles; remove duplicated selectors and dead theme branches. | `cd app/ui/ops-console && npm run build`; no visual regression in clean-lane critical panels (telemetry, firmware IDE, codex panel); token source remains centralized. | New hard-coded palette drift outside token layer; duplicate conflicting selectors for same component state; critical panel visual regressions. |

## Execution Order

1. `server.py` route-shell enforcement (highest blast radius).
2. `codex_tools.py` domain split.
3. `codex_agent.py` orchestration-only enforcement.
4. `CleanApp.tsx` shell-only split.
5. `styles.css/themes.css` token + component boundary cleanup.
6. `serial_gateway.py` transport/protocol split with dedicated tests.

## Guardrail Rules

1. No behavior change in cleanup slices unless explicitly tracked as a separate scorecard item.
2. Every slice must land with automated gates and at least one manual smoke artifact note in scorecard changelog.
3. If a slice fails gates, rollback that slice only and keep other lanes moving.
4. CI module-size/complexity guardrail must remain green:
   - `tools/lean/check_module_size_guardrails.sh`
   - Config + exceptions source of truth: `tools/lean/module_size_guardrails.json`

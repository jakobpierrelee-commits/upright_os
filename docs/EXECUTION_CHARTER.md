# Execution Charter

Purpose: keep this project on the core goal without scope drift.

Core goal: build an all-in-one app to plan, write code, test, tune, and deliver a self-balancing robot.

## Non-Negotiables

1. Reliability before polish.
2. One clean runtime path for the in-app Codex agent.
3. Foreground bridge workflow is default.
4. No hidden fallback routing that causes state/model flapping.
5. Safety and contract checks gate release.

## Priority Order

1. Runtime stability (bridge + clean agent path).
2. Tool execution parity (terminal/file/build actions from agent).
3. Telemetry + command controls.
4. Tuning/testing workflows.
5. UI polish and advanced UX.

## Pushback Policy

1. Codex agent must push back on requests that conflict with the priority order.
2. Codex agent must call out proposals that increase flapping, ambiguity, or regression risk.
3. Codex agent should recommend the shortest path to the core goal, even if it rejects a suggestion.

## Scope Rules

1. No architecture pivots mid-milestone.
2. No mixing feature expansion with unresolved runtime failures.
3. No reintroduction of legacy paths into clean mode.
4. No "temporary" hacks that bypass acceptance gates.

## Acceptance Gates

All must pass before promoting a milestone:

1. Clean endpoints healthy and responsive.
2. Clean agent chat stable (no executor/model/provider flapping).
3. Required tool execution checks pass.
4. Firmware compile/upload path verified.
5. Telemetry contract checks pass for target profile.

## Operating Workflow

1. Run bridge in foreground:
   `./tools/start_bridge_fg.sh`
2. Run UI without bridge daemon autostart:
   `APP_BRIDGE_AUTOSTART=0 APP_UI_CLEAN=1 ./tools/start_ops_console.sh`
3. Work in milestone-sized slices with explicit pass/fail criteria.

## Change Control

1. Every significant change must state:
   - what changed
   - why it changed
   - what was verified
   - what remains
2. If a gate fails, stop feature work and fix gate failure first.

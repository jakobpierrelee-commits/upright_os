# Engineering Governance

## Purpose
This document defines the mandatory workflow for evolving UpRight firmware scaffolds, bridge contracts, UI behavior, and agent tooling without regressions.

## Core Principles
1. Scaffold is source-of-truth.
2. Contracts are versioned and explicit.
3. Changes are additive first, then gated.
4. Every merge is test-gated.
5. No silent telemetry fields.

## Change Workflow
1. Update scaffold/templates first.
2. Update contract docs next.
3. Update bridge probe/readiness logic.
4. Update UI types and rendering.
5. Update agent/tool assumptions.
6. Run full verification gates before merge.

## Contract Policy
1. `v1` required fields remain backward-compatible.
2. `v2_ready` is additive readiness, not a hard break for legacy bots.
3. `v2_factory_ready` is the strict gate for factory-certified builds.
4. New fields must be documented in `docs/contracts`.

## Factory Certification Gate
A build is factory-certified only if all are true:
1. `v1_ok` is true.
2. `v2_factory_ready` is true.
3. Calibration workflow checks pass.
4. Verification script passes.

## No Silent Fields Rule
If a telemetry field is emitted:
1. It must be consumed by bridge/UI/agent, or
2. It must have an explicit TODO with test coverage asserting temporary non-use.

## Required Verification
Run `tools/verify_all.sh` before merge to validate:
1. Bridge test suite.
2. Agent tools sprint suites (T1/T2/T3).
3. Contract v2 readiness tests.
4. Frontend typecheck.
5. Frontend codex tests.

## Release Discipline
1. No breaking contract removals in minor versions.
2. Every contract change includes a migration note.
3. Every safety-related change includes rollback behavior.


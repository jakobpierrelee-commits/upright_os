# Assistant Knowledge Governance v1.0

Purpose:
- Keep learned tuning knowledge durable in markdown.
- Allow updates when new evidence supersedes prior guidance.
- Prevent stale assumptions from driving unsafe or low-quality recommendations.

Scope:
- Applies to files in `docs/assistant_knowledge/`.
- Applies to tuning advice, telemetry interpretation, control limits, and workflow gates.

Supersession policy:
1. Never delete prior versions for audit.
2. Add a new versioned file (`*_vX.Y.md`) when guidance changes materially.
3. Mark old guidance as superseded in `manifest.json` changelog.
4. Promote `active_version` only after:
   - evidence links are captured,
   - safety constraints are unchanged or improved,
   - at least one validation run confirms no obvious regression.

Evidence requirements for updates:
- Each meaningful change must include:
  - what changed,
  - why it changed,
  - supporting artifact paths (run logs, summaries, or code references),
  - rollback note if behavior regresses.

Conflict resolution:
- If operator-observed behavior conflicts with telemetry summary:
  - treat operator observation as primary,
  - classify run as `invalid_window` until telemetry coherence is restored,
  - do not score tuning lift from conflicting runs.

Knowledge quality gate:
- Do not claim certainty when event-contract validity is failing.
- No tuning recommendation can bypass prearm/fail-closed safety gates.
- One-variable tuning deltas only until closed-loop evidence is stable.

Update cadence:
- Update knowledge pack after:
  - a new validated failure mode,
  - a new proven recovery strategy,
  - hardware/profile changes that alter limits or telemetry behavior.

Ownership:
- Implementation owner: `Codex`
- Validation owner: `JVKE`

# Config Schema

## Config Layers
1. Safety defaults (global, non-overridable).
2. Robot profile (style/behavior preset).
3. Session tuning (temporary).

## Profile Requirement
Each profile must declare nudge behavior policy:
- `return_to_origin`
- `hold_new_position`
- `hybrid_threshold`

Default profile for current platform: `return_to_origin`.

## Versioning
- Include explicit config version.
- Reject incompatible versions with migration path.

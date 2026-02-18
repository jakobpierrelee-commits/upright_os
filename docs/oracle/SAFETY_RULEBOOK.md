# Safety Rulebook

## Hard Rules
1. On app disconnect during BALANCING: immediate `DISARM`.
2. Boot behavior: never auto-arm by default; explicit user action required.
3. Any fault state must force motor output to zero and require explicit recovery path.
4. Command handlers must reject malformed payloads and out-of-range values.
5. Dangerous config changes must be bounded while BALANCING.

## Runtime Policy
- `AUTORUN`: disabled by default (future optional feature with explicit user opt-in).
- Safety rules are non-overridable by profile.

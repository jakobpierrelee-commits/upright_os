# MC Outbox — Mission Broker Outbound Queue

**Managed by:** Mission Broker (Claude Teams)
**Purpose:** MC-RESPONSEs from Mission Command (Codex), ready to be relayed to requesting agents.

Status values: `PENDING_RELAY` | `RELAYED`

---

## Queue

<!-- Mission Command: append responses below. Mission Broker relays to requesting thread. -->

| Decision ID | Entry ID | Timestamp (UTC) | Outcome | Status |
|---|---|---|---|---|

---

## Response Template

```
## MC-RESPONSE

- Decision ID:        # Format: MC-YYYY-MMDD-NNN
- Entry ID:           # Matches the MC-QUESTION Entry ID
- Outcome:            # approve | reject | clarify | escalate
- Scope ruling:       # in-bounds | out-of-bounds
- Required actions:
  1. ...
- Verification required:
  - <exact command(s)>
- Handoff/logging condition:
  - update docs/SESSION_HANDOFF.md
  - update docs/MULTI_AGENT_SIGNOFF_LEDGER.md
```

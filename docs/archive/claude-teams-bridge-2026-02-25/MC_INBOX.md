# MC Inbox — Mission Broker Inbound Queue

**Managed by:** Mission Broker (Claude Teams)
**Purpose:** Inbound MC-QUESTIONs from all agents. Mission Broker validates and routes.

Status values: `PENDING` | `ROUTED` | `INVALID`

---

## Queue

<!-- Agents: append entries below. Do not edit existing rows. -->

| Entry ID | Timestamp (UTC) | Agent | Block | Status | Notes |
|---|---|---|---|---|---|
| Q-20260225-002 | 2026-02-25T22:51:00Z | Codex | M1-A | PENDING | Mission Command request: broker append first real inbound entry with full schema + real UTC timestamp |

---

## Submission Template

```
## MC-QUESTION

- Entry ID:           # Format: Q-YYYY-MMDD-NNN
- Agent:
- Signature:
- Timestamp (UTC):
- Block:              # M1-A | M1-B | M1-C
- Branch:
- SHA:
- Scope:
- Ownership Check:

### Question
...

### Context
- Files touched:
- Evidence:
- Risk if wrong:

### Decision Needed
- Type:               # approve | reject | clarify | escalate
- Deadline:
```

---

## Validation Rules (enforced by Mission Broker)

All fields required. Missing any field → marked `INVALID`, resubmission requested.
Escalation triggers (immediate route to Mission Command):
- `/tooling/tuning/*` behavior
- Safety invariants
- Migration/schema policy
- Regression tolerance changes
- Ownership/branch policy conflicts

---

## MC-QUESTION

- Entry ID: Q-20260225-002
- Agent: Codex
- Signature: codex
- Timestamp (UTC): 2026-02-25T22:51:00Z
- Block: M1-A
- Branch: feature/tuning-intelligence-phase-0
- SHA: 32dcc71
- Scope: Broker transport validation and canonical queue normalization.
- Ownership Check: Mission Command governance request; no product-code behavior changes.

### Question
Please append the first real inbound agent question in this canonical root inbox using full required schema and a real UTC timestamp, then reply with: `Q-20260225-002 appended`.

### Context
- Files touched:
  - docs/MC_INBOX.md
  - docs/MC_OUTBOX.md
  - docs/MC_DECISIONS.jsonl
- Evidence:
  - Broker healthcheck reported `ALIVE` and root-path visibility for all MC queue files.
- Risk if wrong:
  - Queue transport ambiguity remains and agent decisions may split across root/worktree paths.

### Decision Needed
- Type: clarify
- Deadline: 2026-02-25T23:10:00Z

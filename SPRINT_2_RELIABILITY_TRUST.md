# Sprint 2: Reliability + Operator Trust

**Duration:** 1 week  
**Goal:** Production hardening for Codex tool integration  
**Constraint:** Backward compatible with `/ai/chat`, no safety relaxations

---

## Sprint Scope

| Priority | Area | Effort |
|----------|------|--------|
| **P0** | Tool transparency UI | 1.5d |
| **P0** | Upload confirmation UX flow | 1d |
| **P1** | Failure-mode handling | 1d |
| **P1** | Observability (logs + metrics) | 0.5d |
| **P2** | Chat persistence/recovery | 0.5d |
| **P2** | Regression test suite | 0.5d |
| Buffer | Code review, fixes | 1d |

---

## P0: Critical Path (Must Ship)

### P0.1: Tool Execution Transparency UI

**Deliverable:** Display tool calls inline in chat with args summary, status indicator, and expandable details.

**Files:**
- `app/ui/ops-console/src/features/codex/CodexPanel.tsx`
- `app/ui/ops-console/src/features/codex/ToolCallCard.tsx` (new)
- `app/ui/ops-console/src/App.css` (tool call styles)

**Implementation:**

```tsx
// ToolCallCard.tsx - new component
type ToolCallCardProps = {
  tool: string;
  args: Record<string, unknown>;
  result: { ok: boolean; data: Record<string, unknown>; error?: string; execution_time_ms: number };
  expanded?: boolean;
  onToggle?: () => void;
};

// Render:
// - Tool name badge (color-coded by category: read=blue, write=amber, flash=red)
// - Args summary (truncated single line)
// - Status pill: ok=green, error=red
// - Execution time
// - Expandable JSON detail view
```

**Acceptance Criteria:**
- [ ] Tool calls appear inline between user message and assistant reply
- [ ] Each tool call shows: name, truncated args (≤60 chars), ok/error pill, time (ms)
- [ ] Click to expand shows full args + result JSON
- [ ] Color coding: read tools (blue), write tools (amber), upload (red)
- [ ] Failed tools show error message prominently

**Test Cases:**
```
TC-P0.1-1: Send message triggering query_telemetry → see blue tool card with result
TC-P0.1-2: Send message triggering execute_command → see amber tool card
TC-P0.1-3: Trigger tool error → see red error state with message
TC-P0.1-4: Multiple tool calls in sequence → all cards visible in order
TC-P0.1-5: Expand/collapse tool details → JSON renders correctly
```

---

### P0.2: Upload Confirmation UX Flow

**Deliverable:** Modal flow for firmware upload token approval with expiry countdown and retry.

**Files:**
- `app/ui/ops-console/src/features/codex/UploadConfirmModal.tsx` (new)
- `app/ui/ops-console/src/hooks/useCodexWorkspace.ts`
- `app/bridge/codex_tools.py` (token refresh endpoint)
- `app/bridge/server.py` (add `/ai/upload/confirm` endpoint)

**Implementation:**

```python
# server.py - new endpoint
POST /ai/upload/confirm
Request: { "token": str, "action": "approve" | "reject" }
Response: { "ok": bool, "upload_result"?: {...}, "error"?: str }
```

```tsx
// UploadConfirmModal.tsx
// - Shows pending upload details: sketch path, board, port
// - 5-minute countdown timer (token expiry)
// - "Approve Upload" (red, prominent) / "Cancel" buttons
// - On expiry: auto-dismiss with "Token expired" toast
// - On approve: show upload progress, then result
```

**Acceptance Criteria:**
- [ ] When upload_firmware returns `requires_confirmation`, modal appears
- [ ] Modal shows: sketch name, board FQBN, port, expiry countdown
- [ ] Approve triggers actual upload with progress indicator
- [ ] Cancel dismisses modal, logs rejection
- [ ] Expired token shows error, offers "Request New Token" action
- [ ] Upload success/failure shows toast notification

**Test Cases:**
```
TC-P0.2-1: Request upload → modal appears with correct details
TC-P0.2-2: Approve before expiry → upload executes, success toast
TC-P0.2-3: Cancel upload → modal closes, no upload executed
TC-P0.2-4: Wait 5+ minutes → token expires, modal shows expired state
TC-P0.2-5: Retry after expiry → new token requested, fresh modal
TC-P0.2-6: Upload fails (compile error) → error displayed in modal
```

---

## P1: Reliability (Should Ship)

### P1.1: Failure-Mode Handling

**Deliverable:** Graceful degradation for OpenAI timeout, tool crash, serial busy, stale session.

**Files:**
- `app/bridge/codex_agent.py`
- `app/bridge/codex_tools.py`
- `app/ui/ops-console/src/hooks/useCodexWorkspace.ts`

**Implementation:**

```python
# codex_agent.py - enhanced error handling
class ToolExecutionError(Exception):
    def __init__(self, tool: str, error: str, recoverable: bool = True):
        self.tool = tool
        self.error = error
        self.recoverable = recoverable

# Failure modes to handle:
# 1. OpenAI timeout (>45s): Return partial response + "AI service slow, retrying..."
# 2. Tool crash: Catch exception, return tool error result, continue loop
# 3. Serial busy: Return "Serial port busy, try again in a moment"
# 4. Stale session (401): Trigger re-auth flow in UI
```

```python
# codex_tools.py - serial busy detection
def _check_serial_available(gateway) -> Tuple[bool, str]:
    health = gateway.health()
    if health.get("write_locked"):
        return False, "Serial port busy with another operation"
    if not health.get("connected"):
        return False, "Serial port not connected"
    return True, ""
```

**Acceptance Criteria:**
- [ ] OpenAI timeout returns user-friendly message, not stack trace
- [ ] Tool crash doesn't break chat; error shown in tool card
- [ ] Serial busy prevents command, shows actionable message
- [ ] 401/403 triggers re-auth modal, preserves draft message
- [ ] Network disconnect shows offline banner, queues retry

**Test Cases:**
```
TC-P1.1-1: Mock OpenAI 504 → "AI service temporarily unavailable" message
TC-P1.1-2: Tool raises exception → tool card shows error, chat continues
TC-P1.1-3: Serial write_locked=true → "Serial busy" error, no command sent
TC-P1.1-4: Session expired mid-chat → re-auth modal, message preserved
TC-P1.1-5: Network offline → offline indicator, retry on reconnect
```

---

### P1.2: Observability

**Deliverable:** Structured JSON logs for tool calls + minimal metrics endpoint.

**Files:**
- `app/bridge/codex_agent.py`
- `app/bridge/server.py` (metrics endpoint)
- `app/bridge/codex_db.py` (tool audit table)

**Implementation:**

```python
# codex_db.py - add tool_audit table
CREATE TABLE IF NOT EXISTS tool_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    session_key TEXT,
    tool TEXT NOT NULL,
    args_json TEXT,
    ok INTEGER NOT NULL,
    error TEXT,
    execution_time_ms REAL,
    INDEX idx_tool_audit_ts (ts)
);

# Structured log format (stdout JSON lines)
{
    "event": "tool_executed",
    "ts": 1708300000.123,
    "tool": "execute_command",
    "args": {"command": "PID 15.0 0.5 0.3"},
    "ok": true,
    "execution_time_ms": 42.5,
    "session_key": "user:1"
}
```

```python
# server.py - metrics endpoint
GET /ai/metrics
Response: {
    "tool_calls_total": 142,
    "tool_calls_by_name": {"execute_command": 45, "query_telemetry": 67, ...},
    "tool_errors_total": 3,
    "avg_execution_time_ms": 38.2,
    "upload_confirmations": {"approved": 2, "rejected": 1, "expired": 0},
    "since": "2026-02-18T00:00:00Z"
}
```

**Acceptance Criteria:**
- [ ] Every tool call logged to stdout as JSON line
- [ ] Tool audit table persists last 10,000 calls (FIFO)
- [ ] `/ai/metrics` returns aggregated stats
- [ ] Logs include session_key for user attribution
- [ ] Error logs include stack trace in `detail` field

**Test Cases:**
```
TC-P1.2-1: Execute tool → JSON log line appears in stdout
TC-P1.2-2: Tool error → log includes error + detail fields
TC-P1.2-3: GET /ai/metrics → returns valid stats JSON
TC-P1.2-4: 10,001st tool call → oldest audit row pruned
TC-P1.2-5: Logs parseable by jq (valid JSON lines)
```

---

## P2: Polish (Nice to Have)

### P2.1: Chat Persistence/Recovery

**Deliverable:** Verify chat history survives refresh, reconnect, and multi-tab scenarios.

**Files:**
- `app/ui/ops-console/src/hooks/useCodexWorkspace.ts`
- `app/bridge/server.py`

**Implementation:**

```tsx
// useCodexWorkspace.ts - recovery flow
// On mount:
// 1. Check localStorage for draft message
// 2. Call /ai/status to restore history
// 3. Restore active thread_id from localStorage
// 4. If tool_calls in last message, re-render tool cards

// On beforeunload:
// 1. Save draft message to localStorage
// 2. Save active thread_id
```

**Acceptance Criteria:**
- [ ] Refresh page → chat history restored
- [ ] Close/reopen tab → history + thread restored
- [ ] Draft message in input preserved across refresh
- [ ] Tool call results in history re-render correctly
- [ ] Multi-tab: each tab can have different thread

**Test Cases:**
```
TC-P2.1-1: Send message, refresh → history intact
TC-P2.1-2: Type draft, refresh → draft preserved
TC-P2.1-3: Switch thread, refresh → same thread active
TC-P2.1-4: Tool call in history → tool cards render on reload
TC-P2.1-5: Two tabs, different threads → independent state
```

---

### P2.2: Regression Test Suite

**Deliverable:** Automated test script covering tuning workflows.

**Files:**
- `app/bridge/tests/test_regression_tuning.py` (new)

**Test Coverage:**

```python
# test_regression_tuning.py
class TuningRegressionTests:
    def test_burst_capture_flow(self):
        """Queue burst → capture → verify CSV saved"""
        
    def test_apply_pid_via_chat(self):
        """Chat 'set PID to 15 0.5 0.3' → verify command sent"""
        
    def test_sync_from_bot(self):
        """Sync config → verify status updated"""
        
    def test_checkpoint_save_load(self):
        """Save checkpoint → reload → verify values"""
        
    def test_compile_without_upload(self):
        """Compile sketch → verify no upload triggered"""
        
    def test_blocked_command_rejected(self):
        """Try ARM via tool → verify rejection"""
        
    def test_blocked_var_rejected(self):
        """Try edit PIN_* → verify rejection"""
```

**Acceptance Criteria:**
- [ ] All 7 regression tests pass
- [ ] Tests run in <30s without hardware
- [ ] Tests use mocks for serial/OpenAI
- [ ] CI-compatible (exit code 0/1)

---

## Safety Policy Audit Checklist

### Blocked Commands (verify in `codex_tools.py`)
- [ ] `ARM` → rejected with "requires UI confirmation"
- [ ] `DISARM` → rejected
- [ ] `STATE` → rejected
- [ ] `MOTOR` → rejected
- [ ] `MOTOROFF` → rejected
- [ ] `ESTOP` → rejected (use UI button)
- [ ] `RESET` → rejected

### Blocked Sketch Variables
- [ ] `PIN_*` → rejected with "hardware pin assignment blocked"
- [ ] `MODE_*` → rejected
- [ ] `CONFIG_MAGIC` → rejected
- [ ] `CONFIG_VERSION` → rejected

### Server-Side Guards
- [ ] Tool execution only via authenticated session
- [ ] Upload token validated server-side before flash
- [ ] Allowlist checked before command dispatch
- [ ] Rate limit: max 10 tool calls per minute per user

---

## Risk Register

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| OpenAI API outage | High | Low | Graceful fallback to non-tool chat |
| Tool card rendering perf | Medium | Medium | Virtualize list if >20 cards |
| Upload token race condition | High | Low | Server-side token lock |
| Serial contention | Medium | Medium | Queue with timeout, clear error |
| localStorage quota | Low | Low | Prune old threads >30 days |

---

## Definition of Done

- [ ] All P0 items implemented and tested
- [ ] All P1 items implemented and tested
- [ ] No regressions in existing `/ai/chat` flow
- [ ] Safety audit checklist passes (all boxes checked)
- [ ] Tool transparency visible in production UI
- [ ] Upload confirmation flow works end-to-end
- [ ] Structured logs emitting for all tool calls
- [ ] Code reviewed and merged
- [ ] No console errors/warnings in UI

---

## PR Sequence (Small, Shippable)

### PR 1: Tool Transparency UI (P0.1)
```
Files:
  + app/ui/ops-console/src/features/codex/ToolCallCard.tsx
  ~ app/ui/ops-console/src/features/codex/CodexPanel.tsx
  ~ app/ui/ops-console/src/App.css
Tests: Visual review + TC-P0.1-*
```

### PR 2: Upload Confirmation Modal (P0.2)
```
Files:
  + app/ui/ops-console/src/features/codex/UploadConfirmModal.tsx
  ~ app/ui/ops-console/src/hooks/useCodexWorkspace.ts
  ~ app/bridge/server.py (POST /ai/upload/confirm)
  ~ app/bridge/codex_tools.py (token refresh)
Tests: TC-P0.2-*
```

### PR 3: Failure Handling (P1.1)
```
Files:
  ~ app/bridge/codex_agent.py (error classes, timeout handling)
  ~ app/bridge/codex_tools.py (serial busy check)
  ~ app/ui/ops-console/src/hooks/useCodexWorkspace.ts (error states)
Tests: TC-P1.1-*
```

### PR 4: Observability (P1.2)
```
Files:
  ~ app/bridge/codex_db.py (tool_audit table)
  ~ app/bridge/codex_agent.py (structured logging)
  ~ app/bridge/server.py (GET /ai/metrics)
Tests: TC-P1.2-*
```

### PR 5: Persistence + Regression (P2)
```
Files:
  ~ app/ui/ops-console/src/hooks/useCodexWorkspace.ts (recovery)
  + app/bridge/tests/test_regression_tuning.py
Tests: TC-P2.1-*, regression suite
```

---

## Code-Level Recommendations

### `codex_agent.py`

```python
# Add at top
import logging
logger = logging.getLogger("codex.agent")

# Add structured logging helper
def _log_tool_call(tool: str, args: dict, result: dict, session_key: str):
    logger.info(json.dumps({
        "event": "tool_executed",
        "ts": time.time(),
        "tool": tool,
        "args": args,
        "ok": result.get("ok", False),
        "error": result.get("error"),
        "execution_time_ms": result.get("execution_time_ms", 0),
        "session_key": session_key,
    }))

# Add timeout wrapper for OpenAI calls
async def _call_openai_with_timeout(client, payload, timeout_s=45):
    try:
        return await asyncio.wait_for(
            client.chat.completions.create(**payload),
            timeout=timeout_s
        )
    except asyncio.TimeoutError:
        raise OpenAITimeoutError("AI service took too long to respond")
```

### `codex_tools.py`

```python
# Add serial availability check before write commands
def execute_command(self, command: str) -> ToolResult:
    available, reason = self._check_serial_available()
    if not available:
        return ToolResult(ok=False, tool="execute_command", data={}, error=reason)
    # ... existing logic

def _check_serial_available(self) -> Tuple[bool, str]:
    if self.gateway is None:
        return False, "Serial gateway not initialized"
    health = self.gateway.health()
    if health.get("write_locked"):
        return False, "Serial port busy with another operation"
    if not health.get("connected"):
        return False, "Robot not connected"
    return True, ""
```

### `useCodexWorkspace.ts`

```typescript
// Add draft persistence
useEffect(() => {
  const saved = localStorage.getItem('codex_draft');
  if (saved) dispatch({ type: 'set_ai_input', payload: saved });
}, []);

useEffect(() => {
  if (state.aiInput) {
    localStorage.setItem('codex_draft', state.aiInput);
  } else {
    localStorage.removeItem('codex_draft');
  }
}, [state.aiInput]);

// Add error state handling
type ErrorState = 
  | { type: 'none' }
  | { type: 'network'; retryAt?: number }
  | { type: 'auth'; message: string }
  | { type: 'tool'; tool: string; message: string };
```

### `server.py`

```python
# Add /ai/upload/confirm endpoint after /ai/chat/tools
if u.path == "/ai/upload/confirm":
    tok = _extract_auth_token(self, body)
    me = auth.me(tok)
    if not me:
        return _json(self, 401, {"ok": False, "error": "unauthenticated"})
    confirm_token = str(body.get("token", "")).strip()
    action = str(body.get("action", "")).strip()
    if action not in ("approve", "reject"):
        return _json(self, 400, {"ok": False, "error": "invalid action"})
    if action == "reject":
        # Log rejection, clear token
        return _json(self, 200, {"ok": True, "action": "rejected"})
    # Validate and execute upload
    result = codex_agent.confirm_upload(confirm_token)
    return _json(self, 200, result)

# Add /ai/metrics endpoint
if u.path == "/ai/metrics" and self.command == "GET":
    tok = _extract_auth_token(self, {})
    me = auth.me(tok)
    if not me:
        return _json(self, 401, {"ok": False, "error": "unauthenticated"})
    stats = codex_agent.get_metrics() if codex_agent else {}
    return _json(self, 200, {"ok": True, **stats})
```

---

## Timeline

| Day | Focus | Deliverable |
|-----|-------|-------------|
| 1 | PR 1: ToolCallCard | Tool transparency UI merged |
| 2 | PR 2: UploadConfirmModal | Upload flow working |
| 3 | PR 3: Error handling | Failure modes graceful |
| 4 | PR 4: Observability | Logs + metrics live |
| 5 | PR 5: Persistence + tests | Full regression passing |
| 6-7 | Buffer | Fixes, polish, review |

---

*Generated: 2026-02-18*

# Scope Cut Checklist

Based on Product Vision v1: "A Windsurf-like workspace for building self-balancing robots with AI partnership."

---

## Agent Mode Consolidation

### CUT these modes:
| Mode | Location | Action |
|------|----------|--------|
| `app_dev` | `agent_helpers.py:180-187` | Remove branch |
| `ops_debug` | `agent_helpers.py:188-193` | Remove branch |
| `firmware_review` | If exists | Remove |

### KEEP and make default:
| Mode | Purpose |
|------|---------|
| `robot_dev` | The ONE mode - robot bring-up, firmware, tuning, controls |

**Result:** `_agent_mode_system_prompt()` returns one prompt, no mode switching.

---

## Routes to CUT

Based on grep of 124 routes, candidates for removal:

| Route Pattern | Reason | Action |
|---------------|--------|--------|
| `/ai/metrics` | App debugging | Cut or stub |
| `/ai/rag/stats` | App debugging | Cut or stub |
| `/auth/*` (complex) | Multi-user | Simplify to single-user |
| `/config/snapshots` | Over-engineered | Evaluate |

### Routes to KEEP (Core to vision):
| Route Pattern | Purpose |
|---------------|---------|
| `/status`, `/health` | Robot state |
| `/lines`, `/burst/*` | Telemetry |
| `/firmware/*` | Compile, flash, boards |
| `/probe/*` | Connect, compat |
| `/tooling/tuning/*` | Tuning capabilities |
| `/agent/*` | Chat, threads |
| `/design-memory` | Build decisions |
| `/profiles` | Robot identity |
| `/overwatch/*` | System health |

---

## Files to Simplify

| File | Current Lines | Issue | Target |
|------|---------------|-------|--------|
| `codex_tools.py` | 3,060 | Too many tools | Prune to robot-focused |
| `codex_rag.py` | 571 | Complex RAG | Simplify or merge |
| `auth_manager.py` | ~400 | Multi-user auth | Stub or remove |
| `provider_router.py` | ~300 | Multi-provider | Simplify to OpenAI only |

---

## Domain Modules Status

| Domain | Status | Notes |
|--------|--------|-------|
| `control_runtime/` | KEEP | Core |
| `firmware_lifecycle/` | KEEP | Core |
| `hardware_profile/` | KEEP | Core |
| `tuning_intelligence/` | KEEP | Core |
| `safety_prearm/` | KEEP | Core |
| `session_traceability/` | KEEP | Design memory valuable |
| `ai_agent/` | SIMPLIFY | Remove mode complexity |

---

## Immediate Actions (Priority Order)

1. **Consolidate agent modes** in `agent_helpers.py`
   - Remove `app_dev`, `ops_debug` branches
   - Make `robot_dev` the implicit default
   - ~30 lines changed

2. **Prune `_agent_choose_executor()`** 
   - Remove `app_dev` special casing
   - ~20 lines changed

3. **Update tests** that reference removed modes
   - `test_clean_codex_chat.py` (12 refs)
   - `test_clean_threads.py` (6 refs)

4. **Defer deeper cuts** until agent mode consolidation proves stable

---

## Verification

After each cut:
```bash
python3 -m py_compile app/bridge/server.py
python3 -m pytest app/bridge/tests/ -x -q
python3 tools/lean/check_import_boundaries.py
```

---

*Checklist created: 2026-02-26*

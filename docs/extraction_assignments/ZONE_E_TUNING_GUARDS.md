# Zone E Assignment: Tuning Guards Extraction

**Branch:** `recover/uiux-restore-2026-02-19`
**Target Module:** `app/bridge/tuning_guards.py`
**Estimated Time:** 20 minutes
**Merge Order:** Can merge in any order (no dependencies)

---

## Your Mission

Extract tuning guard utilities from `server.py` to a new standalone module `tuning_guards.py`.

---

## Critical Rules (Read First)

1. **DO NOT touch `build_handler()` body** (lines ~5150–8700)
2. **DO NOT modify existing import block** except to add your import at line ~670
3. **Copy functions VERBATIM** — no refactoring, no style changes
4. **Preserve all docstrings and comments** exactly as-is

---

## Pre-Extraction Verification

Run these commands to confirm line numbers haven't drifted:

```bash
cd /path/to/UpRight.os-lean
grep -n "^def _status_float" app/bridge/server.py  # Expected: ~3386
grep -n "^def _enforce_preflight_if_needed" app/bridge/server.py  # Expected: ~3718
```

If line numbers differ by >50, stop and report to Mission Command.

---

## Items to Extract

| Item | Approx Lines | Notes |
|------|--------------|-------|
| `_status_float` | 3386–3395 | Float extraction helper |
| `_require_tuning_range` | 3396–3400 | Range validation |
| `_guard_pid_apply` | 3401–3418 | PID guard |
| `_guard_motion_apply` | 3419–3431 | Motion guard |
| `_guard_setpoint_apply` | 3432–3439 | Setpoint guard |
| `_guard_limits_apply` | 3440–3455 | Limits guard |
| `_detect_tuning_capabilities` | 3456–3492 | Capability detection |
| `_validate_tuning_recommendation_contract` | 3493–3524 | Contract validation |
| `_evaluate_tuning_recommendation_quality` | 3525–3668 | Quality evaluation |
| `_build_tuning_apply_signature` | 3669–3678 | Signature building |
| `TUNING_PREFLIGHT_DELTA` | ~3679 | Constant dict (delta thresholds) |
| `_requires_preflight` | 3679–3715 | Preflight requirement check |
| `_enforce_preflight_if_needed` | 3718–3736 | Preflight enforcement |

**Total:** ~350 lines

---

## Step 1: Create tuning_guards.py

Create `app/bridge/tuning_guards.py` with this structure:

```python
"""Tuning guard utilities extracted from server.py."""

from typing import Any, Dict, Optional

__all__ = [
    "_status_float",
    "_require_tuning_range",
    "_guard_pid_apply",
    "_guard_motion_apply",
    "_guard_setpoint_apply",
    "_guard_limits_apply",
    "_detect_tuning_capabilities",
    "_validate_tuning_recommendation_contract",
    "_evaluate_tuning_recommendation_quality",
    "_build_tuning_apply_signature",
    "TUNING_PREFLIGHT_DELTA",
    "_requires_preflight",
    "_enforce_preflight_if_needed",
]


# Paste all functions in order, with TUNING_PREFLIGHT_DELTA constant
# (copy verbatim from server.py lines ~3386-3736)
```

**Note:** Some functions receive `preflight_store: TuningPreflightStore` as parameter — no import needed, just preserve the type hint if present in original.

---

## Step 2: Add Import to server.py

Add this block at **line ~670** (end of existing imports, before first `def`):

```python
try:
    from app.bridge.tuning_guards import (
        _status_float,
        _require_tuning_range,
        _guard_pid_apply,
        _guard_motion_apply,
        _guard_setpoint_apply,
        _guard_limits_apply,
        _detect_tuning_capabilities,
        _validate_tuning_recommendation_contract,
        _evaluate_tuning_recommendation_quality,
        _build_tuning_apply_signature,
        TUNING_PREFLIGHT_DELTA,
        _requires_preflight,
        _enforce_preflight_if_needed,
    )
except ImportError:
    from tuning_guards import (  # type: ignore
        _status_float,
        _require_tuning_range,
        _guard_pid_apply,
        _guard_motion_apply,
        _guard_setpoint_apply,
        _guard_limits_apply,
        _detect_tuning_capabilities,
        _validate_tuning_recommendation_contract,
        _evaluate_tuning_recommendation_quality,
        _build_tuning_apply_signature,
        TUNING_PREFLIGHT_DELTA,
        _requires_preflight,
        _enforce_preflight_if_needed,
    )
```

---

## Step 3: Verification

Run these checks before committing:

```bash
# Module import check
python3 -c "from app.bridge.tuning_guards import _guard_pid_apply; print('OK')"

# Server still loads
python3 -c "from app.bridge import server; print('OK')"

# Run any existing tests
cd app/bridge && python3 -m pytest tests/ -x -q -k tuning 2>/dev/null || echo "No tuning tests found"
cd app/bridge && python3 -m pytest tests/ -x -q -k guard 2>/dev/null || echo "No guard tests found"
cd app/bridge && python3 -m pytest tests/ -x -q -k preflight 2>/dev/null || echo "No preflight tests found"
```

---

## Verification Checklist

- [ ] `tuning_guards.py` created at `app/bridge/`
- [ ] All 12 functions + 1 constant copied verbatim
- [ ] `__all__` export list defined
- [ ] Import block added to server.py (~line 670)
- [ ] `python3 -c "from app.bridge.tuning_guards import *; print('OK')"` passes
- [ ] `python3 -c "from app.bridge import server; print('OK')"` passes
- [ ] No changes made to `build_handler()` body
- [ ] Original functions in server.py are UNTOUCHED (deletion is Phase 2)

---

## Commit Format

```
refactor: extract Zone E tuning guards to tuning_guards.py
```

---

## Questions/Blockers?

Use Mission Command template:

```
## MC Question — [Your Agent Name]
**Zone:** E
**Issue:** [brief description]
**Options:** [A] ... [B] ...
**Recommendation:** [your pick]
```

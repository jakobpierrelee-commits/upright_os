# Zone B Assignment: Contract Readiness Extraction

**Branch:** `recover/uiux-restore-2026-02-19`
**Target Module:** `app/bridge/contract_readiness.py`
**Estimated Time:** 25 minutes
**Merge Order:** Must merge BEFORE Zone C (Zone C depends on this)

---

## Your Mission

Extract contract readiness and compat policy utilities from `server.py` to a new standalone module `contract_readiness.py`.

---

## Critical Rules (Read First)

1. **DO NOT touch `build_handler()` body** (lines ~5150–8700)
2. **DO NOT modify existing import block** except to add your import at line ~670
3. **Copy functions VERBATIM** — no refactoring, no style changes
4. **Preserve all docstrings and comments** exactly as-is
5. **EXCLUDE `_run_prearm_hardware_check`** — it stays in server.py

---

## Pre-Extraction Verification

Run these commands to confirm line numbers haven't drifted:

```bash
cd /path/to/UpRight.os-lean
grep -n "^V1_REQUIRED_FIELDS" app/bridge/server.py  # Expected: ~3744
grep -n "^def _require_action_allowed" app/bridge/server.py  # Expected: ~4277
```

If line numbers differ by >50, stop and report to Mission Command.

---

## Functions to Extract

| Item | Approx Lines | Notes |
|------|--------------|-------|
| `V1_REQUIRED_FIELDS` | ~3744 | Constant |
| `V1_GYRO_ALIASES` | ~3746 | Constant |
| `V2_READINESS_FIELDS` | ~3750 | Constant |
| `V2_FACTORY_FIELDS` | ~3756 | Constant |
| `V2_OPTIONAL_FIELDS` | ~3762 | Constant |
| `detect_contract_readiness` | 3767–3940 | Core readiness detection |
| `_compute_action_gates` | 3941–4056 | Computes action permission gates |
| `_default_compat_policy` | 4057–4181 | Returns default policy dict |
| `_load_compat_policy` | 4182–4209 | Loads from file with fallback |
| `_status_has_required_fields` | 4210–4224 | Validates status dict |
| `_resolve_compat_profile` | 4225–4251 | Resolves profile from policy |
| `_resolve_action_gates` | 4252–4276 | Resolves gates for profile |
| `_require_action_allowed` | 4277–4297 | Raises if action blocked |

**Zone B scope ends at line ~4297** — do NOT include `_run_prearm_hardware_check`

**Total:** ~550 lines

---

## Internal Dependency Graph

```
_require_action_allowed
  └── _resolve_action_gates
        └── _resolve_compat_profile
              └── _load_compat_policy
                    └── _default_compat_policy
  └── _status_has_required_fields

detect_contract_readiness (standalone, uses constants)
_compute_action_gates (uses detect_contract_readiness)
```

---

## Step 1: Create contract_readiness.py

Create `app/bridge/contract_readiness.py` with this structure:

```python
"""Contract readiness and compat policy utilities extracted from server.py."""

import json
import logging
import pathlib
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "V1_REQUIRED_FIELDS",
    "V1_GYRO_ALIASES",
    "V2_READINESS_FIELDS",
    "V2_FACTORY_FIELDS",
    "V2_OPTIONAL_FIELDS",
    "detect_contract_readiness",
    "_compute_action_gates",
    "_default_compat_policy",
    "_load_compat_policy",
    "_status_has_required_fields",
    "_resolve_compat_profile",
    "_resolve_action_gates",
    "_require_action_allowed",
]


# Paste constants first, then all functions in dependency order
# (copy verbatim from server.py lines ~3744-4297)
```

---

## Step 2: Add Import to server.py

Add this block at **line ~670** (end of existing imports, before first `def`):

```python
try:
    from app.bridge.contract_readiness import (
        V1_REQUIRED_FIELDS,
        V1_GYRO_ALIASES,
        V2_READINESS_FIELDS,
        V2_FACTORY_FIELDS,
        V2_OPTIONAL_FIELDS,
        detect_contract_readiness,
        _compute_action_gates,
        _default_compat_policy,
        _load_compat_policy,
        _status_has_required_fields,
        _resolve_compat_profile,
        _resolve_action_gates,
        _require_action_allowed,
    )
except ImportError:
    from contract_readiness import (  # type: ignore
        V1_REQUIRED_FIELDS,
        V1_GYRO_ALIASES,
        V2_READINESS_FIELDS,
        V2_FACTORY_FIELDS,
        V2_OPTIONAL_FIELDS,
        detect_contract_readiness,
        _compute_action_gates,
        _default_compat_policy,
        _load_compat_policy,
        _status_has_required_fields,
        _resolve_compat_profile,
        _resolve_action_gates,
        _require_action_allowed,
    )
```

---

## Step 3: Verification

Run these checks before committing:

```bash
# Module import check
python3 -c "from app.bridge.contract_readiness import detect_contract_readiness; print('OK')"

# Server still loads
python3 -c "from app.bridge import server; print('OK')"

# Run any existing tests
cd app/bridge && python3 -m pytest tests/ -x -q -k contract 2>/dev/null || echo "No contract tests found"
cd app/bridge && python3 -m pytest tests/ -x -q -k readiness 2>/dev/null || echo "No readiness tests found"
```

---

## Verification Checklist

- [ ] `contract_readiness.py` created at `app/bridge/`
- [ ] All 5 constants + 8 functions copied verbatim
- [ ] `__all__` export list defined
- [ ] Import block added to server.py (~line 670)
- [ ] `python3 -c "from app.bridge.contract_readiness import *; print('OK')"` passes
- [ ] `python3 -c "from app.bridge import server; print('OK')"` passes
- [ ] `_run_prearm_hardware_check` was NOT extracted (stays in server.py)
- [ ] No changes made to `build_handler()` body
- [ ] Original functions in server.py are UNTOUCHED (deletion is Phase 2)

---

## Commit Format

```
refactor: extract Zone B contract readiness to contract_readiness.py
```

---

## Questions/Blockers?

Use Mission Command template:

```
## MC Question — [Your Agent Name]
**Zone:** B
**Issue:** [brief description]
**Options:** [A] ... [B] ...
**Recommendation:** [your pick]
```

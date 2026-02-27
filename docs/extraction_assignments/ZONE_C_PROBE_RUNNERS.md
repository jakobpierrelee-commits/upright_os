# Zone C Assignment: Probe Runners Extraction

**Branch:** `recover/uiux-restore-2026-02-19`
**Target Module:** `app/bridge/probe_runners.py`
**Estimated Time:** 35 minutes
**Merge Order:** Must merge AFTER Zone B (imports `detect_contract_readiness`)

---

## Your Mission

Extract probe runner and overwatch utilities from `server.py` to a new standalone module `probe_runners.py`.

---

## Critical Rules (Read First)

1. **DO NOT touch `build_handler()` body** (lines ~5150–8700)
2. **DO NOT modify existing import block** except to add your import at line ~670
3. **Copy functions VERBATIM** — no refactoring, no style changes
4. **Preserve all docstrings and comments** exactly as-is
5. **WAIT for Zone B to merge before merging this zone**

---

## Pre-Extraction Verification

Run these commands to confirm line numbers haven't drifted:

```bash
cd /path/to/UpRight.os-lean
grep -n "^def run_compat_probe" app/bridge/server.py  # Expected: ~4306
grep -n "^def build_overwatch_report" app/bridge/server.py  # Expected: ~4852
```

If line numbers differ by >50, stop and report to Mission Command.

---

## Functions to Extract

| Function | Approx Lines | Notes |
|----------|--------------|-------|
| `run_compat_probe` | 4306–4446 | Main compat probe |
| `_get_port_meta` | 4447–4479 | USB port metadata |
| `_guess_mcu` | 4482–4498 | MCU fingerprinting |
| `run_connect_probe` | 4501–4658 | Connection probe |
| `run_setup_compat_test` | 4659–4721 | Setup compatibility test |
| `run_setup_smoke_check` | 4722–4788 | Smoke check |
| `run_setup_overwatch_check` | 4789–4803 | Overwatch check |
| `_latest_docs_folder` | 4804–4813 | Finds latest docs |
| `_validate_docs_artifacts` | 4814–4851 | Validates docs |
| `build_overwatch_report` | 4852–5145 | Builds full report |

**Total:** ~840 lines

---

## Internal Dependency Graph

```
build_overwatch_report
  └── run_setup_overwatch_check
  └── _latest_docs_folder
  └── _validate_docs_artifacts
  └── detect_contract_readiness (from Zone B - contract_readiness.py)

run_connect_probe
  └── run_compat_probe
  └── _get_port_meta
  └── _guess_mcu
```

---

## Step 1: Create probe_runners.py

Create `app/bridge/probe_runners.py` with this structure:

```python
"""Probe runner and overwatch utilities extracted from server.py."""

import pathlib
import time
from typing import Any, Dict, List, Optional

# Optional imports with fallback
try:
    from serial.tools import list_ports
except Exception:
    list_ports = None

# Cross-zone dependency (Zone B must be merged first)
try:
    from app.bridge.contract_readiness import detect_contract_readiness
except ImportError:
    from contract_readiness import detect_contract_readiness  # type: ignore

__all__ = [
    "run_compat_probe",
    "_get_port_meta",
    "_guess_mcu",
    "run_connect_probe",
    "run_setup_compat_test",
    "run_setup_smoke_check",
    "run_setup_overwatch_check",
    "_latest_docs_folder",
    "_validate_docs_artifacts",
    "build_overwatch_report",
]


# Paste all functions in dependency order
# (copy verbatim from server.py lines ~4306-5145)
```

**Note:** Functions receive `gateway: NanoSerialGateway` as parameter — no import needed, just use in type hints if present in original.

---

## Step 2: Add Import to server.py

Add this block at **line ~670** (end of existing imports, before first `def`):

```python
try:
    from app.bridge.probe_runners import (
        run_compat_probe,
        _get_port_meta,
        _guess_mcu,
        run_connect_probe,
        run_setup_compat_test,
        run_setup_smoke_check,
        run_setup_overwatch_check,
        _latest_docs_folder,
        _validate_docs_artifacts,
        build_overwatch_report,
    )
except ImportError:
    from probe_runners import (  # type: ignore
        run_compat_probe,
        _get_port_meta,
        _guess_mcu,
        run_connect_probe,
        run_setup_compat_test,
        run_setup_smoke_check,
        run_setup_overwatch_check,
        _latest_docs_folder,
        _validate_docs_artifacts,
        build_overwatch_report,
    )
```

---

## Step 3: Verification

Run these checks before committing:

```bash
# Zone B dependency check (must pass first)
python3 -c "from app.bridge.contract_readiness import detect_contract_readiness; print('Zone B OK')"

# Module import check
python3 -c "from app.bridge.probe_runners import build_overwatch_report; print('OK')"

# Server still loads
python3 -c "from app.bridge import server; print('OK')"

# Run any existing tests
cd app/bridge && python3 -m pytest tests/ -x -q -k probe 2>/dev/null || echo "No probe tests found"
cd app/bridge && python3 -m pytest tests/ -x -q -k overwatch 2>/dev/null || echo "No overwatch tests found"
```

---

## Verification Checklist

- [ ] Zone B (`contract_readiness.py`) is already merged
- [ ] `probe_runners.py` created at `app/bridge/`
- [ ] All 10 functions copied verbatim with docstrings
- [ ] `__all__` export list defined
- [ ] Import for `detect_contract_readiness` from Zone B included
- [ ] Import block added to server.py (~line 670)
- [ ] `python3 -c "from app.bridge.probe_runners import *; print('OK')"` passes
- [ ] `python3 -c "from app.bridge import server; print('OK')"` passes
- [ ] No changes made to `build_handler()` body
- [ ] Original functions in server.py are UNTOUCHED (deletion is Phase 2)

---

## Commit Format

```
refactor: extract Zone C probe runners to probe_runners.py
```

---

## Questions/Blockers?

Use Mission Command template:

```
## MC Question — [Your Agent Name]
**Zone:** C
**Issue:** [brief description]
**Options:** [A] ... [B] ...
**Recommendation:** [your pick]
```

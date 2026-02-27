# Zone A Assignment: Manifest Validation Extraction

**Branch:** `recover/uiux-restore-2026-02-19`
**Target Module:** `app/bridge/manifest_validation.py`
**Estimated Time:** 30 minutes
**Merge Order:** Can merge in any order (no dependencies)

---

## Your Mission

Extract manifest validation utilities from `server.py` to a new standalone module `manifest_validation.py`.

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
grep -n "^def _pin_range_for_family" app/bridge/server.py  # Expected: ~2174
grep -n "^def _runtime_manifest_profile_compatibility" app/bridge/server.py  # Expected: ~2627
```

If line numbers differ by >50, stop and report to Mission Command.

---

## Functions to Extract

| Function | Approx Lines | Notes |
|----------|--------------|-------|
| `_pin_range_for_family` | 2174–2182 | Pure function |
| `_family_capabilities` | 2185–2231 | Returns static dict |
| `_protocol_schema` | 2234–2258 | Returns static dict |
| `_has_valid_pin` | 2261–2267 | Pure function |
| `_validate_protocol_pins` | 2270–2310 | Uses `_has_valid_pin` |
| `_validate_runtime_manifest_v1` | 2312–2590 | Large, uses above helpers |
| `_manifest_required_field_present` | 2591–2599 | Pure function |
| `_family_for_fqbn` | 2601–2612 | Pure function |
| `_board_id_for_fqbn` | 2614–2625 | Pure function |
| `_runtime_manifest_profile_compatibility` | 2627–2963 | Large, uses above helpers |

**Total:** ~790 lines

---

## Internal Dependency Graph

```
_runtime_manifest_profile_compatibility
  └── _validate_runtime_manifest_v1
        ├── _validate_protocol_pins
        │     └── _has_valid_pin
        ├── _family_capabilities
        ├── _protocol_schema
        └── _pin_range_for_family
  └── _family_for_fqbn
  └── _board_id_for_fqbn
  └── _manifest_required_field_present
```

All functions must stay together in this module.

---

## Step 1: Create manifest_validation.py

Create `app/bridge/manifest_validation.py` with this structure:

```python
"""Manifest validation utilities extracted from server.py."""

from typing import Any, Dict, Optional

__all__ = [
    "_pin_range_for_family",
    "_family_capabilities",
    "_protocol_schema",
    "_has_valid_pin",
    "_validate_protocol_pins",
    "_validate_runtime_manifest_v1",
    "_manifest_required_field_present",
    "_family_for_fqbn",
    "_board_id_for_fqbn",
    "_runtime_manifest_profile_compatibility",
]


# Paste all functions below in dependency order
# (copy verbatim from server.py lines ~2174-2963)
```

---

## Step 2: Add Import to server.py

Add this block at **line ~670** (end of existing imports, before first `def`):

```python
try:
    from app.bridge.manifest_validation import (
        _pin_range_for_family,
        _family_capabilities,
        _protocol_schema,
        _has_valid_pin,
        _validate_protocol_pins,
        _validate_runtime_manifest_v1,
        _manifest_required_field_present,
        _family_for_fqbn,
        _board_id_for_fqbn,
        _runtime_manifest_profile_compatibility,
    )
except ImportError:
    from manifest_validation import (  # type: ignore
        _pin_range_for_family,
        _family_capabilities,
        _protocol_schema,
        _has_valid_pin,
        _validate_protocol_pins,
        _validate_runtime_manifest_v1,
        _manifest_required_field_present,
        _family_for_fqbn,
        _board_id_for_fqbn,
        _runtime_manifest_profile_compatibility,
    )
```

---

## Step 3: Verification

Run these checks before committing:

```bash
# Module import check
python3 -c "from app.bridge.manifest_validation import *; print('OK')"

# Server still loads
python3 -c "from app.bridge import server; print('OK')"

# Run any existing tests
cd app/bridge && python3 -m pytest tests/ -x -q -k manifest 2>/dev/null || echo "No manifest tests found"
```

---

## Verification Checklist

- [ ] `manifest_validation.py` created at `app/bridge/`
- [ ] All 10 functions copied verbatim with docstrings
- [ ] `__all__` export list defined
- [ ] Import block added to server.py (~line 670)
- [ ] `python3 -c "from app.bridge.manifest_validation import *; print('OK')"` passes
- [ ] `python3 -c "from app.bridge import server; print('OK')"` passes
- [ ] No changes made to `build_handler()` body
- [ ] Original functions in server.py are UNTOUCHED (deletion is Phase 2)

---

## Commit Format

```
refactor: extract Zone A manifest validation to manifest_validation.py
```

---

## Questions/Blockers?

Use Mission Command template:

```
## MC Question — [Your Agent Name]
**Zone:** A
**Issue:** [brief description]
**Options:** [A] ... [B] ...
**Recommendation:** [your pick]
```

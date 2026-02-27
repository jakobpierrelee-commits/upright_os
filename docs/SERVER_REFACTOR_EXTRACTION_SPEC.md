# Server.py Multi-Agent Extraction Specification

**Created:** 2026-02-26
**Branch:** `recover/uiux-restore-2026-02-19`
**Purpose:** Enable parallel extraction of server.py utility functions by multiple agents without merge conflicts.

---

## Executive Summary

`server.py` is currently ~8,850 lines. The `build_handler()` function alone is 3,484 lines (lines 5146–8630).

This spec defines **5 extraction zones** containing ~2,870 lines of utility functions that:
- Live **outside** `build_handler()`
- Have **minimal cross-dependencies**
- Can be extracted to standalone modules **in parallel**

Phase 1 extracts utilities. Phase 2 (sequential, single agent) wires them into `build_handler()`.

---

## Conflict Avoidance Protocol

### Rules for All Agents

1. **DO NOT touch `build_handler()` body** (lines 5146–8630) during Phase 1.
2. **DO NOT touch the import block** (lines 1–673) except to add your zone's import statement.
3. **Add imports at the END of the existing import block** (~line 670) to minimize merge conflicts.
4. **Copy functions verbatim** — no refactoring during extraction.
5. **Preserve all docstrings and comments** exactly.
6. **Use `try/except ImportError` pattern** for all new imports (matches existing style).

### Import Block Template

Each agent adds their import block at **line ~670** (after existing imports, before first `def`):

```python
try:
    from app.bridge.<your_module> import (
        func_a,
        func_b,
    )
except ImportError:
    from <your_module> import (  # type: ignore
        func_a,
        func_b,
    )
```

### Pre-Extraction Line Verification

Before starting extraction, verify function boundaries haven't drifted:

```bash
# Zone A
grep -n "^def _pin_range_for_family" app/bridge/server.py  # Expected: ~2174
grep -n "^def _runtime_manifest_profile_compatibility" app/bridge/server.py  # Expected: ~2627

# Zone B
grep -n "^V1_REQUIRED_FIELDS" app/bridge/server.py  # Expected: ~3744
grep -n "^def _run_prearm_hardware_check" app/bridge/server.py  # Expected: ~4298

# Zone C
grep -n "^def run_compat_probe" app/bridge/server.py  # Expected: ~4306
grep -n "^def build_overwatch_report" app/bridge/server.py  # Expected: ~4852

# Zone D
grep -n "^_codexrules_cache" app/bridge/server.py  # Expected: ~1258
grep -n "^def _normalize_reply_for_prompt" app/bridge/server.py  # Expected: ~1716

# Zone E
grep -n "^def _status_float" app/bridge/server.py  # Expected: ~3386
grep -n "^def _enforce_preflight_if_needed" app/bridge/server.py  # Expected: ~3718
```

If line numbers differ by >50 lines, re-verify function boundaries before proceeding.

### Verification Before Commit

```bash
# Syntax check
python3 -c "from app.bridge import server; print('OK')"

# Import check for your module
python3 -c "from app.bridge.<your_module> import <func>; print('OK')"

# Full test suite (if available)
cd app/bridge && python3 -m pytest tests/ -x -q
```

---

## Zone A: Manifest Validation

**Target module:** `manifest_validation.py`
**Lines:** 2174–2963 (~790 lines)
**Assignable to:** Any agent
**Dependencies:** Standard library only (no managers, no gateway)

### Functions to Extract

| Function | Lines | Notes |
|----------|-------|-------|
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

### Internal Dependencies (must stay together)

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

### Required Imports in New Module

```python
from typing import Any, Dict, Optional
```

### Export List

```python
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
```

### server.py Import Block to Add

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

## Zone B: Contract Readiness & Compat Policy

**Target module:** `contract_readiness.py`
**Lines:** 3739–4305 (~570 lines)
**Assignable to:** Any agent
**Dependencies:** Standard library only

### Functions to Extract

| Function | Lines | Notes |
|----------|-------|-------|
| Constants: `V1_REQUIRED_FIELDS`, `V1_GYRO_ALIASES`, `V2_READINESS_FIELDS`, `V2_FACTORY_FIELDS`, `V2_OPTIONAL_FIELDS` | 3744–3764 | Module-level constants |
| `detect_contract_readiness` | 3767–3940 | Core readiness detection |
| `_compute_action_gates` | 3941–4056 | Computes action permission gates |
| `_default_compat_policy` | 4057–4181 | Returns default policy dict |
| `_load_compat_policy` | 4182–4209 | Loads from file with fallback |
| `_status_has_required_fields` | 4210–4224 | Validates status dict |
| `_resolve_compat_profile` | 4225–4251 | Resolves profile from policy |
| `_resolve_action_gates` | 4252–4276 | Resolves gates for profile |
| `_require_action_allowed` | 4277–4297 | Raises if action blocked |
| `_run_prearm_hardware_check` | 4298–4305 | Thin wrapper (may need import) |

### Internal Dependencies

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

### Required Imports in New Module

```python
import json
import logging
import pathlib
from typing import Any, Dict, List, Optional
```

### Decision: `_run_prearm_hardware_check`

**EXCLUDE from Zone B.** This function calls `_run_prearm_hardware_check_impl` from `arm_safety.py` and belongs with arm/safety routing, not contract readiness.

- **Action:** Leave `_run_prearm_hardware_check` in `server.py` for now
- **Future:** Move to `routes_arm.py` during Phase 2 or later refactor
- **Zone B scope:** Lines 3739–4297 (ends before `_run_prearm_hardware_check`)

---

## Zone C: Probe Runners & Overwatch

**Target module:** `probe_runners.py`
**Lines:** 4306–5145 (~840 lines)
**Assignable to:** Any agent
**Dependencies:** `NanoSerialGateway` (passed as argument), `list_ports` (optional import)

### Functions to Extract

| Function | Lines | Notes |
|----------|-------|-------|
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

### Internal Dependencies

```
build_overwatch_report
  └── run_setup_overwatch_check
  └── _latest_docs_folder
  └── _validate_docs_artifacts
  └── detect_contract_readiness (from Zone B)

run_connect_probe
  └── run_compat_probe
  └── _get_port_meta
  └── _guess_mcu
```

### Required Imports in New Module

```python
import pathlib
import time
from typing import Any, Dict, List, Optional

# Optional imports with fallback
try:
    from serial.tools import list_ports
except Exception:
    list_ports = None

# Cross-zone dependency (add after Zone B is merged)
from app.bridge.contract_readiness import detect_contract_readiness
```

### Note: Gateway Dependency

Functions receive `gateway: NanoSerialGateway` as a parameter — no import needed in module, just type hint.

---

## Zone D: Agent Helpers

**Target module:** `agent_helpers.py`
**Lines:** 1260–1750 (~490 lines)
**Assignable to:** Any agent
**Dependencies:** Standard library, `pathlib`

### Functions to Extract

| Function | Lines | Notes |
|----------|-------|-------|
| Global: `_codexrules_cache` | ~1258 | Module-level cache dict |
| `_load_codexrules` | 1260–1282 | Loads .codexrules file |
| `_resolve_system_prompt` | 1285–1366 | Builds system prompt |
| `_agent_mode_system_prompt` | 1369–1401 | Mode-specific prompt |
| `_agent_model_allowed` | 1404–1412 | Model allowlist |
| `_agent_mode_default_model` | 1413–1419 | Default model per mode |
| `_agent_resolve_model` | 1420–1430 | Resolves final model |
| `_agent_choose_executor` | 1431–1492 | Chooses executor |
| `_install_runtime_diagnostics` | 1493–1538 | Installs diagnostics |
| `_codex_cli_login_status` | 1539–1542 | CLI login check |
| `_legacy_execution_guard` | 1543–1548 | Legacy guard |
| `_extract_mission_facts` | 1549–1652 | Extracts facts from history |
| `_first_sentence` | 1653–1662 | Text helper |
| `_truncate_words` | 1663–1669 | Text helper |
| `_is_high_risk_user_request` | 1670–1688 | Risk detection |
| `_strip_repetitive_caution_lines` | 1689–1704 | Reply cleanup |
| `_soften_forced_reply_exact` | 1705–1715 | Reply softening |
| `_normalize_reply_for_prompt` | 1716–1750 | Reply normalization |

### Required Imports in New Module

```python
import logging
import pathlib
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)
```

---

## Zone E: Tuning Guards

**Target module:** `tuning_guards.py`
**Lines:** 3386–3736 (~350 lines)
**Assignable to:** Any agent
**Dependencies:** Standard library, `TuningPreflightStore` (passed as argument)

### Functions to Extract

| Function | Lines | Notes |
|----------|-------|-------|
| `_status_float` | 3386–3395 | Float extraction |
| `_require_tuning_range` | 3396–3400 | Range validation |
| `_guard_pid_apply` | 3401–3418 | PID guard |
| `_guard_motion_apply` | 3419–3431 | Motion guard |
| `_guard_setpoint_apply` | 3432–3439 | Setpoint guard |
| `_guard_limits_apply` | 3440–3455 | Limits guard |
| `_detect_tuning_capabilities` | 3456–3492 | Capability detection |
| `_validate_tuning_recommendation_contract` | 3493–3524 | Contract validation |
| `_evaluate_tuning_recommendation_quality` | 3525–3668 | Quality evaluation |
| `_build_tuning_apply_signature` | 3669–3678 | Signature building |
| Constant: `TUNING_PREFLIGHT_DELTA` | ~3679 | Delta thresholds |
| `_requires_preflight` | 3679–3715 | Preflight requirement check |
| `_enforce_preflight_if_needed` | 3718–3736 | Preflight enforcement |

### Required Imports in New Module

```python
from typing import Any, Dict, Optional
```

---

## Execution Order

### Phase 1: Parallel Extraction (No Conflicts)

| Agent | Zone | Target Module | Est. Time |
|-------|------|---------------|-----------|
| A | Zone A | `manifest_validation.py` | 30 min |
| B | Zone B | `contract_readiness.py` | 25 min |
| C | Zone C | `probe_runners.py` | 35 min |
| D | Zone D | `agent_helpers.py` | 25 min |
| E | Zone E | `tuning_guards.py` | 20 min |

**Merge order constraints:**
- **Zone B must merge before Zone C** (Zone C imports `detect_contract_readiness` from Zone B)
- Zones A, D, E can merge in any order
- Recommended sequence: A → B → D → E → C

### Phase 2: Sequential Wiring (Single Agent)

After all Phase 1 PRs are merged:

1. Delete extracted function bodies from `server.py` (keep imports)
2. Verify all call sites in `build_handler()` still work
3. Run full test suite

---

## Verification Checklist

Before marking zone complete:

- [ ] New module file created at `app/bridge/<module>.py`
- [ ] All functions copied verbatim with docstrings
- [ ] Module has correct imports at top
- [ ] `__all__` export list defined
- [ ] Import block added to server.py (~line 670)
- [ ] `python3 -c "from app.bridge.<module> import *; print('OK')"` passes
- [ ] `python3 -c "from app.bridge import server; print('OK')"` passes
- [ ] No changes made to `build_handler()` body
- [ ] Identified existing tests that call extracted functions
- [ ] Those tests pass with new import path (run targeted tests)
- [ ] Commit message follows format: `refactor: extract <zone> to <module>.py`

---

## Post-Extraction: Deleting from server.py

After ALL zones are extracted and verified, a **single agent** should:

1. Delete function bodies from server.py (lines 1260–3736, 3767–5145)
2. Keep only the import statements
3. Run full verification
4. Commit: `refactor: remove extracted utility functions from server.py`

Expected reduction: **~2,870 lines** removed from server.py.

---

## Rollback & Recovery Procedure

If Phase 2 wiring fails (tests break after deletions):

### Immediate Recovery

1. **Do NOT force-push or delete branches** — preserve extracted modules
2. Revert the deletion commit: `git revert HEAD`
3. Server.py now has both: original functions + import statements (redundant but working)

### Structured Recovery

1. Create `_legacy_backup/` directory before Phase 2 deletions
2. Copy original function bodies to `_legacy_backup/server_utilities.py`
3. Proceed with deletions
4. If tests fail: restore from `_legacy_backup/`, debug import wiring
5. Delete `_legacy_backup/` only after full test suite passes

### Recovery Commands

```bash
# Before Phase 2 deletions
mkdir -p app/bridge/_legacy_backup
cp app/bridge/server.py app/bridge/_legacy_backup/server_pre_phase2.py

# If Phase 2 fails
cp app/bridge/_legacy_backup/server_pre_phase2.py app/bridge/server.py
git checkout -- app/bridge/*.py  # Reset extracted modules if needed
```

### Success Criteria for Phase 2 Completion

- [ ] All extracted functions deleted from server.py
- [ ] `python3 -c "from app.bridge import server; print('OK')"` passes
- [ ] Full test suite passes: `cd app/bridge && python3 -m pytest tests/ -x`
- [ ] `_legacy_backup/` deleted
- [ ] Final commit: `refactor: remove extracted utility functions from server.py`

---

## Questions? Blockers?

Use Mission Command template:

```
## MC Question — [Agent Name]
**Zone:** [A/B/C/D/E]
**Issue:** [brief description]
**Options:** [A] ... [B] ...
**Recommendation:** [your pick]
```

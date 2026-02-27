# Zone D Assignment: Agent Helpers Extraction

**Branch:** `recover/uiux-restore-2026-02-19`
**Target Module:** `app/bridge/agent_helpers.py`
**Estimated Time:** 25 minutes
**Merge Order:** Can merge in any order (no dependencies)

---

## Your Mission

Extract agent/AI helper utilities from `server.py` to a new standalone module `agent_helpers.py`.

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
grep -n "^_codexrules_cache" app/bridge/server.py  # Expected: ~1258
grep -n "^def _normalize_reply_for_prompt" app/bridge/server.py  # Expected: ~1716
```

If line numbers differ by >50, stop and report to Mission Command.

---

## Items to Extract

| Item | Approx Lines | Notes |
|------|--------------|-------|
| `_codexrules_cache` | ~1258 | Module-level cache dict |
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

**Total:** ~490 lines

---

## Step 1: Create agent_helpers.py

Create `app/bridge/agent_helpers.py` with this structure:

```python
"""Agent/AI helper utilities extracted from server.py."""

import logging
import pathlib
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "_codexrules_cache",
    "_load_codexrules",
    "_resolve_system_prompt",
    "_agent_mode_system_prompt",
    "_agent_model_allowed",
    "_agent_mode_default_model",
    "_agent_resolve_model",
    "_agent_choose_executor",
    "_install_runtime_diagnostics",
    "_codex_cli_login_status",
    "_legacy_execution_guard",
    "_extract_mission_facts",
    "_first_sentence",
    "_truncate_words",
    "_is_high_risk_user_request",
    "_strip_repetitive_caution_lines",
    "_soften_forced_reply_exact",
    "_normalize_reply_for_prompt",
]


# Paste _codexrules_cache dict first, then all functions in order
# (copy verbatim from server.py lines ~1258-1750)
```

---

## Step 2: Add Import to server.py

Add this block at **line ~670** (end of existing imports, before first `def`):

```python
try:
    from app.bridge.agent_helpers import (
        _codexrules_cache,
        _load_codexrules,
        _resolve_system_prompt,
        _agent_mode_system_prompt,
        _agent_model_allowed,
        _agent_mode_default_model,
        _agent_resolve_model,
        _agent_choose_executor,
        _install_runtime_diagnostics,
        _codex_cli_login_status,
        _legacy_execution_guard,
        _extract_mission_facts,
        _first_sentence,
        _truncate_words,
        _is_high_risk_user_request,
        _strip_repetitive_caution_lines,
        _soften_forced_reply_exact,
        _normalize_reply_for_prompt,
    )
except ImportError:
    from agent_helpers import (  # type: ignore
        _codexrules_cache,
        _load_codexrules,
        _resolve_system_prompt,
        _agent_mode_system_prompt,
        _agent_model_allowed,
        _agent_mode_default_model,
        _agent_resolve_model,
        _agent_choose_executor,
        _install_runtime_diagnostics,
        _codex_cli_login_status,
        _legacy_execution_guard,
        _extract_mission_facts,
        _first_sentence,
        _truncate_words,
        _is_high_risk_user_request,
        _strip_repetitive_caution_lines,
        _soften_forced_reply_exact,
        _normalize_reply_for_prompt,
    )
```

---

## Step 3: Verification

Run these checks before committing:

```bash
# Module import check
python3 -c "from app.bridge.agent_helpers import _load_codexrules; print('OK')"

# Server still loads
python3 -c "from app.bridge import server; print('OK')"

# Run any existing tests
cd app/bridge && python3 -m pytest tests/ -x -q -k agent 2>/dev/null || echo "No agent tests found"
cd app/bridge && python3 -m pytest tests/ -x -q -k codex 2>/dev/null || echo "No codex tests found"
```

---

## Verification Checklist

- [ ] `agent_helpers.py` created at `app/bridge/`
- [ ] `_codexrules_cache` dict + all 17 functions copied verbatim
- [ ] `__all__` export list defined
- [ ] Import block added to server.py (~line 670)
- [ ] `python3 -c "from app.bridge.agent_helpers import *; print('OK')"` passes
- [ ] `python3 -c "from app.bridge import server; print('OK')"` passes
- [ ] No changes made to `build_handler()` body
- [ ] Original functions in server.py are UNTOUCHED (deletion is Phase 2)

---

## Commit Format

```
refactor: extract Zone D agent helpers to agent_helpers.py
```

---

## Questions/Blockers?

Use Mission Command template:

```
## MC Question — [Your Agent Name]
**Zone:** D
**Issue:** [brief description]
**Options:** [A] ... [B] ...
**Recommendation:** [your pick]
```

from __future__ import annotations

import os
from typing import Mapping, Optional, Dict, Any


LEGACY_EXEC_ENV_FLAG = "UPRIGHT_ALLOW_LEGACY_EXEC"


def parse_flag_enabled(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def legacy_execution_enabled(env: Optional[Mapping[str, str]] = None) -> bool:
    source = env if env is not None else os.environ
    return parse_flag_enabled(str(source.get(LEGACY_EXEC_ENV_FLAG, "")))


def legacy_execution_block_payload(path: str) -> Dict[str, Any]:
    return {
        "ok": False,
        "error": "legacy_execution_disabled",
        "message": "Legacy /agent/* execution routes are disabled by default. Use /agent/clean/* routes, or set UPRIGHT_ALLOW_LEGACY_EXEC=1 for explicit dev override.",
        "path": str(path or ""),
        "dev_flag": LEGACY_EXEC_ENV_FLAG,
        "clean_lane_default": True,
    }

"""
Agent Mission Manager - Agent mode configuration and management.

Extracted from server.py to domains/session_traceability/
"""

from __future__ import annotations

import json
import pathlib
import threading
import time
from typing import Any, Dict


class AgentMissionManager:
    def __init__(self, repo_root: pathlib.Path) -> None:
        self.path = repo_root / "app" / "bridge" / "agent_mode.json"
        self._lock = threading.Lock()
        self._allowed_modes = ("app_dev", "robot_dev", "ops_debug")

    def _default(self) -> Dict[str, Any]:
        now = time.time()
        return {
            "mode": "robot_dev",
            "updated_at": now,
            "allowed_modes": list(self._allowed_modes),
        }

    def status(self) -> Dict[str, Any]:
        with self._lock:
            if not self.path.exists():
                payload = self._default()
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(
                    json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
                )
                return payload
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    return self._default()
                mode = str(raw.get("mode", "robot_dev")).strip()
                if mode not in self._allowed_modes:
                    mode = "robot_dev"
                updated_at = float(raw.get("updated_at", time.time()) or time.time())
                return {
                    "mode": mode,
                    "updated_at": updated_at,
                    "allowed_modes": list(self._allowed_modes),
                }
            except Exception:
                return self._default()

    def set_mode(self, mode: str) -> Dict[str, Any]:
        normalized = str(mode).strip()
        if normalized not in self._allowed_modes:
            raise RuntimeError("invalid_mode")
        payload = {
            "mode": normalized,
            "updated_at": time.time(),
            "allowed_modes": list(self._allowed_modes),
        }
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
            )
        return payload

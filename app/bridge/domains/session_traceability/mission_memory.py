"""
Mission Memory Store - Per-session mission facts for assistant continuity.

Extracted from server.py to domains/session_traceability/
"""

from __future__ import annotations

import json
import os
import pathlib
import threading
import time
from typing import Any, Dict


class MissionMemoryStore:
    """Durable per-session mission facts for assistant continuity."""

    def __init__(self, repo_root: pathlib.Path) -> None:
        self.path = repo_root / "app" / "bridge" / "ai_mission_memory.json"
        self._lock = threading.Lock()
        self._data: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return
            clean: Dict[str, Dict[str, Any]] = {}
            for skey, node in raw.items():
                if not isinstance(skey, str) or not isinstance(node, dict):
                    continue
                facts = node.get("facts", {})
                if not isinstance(facts, dict):
                    facts = {}
                clean[skey] = {
                    "facts": {
                        str(k): str(v) for k, v in facts.items() if isinstance(k, str)
                    },
                    "updated_at": float(
                        node.get("updated_at", time.time()) or time.time()
                    ),
                    "source": str(node.get("source", "unknown")),
                }
            self._data = clean
        except Exception:
            self._data = {}

    def _save_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        blob = json.dumps(self._data, ensure_ascii=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(blob, encoding="utf-8")
        os.replace(tmp, self.path)

    def get(self, session_key: str) -> Dict[str, str]:
        with self._lock:
            node = self._data.get(session_key, {})
            facts = node.get("facts", {}) if isinstance(node, dict) else {}
            if not isinstance(facts, dict):
                return {}
            return {str(k): str(v) for k, v in facts.items() if isinstance(k, str)}

    def upsert(
        self,
        session_key: str,
        updates: Dict[str, str],
        *,
        source: str = "user_asserted",
    ) -> Dict[str, str]:
        clean = {
            str(k): str(v)
            for k, v in updates.items()
            if isinstance(k, str) and str(v).strip()
        }
        if not clean:
            return self.get(session_key)
        with self._lock:
            node = self._data.setdefault(
                session_key, {"facts": {}, "updated_at": 0.0, "source": source}
            )
            facts = node.setdefault("facts", {})
            if not isinstance(facts, dict):
                facts = {}
                node["facts"] = facts
            facts.update(clean)
            node["updated_at"] = time.time()
            node["source"] = source
            self._save_locked()
            return {str(k): str(v) for k, v in facts.items() if isinstance(k, str)}

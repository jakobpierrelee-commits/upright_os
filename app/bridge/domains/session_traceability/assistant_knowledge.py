"""
Assistant Knowledge Manager - Knowledge base loading for assistant context.

Extracted from server.py to domains/session_traceability/
"""

from __future__ import annotations

import json
import pathlib
import threading
import time
from typing import Any, Dict


class AssistantKnowledgeManager:
    def __init__(self, repo_root: pathlib.Path) -> None:
        self.root = repo_root
        self.base_dir = repo_root / "docs" / "assistant_knowledge"
        self.manifest_path = self.base_dir / "manifest.json"
        self._lock = threading.Lock()
        self._cache: Dict[str, Any] = {"ts": 0.0, "payload": None}
        self._cache_ttl_s = 2.0

    def _load_text(self, filename: str, max_chars: int = 7000) -> str:
        p = self.base_dir / filename
        if not p.exists() or not p.is_file():
            return ""
        try:
            txt = p.read_text(encoding="utf-8")
        except Exception:
            return ""
        if len(txt) > max_chars:
            return txt[:max_chars] + "\n\n[truncated]"
        return txt

    def _build_payload_unlocked(self) -> Dict[str, Any]:
        if not self.manifest_path.exists():
            return {"available": False, "error": "knowledge_manifest_missing"}
        try:
            man = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"available": False, "error": f"knowledge_manifest_invalid:{exc}"}
        if not isinstance(man, dict):
            return {"available": False, "error": "knowledge_manifest_not_object"}
        active = str(man.get("active_version", "")).strip()
        versions = man.get("versions", [])
        if not isinstance(versions, list):
            versions = []
        current = None
        for v in versions:
            if isinstance(v, dict) and str(v.get("version", "")) == active:
                current = v
                break
        if current is None and versions and isinstance(versions[0], dict):
            current = versions[0]
            active = str(current.get("version", "")).strip()
        if current is None:
            return {"available": False, "error": "knowledge_version_missing"}
        playbook_file = str(current.get("playbook_file", "")).strip()
        theory_file = str(current.get("theory_file", "")).strip()
        rules_file = str(current.get("rules_file", "")).strip()
        return {
            "available": True,
            "active_version": active,
            "label": str(current.get("label", "")),
            "created_at": str(current.get("created_at", "")),
            "changelog": list(current.get("changelog", []))
            if isinstance(current.get("changelog", []), list)
            else [],
            "playbook_markdown": self._load_text(playbook_file),
            "theory_markdown": self._load_text(theory_file),
            "rules_markdown": self._load_text(rules_file),
        }

    def context(self) -> Dict[str, Any]:
        now = time.monotonic()
        with self._lock:
            ts = float(self._cache.get("ts", 0.0) or 0.0)
            if (
                self._cache.get("payload") is not None
                and (now - ts) <= self._cache_ttl_s
            ):
                return dict(self._cache["payload"])
            payload = self._build_payload_unlocked()
            self._cache = {"ts": now, "payload": payload}
            return dict(payload)

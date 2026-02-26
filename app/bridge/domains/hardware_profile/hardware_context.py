"""
Hardware Context Store - Per-session hardware context for assistant awareness.

Extracted from server.py to domains/hardware_profile/
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import threading
import time
from typing import Any, Dict, List, Optional


class HardwareContextStore:
    """Durable per-session hardware context for assistant awareness + drift detection."""

    def __init__(self, repo_root: pathlib.Path) -> None:
        self.path = repo_root / "app" / "bridge" / "ai_hardware_context.json"
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
                ctx = node.get("context")
                digest = str(node.get("digest", ""))
                updated_at = float(node.get("updated_at", time.time()) or time.time())
                if isinstance(ctx, dict):
                    clean[skey] = {
                        "context": ctx,
                        "digest": digest,
                        "updated_at": updated_at,
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

    @staticmethod
    def _normalize(ctx: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(ctx, dict):
            return None
        try:
            txt = json.dumps(
                ctx, ensure_ascii=True, sort_keys=True, separators=(",", ":")
            )
            obj = json.loads(txt)
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None

    @staticmethod
    def _digest(ctx: Dict[str, Any]) -> str:
        txt = json.dumps(ctx, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(txt.encode("utf-8")).hexdigest()[:16]

    def get(self, session_key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            node = self._data.get(session_key)
            if not isinstance(node, dict):
                return None
            ctx = node.get("context")
            return dict(ctx) if isinstance(ctx, dict) else None

    def upsert(self, session_key: str, incoming_ctx: Any) -> Dict[str, Any]:
        normalized = self._normalize(incoming_ctx)
        if normalized is None:
            return {"accepted": False, "changed": False, "initial": False}
        new_digest = self._digest(normalized)
        changed_keys: List[str] = []
        with self._lock:
            prev = self._data.get(session_key)
            prev_ctx = prev.get("context") if isinstance(prev, dict) else None
            prev_digest = str(prev.get("digest", "")) if isinstance(prev, dict) else ""
            initial = prev_ctx is None
            changed = initial or (new_digest != prev_digest)
            if changed and isinstance(prev_ctx, dict):
                key_union = set(prev_ctx.keys()) | set(normalized.keys())
                changed_keys = sorted(
                    [k for k in key_union if prev_ctx.get(k) != normalized.get(k)]
                )
            elif changed:
                changed_keys = sorted(normalized.keys())
            self._data[session_key] = {
                "context": normalized,
                "digest": new_digest,
                "updated_at": time.time(),
            }
            self._save_locked()
        return {
            "accepted": True,
            "changed": changed,
            "initial": initial,
            "changed_keys": changed_keys[:16],
            "digest": new_digest,
        }

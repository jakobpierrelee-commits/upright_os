"""
Tuning Preflight Store - Preflight token management for tuning operations.

Extracted from server.py to domains/safety_prearm/
"""

from __future__ import annotations

import secrets
import threading
import time
from typing import Any, Dict


class TuningPreflightStore:
    def __init__(self, ttl_s: float = 900.0, max_entries: int = 256) -> None:
        self._ttl_s = ttl_s
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._items: Dict[str, Dict[str, Any]] = {}

    def _prune_locked(self) -> None:
        now = time.monotonic()
        expired = [
            k
            for k, v in self._items.items()
            if (now - float(v.get("ts", now))) > self._ttl_s
        ]
        for k in expired:
            self._items.pop(k, None)
        if len(self._items) <= self._max_entries:
            return
        ordered = sorted(
            self._items.items(), key=lambda kv: float(kv[1].get("ts", 0.0))
        )
        for k, _ in ordered[: max(0, len(self._items) - self._max_entries)]:
            self._items.pop(k, None)

    def issue(
        self, *, family: str, signature: str, score_pct: int, notes: list[str]
    ) -> Dict[str, Any]:
        with self._lock:
            self._prune_locked()
            preflight_id = secrets.token_urlsafe(18)
            self._items[preflight_id] = {
                "ts": time.monotonic(),
                "family": family,
                "signature": signature,
                "score_pct": int(score_pct),
                "notes": list(notes[:8]),
            }
        return {"preflight_id": preflight_id, "expires_in_s": int(self._ttl_s)}

    def validate(self, preflight_id: str, expected_signature: str) -> Dict[str, Any]:
        with self._lock:
            self._prune_locked()
            node = self._items.get(preflight_id)
            if not node:
                raise RuntimeError("preflight_invalid")
            if str(node.get("signature", "")) != expected_signature:
                raise RuntimeError("preflight_mismatch")
            return dict(node)

"""
Setup Attempt History Store - Durable setup validation attempt history.

Extracted from server.py to domains/session_traceability/
"""

from __future__ import annotations

import json
import os
import pathlib
import secrets
import threading
import time
from typing import Any, Dict


class SetupAttemptHistoryStore:
    """Durable setup validation attempt history for timeline rendering."""

    def __init__(self, repo_root: pathlib.Path, max_entries: int = 240) -> None:
        self.path = repo_root / "app" / "bridge" / "setup_attempt_history.json"
        self.max_entries = max(30, int(max_entries))
        self._lock = threading.Lock()
        self._entries: list[Dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                return
            clean: list[Dict[str, Any]] = []
            for node in raw:
                if not isinstance(node, dict):
                    continue
                attempt_id = str(node.get("attempt_id", "")).strip()
                if not attempt_id:
                    continue
                clean.append(
                    {
                        "attempt_id": attempt_id,
                        "test_type": str(node.get("test_type", "unknown")),
                        "status": str(node.get("status", "unknown")),
                        "created_at": float(
                            node.get("created_at", time.time()) or time.time()
                        ),
                        "sketch_revision": str(node.get("sketch_revision", "")),
                        "sketch_hash": str(node.get("sketch_hash", "")),
                        "action_source": str(node.get("action_source", "setup_page")),
                        "profile_id": str(node.get("profile_id", "")),
                        "profile_label": str(node.get("profile_label", "")),
                        "result": node.get("result")
                        if isinstance(node.get("result"), dict)
                        else {},
                    }
                )
            self._entries = clean[-self.max_entries :]
        except Exception:
            self._entries = []

    def _save_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        blob = json.dumps(self._entries, ensure_ascii=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(blob, encoding="utf-8")
        os.replace(tmp, self.path)

    @staticmethod
    def _new_attempt_id() -> str:
        return f"setup_{int(time.time() * 1000)}_{secrets.token_hex(3)}"

    def append(
        self,
        *,
        test_type: str,
        status: str,
        sketch_revision: str,
        sketch_hash: str,
        action_source: str,
        profile_id: str,
        profile_label: str,
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        entry = {
            "attempt_id": self._new_attempt_id(),
            "test_type": str(test_type or "unknown"),
            "status": str(status or "unknown"),
            "created_at": time.time(),
            "sketch_revision": str(sketch_revision or ""),
            "sketch_hash": str(sketch_hash or ""),
            "action_source": str(action_source or "setup_page"),
            "profile_id": str(profile_id or ""),
            "profile_label": str(profile_label or ""),
            "result": dict(result),
        }
        with self._lock:
            self._entries.append(entry)
            self._entries = self._entries[-self.max_entries :]
            self._save_locked()
        return dict(entry)

    def list_recent(self, limit: int = 40) -> list[Dict[str, Any]]:
        take = max(1, min(int(limit), self.max_entries))
        with self._lock:
            rows = self._entries[-take:]
            return [dict(r) for r in reversed(rows)]

    def list_recent_page(
        self,
        *,
        limit: int = 20,
        cursor_attempt_id: str = "",
        kind: str = "all",
    ) -> Dict[str, Any]:
        take = max(1, min(int(limit), 80))
        kind_norm = str(kind or "all").strip().lower()
        with self._lock:
            rows = list(self._entries)
        rows_rev = list(reversed(rows))
        if kind_norm not in {"", "all"}:
            rows_rev = [
                r for r in rows_rev if str(r.get("test_type", "")).lower() == kind_norm
            ]
        start_idx = 0
        cursor = str(cursor_attempt_id or "").strip()
        if cursor:
            found_idx = next(
                (
                    i
                    for i, r in enumerate(rows_rev)
                    if str(r.get("attempt_id", "")) == cursor
                ),
                None,
            )
            if found_idx is not None:
                start_idx = found_idx + 1
        page = rows_rev[start_idx : start_idx + take]
        next_cursor = ""
        if (start_idx + take) < len(rows_rev) and page:
            next_cursor = str(page[-1].get("attempt_id", ""))
        return {
            "attempts": [dict(r) for r in page],
            "next_cursor": next_cursor,
            "has_more": bool(next_cursor),
        }

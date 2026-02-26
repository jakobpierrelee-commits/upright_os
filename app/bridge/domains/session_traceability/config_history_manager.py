"""
Config History Manager - Configuration snapshot tracking.

Extracted from server.py to domains/session_traceability/
"""

from __future__ import annotations

import json
import pathlib
import secrets
import threading
import time
from typing import Any, Dict, Optional


def _safe_float(v: Any) -> Optional[float]:
    try:
        return float(v)
    except Exception:
        return None


def _first_float(status: Dict[str, Any], *keys: str) -> Optional[float]:
    for k in keys:
        if k in status:
            out = _safe_float(status.get(k))
            if out is not None:
                return out
    return None


class ConfigHistoryManager:
    def __init__(self, repo_root: pathlib.Path) -> None:
        self.path = repo_root / "app" / "bridge" / "config_history.json"
        self._lock = threading.Lock()
        self._max_entries = 200

    def _read_unlocked(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"snapshots": []}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"snapshots": []}
        if not isinstance(raw, dict):
            return {"snapshots": []}
        snaps = raw.get("snapshots")
        if not isinstance(snaps, list):
            snaps = []
        return {"snapshots": snaps}

    def _write_unlocked(self, data: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, indent=2, sort_keys=True), encoding="utf-8"
        )

    def _capture_fields(self, status: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "pid": {
                "kp": _first_float(status, "kp"),
                "ki": _first_float(status, "ki"),
                "kd": _first_float(status, "kd"),
            },
            "motion": {
                "kv": _first_float(status, "kv"),
                "kx": _first_float(status, "kx"),
            },
            "setpoint": {
                "deg": _first_float(status, "set"),
            },
            "limits": {
                "out_max": _first_float(status, "outMax", "out_max"),
                "tip_deg": _first_float(status, "tipDeg", "tip_deg"),
                "i_max": _first_float(status, "iMax", "i_max"),
            },
        }

    def save_snapshot(
        self, *, source: str, status_before: Dict[str, Any], note: str = ""
    ) -> Dict[str, Any]:
        entry = {
            "snapshot_id": secrets.token_urlsafe(8),
            "ts": time.time(),
            "source": source,
            "note": note,
            "values": self._capture_fields(status_before),
            "status_before": dict(status_before),
        }
        with self._lock:
            data = self._read_unlocked()
            snaps = list(data.get("snapshots", []))
            snaps.append(entry)
            if len(snaps) > self._max_entries:
                snaps = snaps[-self._max_entries :]
            data["snapshots"] = snaps
            self._write_unlocked(data)
        return entry

    def list_snapshots(self, *, limit: int = 30) -> list:
        n = max(1, min(int(limit), 200))
        with self._lock:
            data = self._read_unlocked()
            snaps = list(data.get("snapshots", []))
        snaps.sort(key=lambda e: float(e.get("ts", 0.0) or 0.0), reverse=True)
        return snaps[:n]

    def get_snapshot(
        self, snapshot_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        with self._lock:
            data = self._read_unlocked()
            snaps = list(data.get("snapshots", []))
        if not snaps:
            return None
        if snapshot_id:
            for e in snaps:
                if str(e.get("snapshot_id", "")) == snapshot_id:
                    return e
            return None
        snaps.sort(key=lambda e: float(e.get("ts", 0.0) or 0.0), reverse=True)
        return snaps[0]

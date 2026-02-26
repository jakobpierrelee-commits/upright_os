"""
Config History - Configuration change tracking.

Tracks all configuration changes made during a tuning session
for audit and rollback purposes.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ConfigChange:
    """A single configuration change record."""
    ts: float
    param: str
    old_value: Any
    new_value: Any
    source: str = "unknown"  # "user", "agent", "rollback", etc.
    session_id: str = ""


class ConfigHistory:
    """
    Tracks configuration changes over time.
    
    Maintains a history of all PID and config changes for
    audit, rollback, and analysis purposes.
    """

    def __init__(
        self,
        history_file: Optional[Path] = None,
        max_entries: int = 1000,
    ):
        self._history_file = history_file
        self._max_entries = max_entries
        self._changes: List[ConfigChange] = []
        self._current_config: Dict[str, Any] = {}
        
        if history_file and history_file.exists():
            self._load()

    def record_change(
        self,
        param: str,
        old_value: Any,
        new_value: Any,
        source: str = "unknown",
        session_id: str = "",
    ) -> None:
        """Record a configuration change."""
        change = ConfigChange(
            ts=time.time(),
            param=param,
            old_value=old_value,
            new_value=new_value,
            source=source,
            session_id=session_id,
        )
        self._changes.append(change)
        self._current_config[param] = new_value
        
        # Trim if over limit
        if len(self._changes) > self._max_entries:
            self._changes = self._changes[-self._max_entries:]
        
        # Auto-save if file configured
        if self._history_file:
            self._save()

    def get_history(
        self,
        param: Optional[str] = None,
        since_ts: Optional[float] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get configuration change history."""
        results = self._changes
        
        if param:
            results = [c for c in results if c.param == param]
        if since_ts:
            results = [c for c in results if c.ts >= since_ts]
        
        # Return most recent first
        results = sorted(results, key=lambda x: x.ts, reverse=True)[:limit]
        
        return [
            {
                "ts": c.ts,
                "param": c.param,
                "old_value": c.old_value,
                "new_value": c.new_value,
                "source": c.source,
                "session_id": c.session_id,
            }
            for c in results
        ]

    def get_current_config(self) -> Dict[str, Any]:
        """Get the current configuration state."""
        return dict(self._current_config)

    def get_config_at(self, ts: float) -> Dict[str, Any]:
        """Reconstruct configuration at a specific timestamp."""
        config: Dict[str, Any] = {}
        for change in sorted(self._changes, key=lambda x: x.ts):
            if change.ts <= ts:
                config[change.param] = change.new_value
        return config

    def _load(self) -> None:
        """Load history from file."""
        if not self._history_file or not self._history_file.exists():
            return
        try:
            data = json.loads(self._history_file.read_text())
            self._changes = [
                ConfigChange(
                    ts=c["ts"],
                    param=c["param"],
                    old_value=c["old_value"],
                    new_value=c["new_value"],
                    source=c.get("source", "unknown"),
                    session_id=c.get("session_id", ""),
                )
                for c in data.get("changes", [])
            ]
            self._current_config = data.get("current", {})
        except Exception:
            pass

    def _save(self) -> None:
        """Save history to file."""
        if not self._history_file:
            return
        try:
            data = {
                "changes": [
                    {
                        "ts": c.ts,
                        "param": c.param,
                        "old_value": c.old_value,
                        "new_value": c.new_value,
                        "source": c.source,
                        "session_id": c.session_id,
                    }
                    for c in self._changes
                ],
                "current": self._current_config,
            }
            self._history_file.write_text(json.dumps(data, indent=2))
        except Exception:
            pass

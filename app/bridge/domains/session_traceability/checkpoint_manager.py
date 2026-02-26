"""
Checkpoint Manager - Checkpoint save/restore/query operations.

Manages tuning checkpoints - snapshots of robot state that can be
saved, rated, and restored later.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    from app.bridge.codex_db import CodexDB
except ImportError:
    from codex_db import CodexDB  # type: ignore


@dataclass
class Checkpoint:
    """A tuning checkpoint."""

    id: int
    ts: float
    robot_id: str
    rating: Optional[str]
    mode: str
    kp: float
    ki: float
    kd: float
    setpoint: float
    notes: str
    config: Dict[str, Any] = field(default_factory=dict)


class CheckpointManager:
    """
    Manages tuning checkpoint operations.

    Provides save, restore, query, and comparison operations
    for tuning checkpoints.
    """

    def __init__(self, db: CodexDB, robot_id: str = ""):
        self._db = db
        self._robot_id = robot_id

    def save_checkpoint(
        self,
        kp: float,
        ki: float,
        kd: float,
        setpoint: float = 0.0,
        mode: str = "",
        rating: Optional[str] = None,
        notes: str = "",
        config: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Save a new checkpoint.

        Returns the checkpoint ID.
        """
        return self._db.save_checkpoint(
            robot_id=self._robot_id,
            ts=time.time(),
            kp=kp,
            ki=ki,
            kd=kd,
            setpoint=setpoint,
            mode=mode,
            rating=rating,
            notes=notes,
            config_json=config,
        )

    def get_checkpoint(self, checkpoint_id: int) -> Optional[Checkpoint]:
        """Get a checkpoint by ID."""
        checkpoints = self._db.query_checkpoints(
            robot_id=self._robot_id,
            limit=100,
        )
        for cp in checkpoints:
            if cp.get("id") == checkpoint_id:
                return self._to_checkpoint(cp)
        return None

    def query_checkpoints(
        self,
        rating: Optional[str] = None,
        min_rating: Optional[str] = None,
        limit: int = 10,
    ) -> List[Checkpoint]:
        """Query checkpoints with optional filters."""
        results = self._db.query_checkpoints(
            robot_id=self._robot_id,
            rating=rating,
            min_rating=min_rating,
            limit=limit,
        )
        return [self._to_checkpoint(r) for r in results]

    def get_best_checkpoint(self) -> Optional[Checkpoint]:
        """Get the highest-rated checkpoint."""
        for rating in ["great", "good", "ok", "poor"]:
            checkpoints = self.query_checkpoints(rating=rating, limit=1)
            if checkpoints:
                return checkpoints[0]
        return None

    def rate_checkpoint(self, checkpoint_id: int, rating: str) -> bool:
        """Update the rating of a checkpoint."""
        return self._db.update_checkpoint_rating(checkpoint_id, rating)

    def _to_checkpoint(self, data: Dict[str, Any]) -> Checkpoint:
        """Convert dict to Checkpoint dataclass."""
        return Checkpoint(
            id=data.get("id", 0),
            ts=data.get("ts", 0.0),
            robot_id=data.get("robot_id", ""),
            rating=data.get("rating"),
            mode=data.get("mode", ""),
            kp=data.get("kp", 0.0),
            ki=data.get("ki", 0.0),
            kd=data.get("kd", 0.0),
            setpoint=data.get("setpoint", 0.0),
            notes=data.get("notes", ""),
            config=data.get("config", {}),
        )

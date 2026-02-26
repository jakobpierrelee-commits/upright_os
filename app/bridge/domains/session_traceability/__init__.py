"""
Session Traceability Domain

Handles session state, checkpoint management, config history, and audit trails.
Provides persistent storage and recall for tuning sessions.

Components:
- codex_db: Persistent storage for telemetry and sessions
- checkpoint_manager: Checkpoint save/restore/query
- config_history: Configuration change tracking
"""

# Re-export from existing modules (facade pattern)
try:
    from app.bridge.codex_db import CodexDB, get_codex_db
except ImportError:
    from codex_db import CodexDB, get_codex_db  # type: ignore

# Local domain components
from .checkpoint_manager import CheckpointManager, Checkpoint
from .config_history import ConfigHistory, ConfigChange
from .config_history_manager import ConfigHistoryManager
from .mission_memory import MissionMemoryStore
from .design_memory import DesignMemoryStore

__all__ = [
    "CodexDB",
    "get_codex_db",
    "CheckpointManager",
    "Checkpoint",
    "ConfigHistory",
    "ConfigChange",
    "ConfigHistoryManager",
    "MissionMemoryStore",
    "DesignMemoryStore",
]

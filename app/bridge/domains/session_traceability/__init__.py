"""
Session Traceability Domain

Handles session state, checkpoint management, config history, and audit trails.
Provides persistent storage and recall for tuning sessions.

Components:
- codex_db: Persistent storage for telemetry and sessions
- checkpoint_manager: Checkpoint save/restore/query
- config_history: Configuration change tracking
"""

# Import from local copies in domain
try:
    from .codex_db import CodexDB, get_codex_db
except ImportError:
    # Fallback to original location during transition
    from codex_db import CodexDB, get_codex_db  # type: ignore

from .checkpoint_manager import CheckpointManager, Checkpoint
from .config_history import ConfigHistory, ConfigChange

__all__ = [
    "CodexDB",
    "get_codex_db",
    "CheckpointManager",
    "Checkpoint",
    "ConfigHistory",
    "ConfigChange",
]

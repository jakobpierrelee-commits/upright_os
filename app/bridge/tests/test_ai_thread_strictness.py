import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from server import AIManager


def test_explicit_invalid_thread_id_raises(tmp_path: Path) -> None:
    ai = AIManager(tmp_path)
    session_key = "user:test"
    tid = ai._append(session_key, "user", "hello")
    assert tid

    with pytest.raises(RuntimeError, match="thread_not_found"):
        ai._append(session_key, "user", "next", thread_id="missing-thread-id")


def test_missing_explicit_thread_does_not_change_active(tmp_path: Path) -> None:
    ai = AIManager(tmp_path)
    session_key = "user:test"
    tid = ai._append(session_key, "user", "hello")
    active_before = ai.status(configured=True, model="gpt-5-mini", session_key=session_key)["active_thread_id"]
    assert active_before == tid

    with pytest.raises(RuntimeError, match="thread_not_found"):
        ai.history(session_key, "missing-thread-id")

    active_after = ai.status(configured=True, model="gpt-5-mini", session_key=session_key)["active_thread_id"]
    assert active_after == tid

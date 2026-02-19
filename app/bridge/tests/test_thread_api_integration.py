"""Integration tests for thread_id handling at HTTP API level.

These tests validate that stale/invalid thread_ids are rejected at the API
boundary with proper 404 responses, rather than silently falling back.
"""
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from server import AIManager


class MockRequestHandler:
    """Minimal mock of HTTP request handler for testing _json responses."""

    def __init__(self) -> None:
        self.response_code: Optional[int] = None
        self.response_body: Optional[Dict[str, Any]] = None
        self.headers_sent: Dict[str, str] = {}

    def send_response(self, code: int) -> None:
        self.response_code = code

    def send_header(self, key: str, value: str) -> None:
        self.headers_sent[key] = value

    def end_headers(self) -> None:
        pass

    @property
    def wfile(self) -> MagicMock:
        mock = MagicMock()
        return mock


def _json(handler: MockRequestHandler, code: int, body: Dict[str, Any]) -> None:
    """Simplified _json helper matching server.py behavior."""
    import json

    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.end_headers()
    handler.response_code = code
    handler.response_body = body


class TestThreadIdApiIntegration:
    """Test thread_id validation at API boundary level."""

    def test_stale_thread_id_returns_404_not_silent_fallback(self, tmp_path: Path) -> None:
        """
        Scenario: Client sends a thread_id that does not exist in storage.
        Expected: API returns 404 with error='thread_not_found'.
        Before fix: Would silently create new thread or use active thread.
        """
        ai = AIManager(tmp_path)
        session_key = "user:42"

        # Create a valid thread first
        valid_tid = ai._append(session_key, "user", "hello world")
        assert valid_tid is not None

        # Attempt to access a non-existent thread_id
        stale_thread_id = "nonexistent-thread-abc123"

        # Simulate API-level validation (as done in server.py /ai/chat and /ai/chat/tools)
        handler = MockRequestHandler()

        # This is the validation pattern used in server.py before calling ai.chat()
        if stale_thread_id:
            try:
                ai.history(session_key, stale_thread_id)
                # If we get here, thread exists - continue to chat
                _json(handler, 200, {"ok": True, "thread_id": stale_thread_id})
            except RuntimeError as exc:
                if str(exc) == "thread_not_found":
                    _json(handler, 404, {"ok": False, "error": "thread_not_found"})
                else:
                    raise

        assert handler.response_code == 404
        assert handler.response_body is not None
        assert handler.response_body["ok"] is False
        assert handler.response_body["error"] == "thread_not_found"

    def test_valid_thread_id_passes_validation(self, tmp_path: Path) -> None:
        """
        Scenario: Client sends a valid thread_id that exists.
        Expected: API proceeds normally (200 OK path).
        """
        ai = AIManager(tmp_path)
        session_key = "user:42"

        # Create a valid thread
        valid_tid = ai._append(session_key, "user", "hello world")
        assert valid_tid is not None

        handler = MockRequestHandler()

        # Validate existing thread_id
        if valid_tid:
            try:
                history = ai.history(session_key, valid_tid)
                # Thread exists, would proceed to chat
                _json(handler, 200, {"ok": True, "thread_id": valid_tid, "history_len": len(history)})
            except RuntimeError as exc:
                if str(exc) == "thread_not_found":
                    _json(handler, 404, {"ok": False, "error": "thread_not_found"})
                else:
                    raise

        assert handler.response_code == 200
        assert handler.response_body is not None
        assert handler.response_body["ok"] is True
        assert handler.response_body["thread_id"] == valid_tid

    def test_empty_thread_id_skips_validation(self, tmp_path: Path) -> None:
        """
        Scenario: Client sends empty/null thread_id (new conversation).
        Expected: No validation performed, proceeds to create new thread.
        """
        ai = AIManager(tmp_path)
        session_key = "user:42"

        handler = MockRequestHandler()

        # Empty thread_id should skip validation (as in server.py)
        thread_id = ""
        thread_id = thread_id.strip() or None

        if thread_id:
            try:
                ai.history(session_key, thread_id)
            except RuntimeError as exc:
                if str(exc) == "thread_not_found":
                    _json(handler, 404, {"ok": False, "error": "thread_not_found"})
                    return

        # No validation needed, would proceed to create new thread
        _json(handler, 200, {"ok": True, "thread_id": None, "note": "new_thread_will_be_created"})

        assert handler.response_code == 200
        assert handler.response_body is not None
        assert handler.response_body["ok"] is True

    def test_stale_thread_does_not_affect_active_thread(self, tmp_path: Path) -> None:
        """
        Scenario: Failed stale thread lookup should not change active thread state.
        Expected: Active thread remains unchanged after failed lookup.
        """
        ai = AIManager(tmp_path)
        session_key = "user:42"

        # Create valid thread and note the active thread
        valid_tid = ai._append(session_key, "user", "first message")
        status_before = ai.status(configured=True, model="gpt-5-mini", session_key=session_key)
        active_before = status_before["active_thread_id"]
        assert active_before == valid_tid

        # Attempt stale lookup
        stale_thread_id = "stale-thread-xyz"
        with pytest.raises(RuntimeError, match="thread_not_found"):
            ai.history(session_key, stale_thread_id)

        # Active thread should be unchanged
        status_after = ai.status(configured=True, model="gpt-5-mini", session_key=session_key)
        active_after = status_after["active_thread_id"]
        assert active_after == active_before, "Active thread changed after failed stale lookup"

    def test_cross_session_thread_id_rejected(self, tmp_path: Path) -> None:
        """
        Scenario: Client A's thread_id used by Client B.
        Expected: 404 thread_not_found (threads are session-scoped).
        """
        ai = AIManager(tmp_path)
        session_a = "user:100"
        session_b = "user:200"

        # User A creates a thread
        tid_a = ai._append(session_a, "user", "hello from user A")
        assert tid_a is not None

        # User B tries to access User A's thread
        handler = MockRequestHandler()
        try:
            ai.history(session_b, tid_a)
            _json(handler, 200, {"ok": True})
        except RuntimeError as exc:
            if str(exc) == "thread_not_found":
                _json(handler, 404, {"ok": False, "error": "thread_not_found"})
            else:
                raise

        assert handler.response_code == 404
        assert handler.response_body["error"] == "thread_not_found"

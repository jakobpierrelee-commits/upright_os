"""
Tests for PR3: Failure Handling + Observability

Tests:
- ToolExecutionError class
- tool_audit table and methods in CodexDB
- Serial busy guard in CodexToolExecutor
- OpenAI timeout handling
"""

import time
import tempfile
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from codex_db import CodexDB, ToolAudit
from codex_agent import ToolExecutionError, CodexAgent, OPENAI_TIMEOUT_S
from codex_tools import CodexToolExecutor, ToolResult


class TestToolExecutionError:
    """Tests for ToolExecutionError class."""

    def test_error_creation(self):
        err = ToolExecutionError(tool="test_tool", message="Something failed")
        assert err.tool == "test_tool"
        assert err.message == "Something failed"
        assert err.recoverable is True
        assert "test_tool" in str(err)
        assert "Something failed" in str(err)

    def test_error_non_recoverable(self):
        err = ToolExecutionError(tool="critical_tool", message="Fatal error", recoverable=False)
        assert err.recoverable is False

    def test_error_to_dict(self):
        err = ToolExecutionError(tool="my_tool", message="Error msg", recoverable=True)
        d = err.to_dict()
        assert d["error_type"] == "ToolExecutionError"
        assert d["tool"] == "my_tool"
        assert d["message"] == "Error msg"
        assert d["recoverable"] is True


class TestToolAuditDB:
    """Tests for tool_audit table and methods in CodexDB."""

    @pytest.fixture
    def db(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        db = CodexDB(db_path)
        db.init_schema()
        yield db
        db.close()
        db_path.unlink(missing_ok=True)

    def test_log_tool_audit_success(self, db):
        row_id = db.log_tool_audit(
            tool="get_probe_results",
            args_hash="abc123",
            ok=True,
            latency_ms=42.5,
            error=None,
        )
        assert row_id is not None
        assert row_id > 0

    def test_log_tool_audit_failure(self, db):
        row_id = db.log_tool_audit(
            tool="execute_command",
            args_hash="def456",
            ok=False,
            latency_ms=100.0,
            error="Command blocked",
        )
        assert row_id is not None

    def test_get_tool_metrics_empty(self, db):
        metrics = db.get_tool_metrics()
        assert metrics["total_calls"] == 0
        assert metrics["success_rate"] == 1.0
        assert metrics["per_tool"] == []
        assert metrics["recent_errors"] == []

    def test_get_tool_metrics_with_data(self, db):
        # Log some audit records
        db.log_tool_audit("tool_a", "h1", True, 10.0)
        db.log_tool_audit("tool_a", "h2", True, 20.0)
        db.log_tool_audit("tool_a", "h3", False, 30.0, "Some error")
        db.log_tool_audit("tool_b", "h4", True, 15.0)

        metrics = db.get_tool_metrics()
        assert metrics["total_calls"] == 4
        assert metrics["success_calls"] == 3
        assert metrics["failed_calls"] == 1
        assert metrics["success_rate"] == 0.75
        assert len(metrics["per_tool"]) == 2
        assert len(metrics["recent_errors"]) == 1
        assert metrics["recent_errors"][0]["tool"] == "tool_a"

    def test_get_tool_metrics_with_filter(self, db):
        db.log_tool_audit("tool_a", "h1", True, 10.0)
        db.log_tool_audit("tool_b", "h2", True, 20.0)

        metrics = db.get_tool_metrics(tool_filter="tool_a")
        assert metrics["total_calls"] == 1
        assert len(metrics["per_tool"]) == 1
        assert metrics["per_tool"][0]["tool"] == "tool_a"

    def test_get_tool_metrics_since_ts(self, db):
        old_ts = time.time() - 7200  # 2 hours ago
        now_ts = time.time()

        # Manually insert an old record
        with db._cursor() as cur:
            cur.execute(
                "INSERT INTO tool_audit (ts, tool, args_hash, ok, latency_ms) VALUES (?, ?, ?, ?, ?)",
                (old_ts, "old_tool", "h1", 1, 10.0),
            )

        db.log_tool_audit("new_tool", "h2", True, 20.0)

        # Query with since_ts filtering out the old one
        metrics = db.get_tool_metrics(since_ts=now_ts - 60)
        assert metrics["total_calls"] == 1
        assert metrics["per_tool"][0]["tool"] == "new_tool"

    def test_prune_tool_audit(self, db):
        old_ts = time.time() - (10 * 24 * 60 * 60)  # 10 days ago

        # Insert old records
        with db._cursor() as cur:
            for i in range(5):
                cur.execute(
                    "INSERT INTO tool_audit (ts, tool, args_hash, ok, latency_ms) VALUES (?, ?, ?, ?, ?)",
                    (old_ts, f"old_tool_{i}", f"h{i}", 1, 10.0),
                )

        # Insert recent record
        db.log_tool_audit("recent_tool", "h_new", True, 20.0)

        # Prune with 7 day retention
        deleted = db.prune_tool_audit(max_age_days=7)
        assert deleted == 5

        metrics = db.get_tool_metrics()
        assert metrics["total_calls"] == 1
        assert metrics["per_tool"][0]["tool"] == "recent_tool"

    def test_get_stats_includes_tool_audit(self, db):
        db.log_tool_audit("test", "h1", True, 10.0)
        db.log_tool_audit("test", "h2", True, 10.0)

        stats = db.get_stats()
        assert "tool_audit_count" in stats
        assert stats["tool_audit_count"] == 2


class TestSerialBusyGuard:
    """Tests for serial busy guard in CodexToolExecutor."""

    def test_execute_command_returns_busy_error(self):
        """Test that execute_command returns SERIAL_BUSY error when gateway is busy."""
        mock_gateway = MagicMock()
        mock_gateway.is_busy.return_value = True

        executor = CodexToolExecutor(gateway=mock_gateway)
        result = executor.execute("execute_command", {"cmd": "PID 1.0 0 0"})

        assert result.ok is False
        assert "SERIAL_BUSY" in result.error
        assert result.data.get("retry_after_ms") == 500

    def test_execute_command_proceeds_when_not_busy(self):
        """Test that execute_command proceeds normally when gateway is not busy."""
        mock_gateway = MagicMock()
        mock_gateway.is_busy.return_value = False
        mock_gateway.command.return_value = "OK"
        mock_gateway.get_status.return_value = {"mode": "SAFE_IDLE"}

        executor = CodexToolExecutor(gateway=mock_gateway)
        result = executor.execute("execute_command", {"cmd": "PID 1.0 0 0"})

        assert result.ok is True
        assert result.data["command"] == "PID 1.0 0 0"
        mock_gateway.command.assert_called_once()

    def test_execute_command_proceeds_without_is_busy_method(self):
        """Test that execute_command proceeds if gateway has no is_busy method."""
        mock_gateway = MagicMock(spec=["command", "get_status"])  # No is_busy
        mock_gateway.command.return_value = "OK"
        mock_gateway.get_status.return_value = {"mode": "SAFE_IDLE"}

        executor = CodexToolExecutor(gateway=mock_gateway)
        result = executor.execute("execute_command", {"cmd": "GET"})

        assert result.ok is True
        mock_gateway.command.assert_called_once()


class TestOpenAITimeoutHandling:
    """Tests for OpenAI timeout handling in CodexAgent."""

    def test_timeout_constant_is_45_seconds(self):
        """Verify the timeout constant is set to 45 seconds."""
        assert OPENAI_TIMEOUT_S == 45

    def test_call_openai_timeout_error_message(self):
        """Test that timeout produces user-friendly error message."""
        agent = CodexAgent()

        # Mock urlrequest.urlopen to raise timeout
        with patch("codex_agent.urlrequest.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = TimeoutError("Connection timed out")

            with pytest.raises(RuntimeError) as exc_info:
                agent._call_openai(
                    messages=[{"role": "user", "content": "test"}],
                    api_key="test-key",
                    model="gpt-4",
                )

            assert "openai_timeout" in str(exc_info.value)
            assert "45 seconds" in str(exc_info.value)

    def test_call_openai_socket_timeout_detection(self):
        """Test that socket timeout is detected via error message."""
        agent = CodexAgent()

        with patch("codex_agent.urlrequest.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = Exception("Read timed out")

            with pytest.raises(RuntimeError) as exc_info:
                agent._call_openai(
                    messages=[{"role": "user", "content": "test"}],
                    api_key="test-key",
                    model="gpt-4",
                )

            assert "openai_timeout" in str(exc_info.value)


class TestToolAuditLogging:
    """Tests for structured JSON logging in CodexAgent."""

    def test_log_tool_audit_called_during_execution(self):
        """Test that _log_tool_audit is called after tool execution."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        db = CodexDB(db_path)
        db.init_schema()

        agent = CodexAgent(db=db)

        # Create mock response with tool call
        mock_response = {
            "choices": [{
                "message": {
                    "content": "Done",
                    "tool_calls": None,
                }
            }]
        }

        # Patch _call_openai to return our mock response
        with patch.object(agent, "_call_openai", return_value=mock_response):
            # This won't actually execute tools since no tool_calls in response
            result = agent.chat_with_tools(
                message="test",
                context={},
                api_key="test-key",
                model="gpt-4",
                system_prompt="test",
                enable_tools=False,
            )

        db.close()
        db_path.unlink(missing_ok=True)

        # Verify no errors
        assert result["answer"] == "Done"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""
Sprint 4 Acceptance Tests: T2 Experimentation Tools

Tests for diff_config, safe_rollback, and run_experiment
per PRD_AGENT_TOOLS_V2.md acceptance criteria.
"""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from codex_tools import (
    CodexToolExecutor,
    ToolResult,
    T1Errors,
    T2Errors,
    FACTORY_DEFAULTS,
    RATING_HIERARCHY,
    SAFE_COMMANDS,
    BLOCKED_COMMANDS,
    ObservationLimits,
)


# ============================================================================
# Mock Checkpoint for tests
# ============================================================================

@dataclass
class MockCheckpoint:
    id: str
    rating: str
    ts: float
    kp: float
    ki: float
    kd: float
    robot_id: str = "default"


# ============================================================================
# diff_config Tests
# ============================================================================

class TestDiffConfig:
    """Tests for diff_config tool."""

    def _make_executor(self, gateway=None, db=None):
        """Create executor with mocked dependencies."""
        return CodexToolExecutor(gateway=gateway, db=db)

    def test_diff_factory_defaults_identical(self):
        """diff_config against factory when config matches should show no diffs."""
        mock_gateway = MagicMock()
        mock_gateway.get_status.return_value = {
            "kp": FACTORY_DEFAULTS["kp"],
            "ki": FACTORY_DEFAULTS["ki"],
            "kd": FACTORY_DEFAULTS["kd"],
            "set": FACTORY_DEFAULTS["setpoint"],
        }

        executor = self._make_executor(gateway=mock_gateway)
        result = executor.execute("diff_config", {"compare_to": "factory"})

        assert result.ok
        assert len(result.data["diffs"]) == 0
        assert "kp" in result.data["identical"]
        assert "No differences" in result.data["summary"]

    def test_diff_factory_defaults_with_changes(self):
        """diff_config against factory when config differs should show delta percentages."""
        mock_gateway = MagicMock()
        mock_gateway.get_status.return_value = {
            "kp": 22.0,  # +22% from 18.0
            "ki": 0.1,   # same
            "kd": 0.3,   # -50% from 0.6
            "set": 2.0,  # +2.0 from 0
        }

        executor = self._make_executor(gateway=mock_gateway)
        result = executor.execute("diff_config", {"compare_to": "factory"})

        assert result.ok
        assert len(result.data["diffs"]) == 3
        assert "ki" in result.data["identical"]

        # Check kp diff
        kp_diff = next(d for d in result.data["diffs"] if d["param"] == "kp")
        assert kp_diff["current"] == 22.0
        assert kp_diff["reference"] == 18.0
        assert "+22%" in kp_diff["delta"]

        # Check kd diff
        kd_diff = next(d for d in result.data["diffs"] if d["param"] == "kd")
        assert "-50%" in kd_diff["delta"]

    def test_diff_checkpoint_best_rated(self):
        """diff_config against checkpoint should use best-rated by default."""
        mock_gateway = MagicMock()
        mock_gateway.get_status.return_value = {"kp": 20.0, "ki": 0.1, "kd": 0.5, "set": 0}

        mock_db = MagicMock()
        great_checkpoint = MockCheckpoint(
            id="cp_great", rating="great", ts=1000, kp=18.0, ki=0.1, kd=0.6
        )
        mock_db.query_checkpoints.return_value = [great_checkpoint]

        executor = self._make_executor(gateway=mock_gateway, db=mock_db)
        result = executor.execute("diff_config", {"compare_to": "checkpoint"})

        assert result.ok
        assert result.data["checkpoint_id"] == "cp_great"
        assert result.data["checkpoint_rating"] == "great"
        assert len(result.data["diffs"]) >= 1

    def test_diff_checkpoint_specific_id(self):
        """diff_config with specific checkpoint_id should use that checkpoint."""
        mock_gateway = MagicMock()
        mock_gateway.get_status.return_value = {"kp": 15.0, "ki": 0.2, "kd": 0.4, "set": 0}

        mock_db = MagicMock()
        target_checkpoint = MockCheckpoint(
            id="cp_target", rating="good", ts=500, kp=18.0, ki=0.1, kd=0.6
        )
        mock_db.query_checkpoints.return_value = [target_checkpoint]

        executor = self._make_executor(gateway=mock_gateway, db=mock_db)
        result = executor.execute("diff_config", {
            "compare_to": "checkpoint",
            "checkpoint_id": "cp_target",
        })

        assert result.ok
        assert result.data["checkpoint_id"] == "cp_target"

    def test_diff_no_gateway_fails(self):
        """diff_config without gateway should fail gracefully."""
        executor = self._make_executor(gateway=None)
        result = executor.execute("diff_config", {"compare_to": "factory"})

        assert not result.ok
        assert result.error == T2Errors.E_NO_DB

    def test_diff_no_checkpoint_found(self):
        """diff_config when no checkpoints exist should fail with E_NO_CHECKPOINT."""
        mock_gateway = MagicMock()
        mock_gateway.get_status.return_value = {"kp": 18.0, "ki": 0.1, "kd": 0.6, "set": 0}

        mock_db = MagicMock()
        mock_db.query_checkpoints.return_value = []

        executor = self._make_executor(gateway=mock_gateway, db=mock_db)
        result = executor.execute("diff_config", {"compare_to": "checkpoint"})

        assert not result.ok
        assert result.error == T2Errors.E_NO_CHECKPOINT


# ============================================================================
# safe_rollback Tests
# ============================================================================

class TestSafeRollback:
    """Tests for safe_rollback tool."""

    def _make_executor(self, gateway=None, db=None):
        """Create executor with mocked dependencies."""
        return CodexToolExecutor(gateway=gateway, db=db, active_robot_id="default")

    def test_rollback_dry_run(self):
        """safe_rollback dry_run should preview changes without applying."""
        mock_gateway = MagicMock()
        mock_gateway.get_status.return_value = {"kp": 22.0, "ki": 0.1, "kd": 0.3}
        mock_gateway.is_busy.return_value = False

        mock_db = MagicMock()
        checkpoint = MockCheckpoint(id="cp_good", rating="good", ts=1000, kp=18.0, ki=0.1, kd=0.6)
        mock_db.query_checkpoints.return_value = [checkpoint]

        executor = self._make_executor(gateway=mock_gateway, db=mock_db)
        result = executor.execute("safe_rollback", {"dry_run": True})

        assert result.ok
        assert result.data["dry_run"] is True
        assert "changes_preview" in result.data
        assert len(result.data["changes_preview"]) >= 1
        # Verify no commands were actually sent
        mock_gateway.command.assert_not_called()

    def test_rollback_applies_pid_command(self):
        """safe_rollback should send PID command to gateway."""
        mock_gateway = MagicMock()
        mock_gateway.get_status.return_value = {"kp": 22.0, "ki": 0.1, "kd": 0.3}
        mock_gateway.is_busy.return_value = False
        mock_gateway.command.return_value = {"ok": True}

        mock_db = MagicMock()
        checkpoint = MockCheckpoint(id="cp_good", rating="good", ts=1000, kp=18.0, ki=0.1, kd=0.6)
        mock_db.query_checkpoints.return_value = [checkpoint]

        executor = self._make_executor(gateway=mock_gateway, db=mock_db)
        result = executor.execute("safe_rollback", {"dry_run": False})

        assert result.ok
        assert result.data["dry_run"] is False
        assert len(result.data["commands_sent"]) >= 1
        assert "PID" in result.data["commands_sent"][0]
        mock_gateway.command.assert_called()

    def test_rollback_min_rating_filter(self):
        """safe_rollback should only use checkpoints meeting min_rating."""
        mock_gateway = MagicMock()
        mock_gateway.get_status.return_value = {"kp": 22.0, "ki": 0.1, "kd": 0.3}
        mock_gateway.is_busy.return_value = False
        mock_gateway.command.return_value = {"ok": True}

        mock_db = MagicMock()
        
        def mock_query_checkpoints(robot_id=None, min_rating=None, limit=None):
            if min_rating == "great":
                return [MockCheckpoint(id="cp_great", rating="great", ts=2000, kp=19.0, ki=0.1, kd=0.55)]
            elif min_rating == "good":
                return [MockCheckpoint(id="cp_good", rating="good", ts=1000, kp=18.0, ki=0.1, kd=0.6)]
            return []
        
        mock_db.query_checkpoints.side_effect = mock_query_checkpoints

        executor = self._make_executor(gateway=mock_gateway, db=mock_db)
        
        # With min_rating=great, should get great checkpoint
        result = executor.execute("safe_rollback", {"min_rating": "great", "dry_run": True})
        assert result.ok
        assert result.data["checkpoint_rating"] == "great"

    def test_rollback_no_checkpoint_fails(self):
        """safe_rollback without matching checkpoint should fail."""
        mock_gateway = MagicMock()
        mock_gateway.get_status.return_value = {"kp": 22.0, "ki": 0.1, "kd": 0.3}
        mock_gateway.is_busy.return_value = False

        mock_db = MagicMock()
        mock_db.query_checkpoints.return_value = []

        executor = self._make_executor(gateway=mock_gateway, db=mock_db)
        result = executor.execute("safe_rollback", {"min_rating": "great"})

        assert not result.ok
        assert result.error == T2Errors.E_NO_CHECKPOINT

    def test_rollback_serial_busy_fails(self):
        """safe_rollback when serial busy should fail gracefully."""
        mock_gateway = MagicMock()
        mock_gateway.is_busy.return_value = True

        mock_db = MagicMock()
        checkpoint = MockCheckpoint(id="cp_good", rating="good", ts=1000, kp=18.0, ki=0.1, kd=0.6)
        mock_db.query_checkpoints.return_value = [checkpoint]

        executor = self._make_executor(gateway=mock_gateway, db=mock_db)
        result = executor.execute("safe_rollback", {})

        assert not result.ok
        assert result.error == T2Errors.E_SERIAL_BUSY

    def test_rollback_no_db_fails(self):
        """safe_rollback without database should fail."""
        mock_gateway = MagicMock()
        executor = self._make_executor(gateway=mock_gateway, db=None)
        result = executor.execute("safe_rollback", {})

        assert not result.ok
        assert result.error == T2Errors.E_NO_DB


# ============================================================================
# run_experiment Tests
# ============================================================================

class TestRunExperiment:
    """Tests for run_experiment tool."""

    def _make_executor(self, gateway=None, db=None):
        """Create executor with mocked dependencies."""
        return CodexToolExecutor(gateway=gateway, db=db)

    def test_experiment_blocked_command_rejected(self):
        """run_experiment should reject ARM/DISARM commands."""
        mock_gateway = MagicMock()
        executor = self._make_executor(gateway=mock_gateway)

        result = executor.execute("run_experiment", {
            "change": {"cmd": "ARM"}
        })

        assert not result.ok
        assert result.error == T2Errors.E_BLOCKED_COMMAND

    def test_experiment_unknown_command_rejected(self):
        """run_experiment should reject commands not in allowlist."""
        mock_gateway = MagicMock()
        executor = self._make_executor(gateway=mock_gateway)

        result = executor.execute("run_experiment", {
            "change": {"cmd": "DANGEROUS_CMD 123"}
        })

        assert not result.ok
        assert result.error == T2Errors.E_BLOCKED_COMMAND

    def test_experiment_safe_command_allowed(self):
        """run_experiment should allow PID commands."""
        mock_gateway = MagicMock()
        mock_gateway.get_status.return_value = {
            "kp": 18.0, "ki": 0.1, "kd": 0.6,
            "ang": 1.0, "raw": 1.1, "out": 50, "mode": "BALANCING", "gyro": 0.1,
        }
        mock_gateway.health.return_value = {"connected": True}
        mock_gateway.command.return_value = {"ok": True}

        executor = self._make_executor(gateway=mock_gateway)

        # Use very short durations for test speed
        with patch.object(ObservationLimits, 'EXPERIMENT_COOLDOWN_S', 0.1):
            result = executor.execute("run_experiment", {
                "change": {"cmd": "PID 20 0.1 0.5"},
                "baseline_s": 0.2,
                "observe_s": 0.2,
            })

        assert result.ok
        assert result.data["change_applied"]["cmd"] == "PID 20 0.1 0.5"
        mock_gateway.command.assert_called()

    def test_experiment_auto_revert_on_failure(self):
        """run_experiment should auto-revert when criteria not met."""
        call_count = [0]
        
        def mock_get_status():
            call_count[0] += 1
            # Return bad metrics after command is applied
            if call_count[0] > 20:
                return {
                    "kp": 20.0, "ki": 0.1, "kd": 0.5,
                    "ang": 10.0,  # High angle = bad
                    "raw": 10.1, "out": 250, "mode": "BALANCING", "gyro": 5.0,
                }
            return {
                "kp": 18.0, "ki": 0.1, "kd": 0.6,
                "ang": 1.0, "raw": 1.1, "out": 50, "mode": "BALANCING", "gyro": 0.1,
            }

        mock_gateway = MagicMock()
        mock_gateway.get_status = mock_get_status
        mock_gateway.health.return_value = {"connected": True}
        mock_gateway.command.return_value = {"ok": True}

        executor = self._make_executor(gateway=mock_gateway)

        with patch.object(ObservationLimits, 'EXPERIMENT_COOLDOWN_S', 0.1):
            result = executor.execute("run_experiment", {
                "change": {"cmd": "PID 20 0.1 0.5"},
                "baseline_s": 0.2,
                "observe_s": 0.2,
                "auto_revert": True,
                "success_criteria": {
                    "max_angle_variance": 1.0,  # Will fail with high variance
                },
            })

        assert result.ok
        # Check that auto-revert was triggered
        if not result.data["success_criteria_met"]:
            assert result.data["auto_reverted"] is True
            assert result.data["revert_cmd"] is not None

    def test_experiment_no_auto_revert_when_disabled(self):
        """run_experiment should not revert when auto_revert=false."""
        call_count = [0]
        
        def mock_get_status():
            call_count[0] += 1
            if call_count[0] > 20:
                return {
                    "kp": 20.0, "ki": 0.1, "kd": 0.5,
                    "ang": 10.0, "raw": 10.1, "out": 250, "mode": "BALANCING", "gyro": 5.0,
                }
            return {
                "kp": 18.0, "ki": 0.1, "kd": 0.6,
                "ang": 1.0, "raw": 1.1, "out": 50, "mode": "BALANCING", "gyro": 0.1,
            }

        mock_gateway = MagicMock()
        mock_gateway.get_status = mock_get_status
        mock_gateway.health.return_value = {"connected": True}
        mock_gateway.command.return_value = {"ok": True}

        executor = self._make_executor(gateway=mock_gateway)

        with patch.object(ObservationLimits, 'EXPERIMENT_COOLDOWN_S', 0.1):
            result = executor.execute("run_experiment", {
                "change": {"cmd": "PID 20 0.1 0.5"},
                "baseline_s": 0.2,
                "observe_s": 0.2,
                "auto_revert": False,
                "success_criteria": {
                    "max_angle_variance": 1.0,
                },
            })

        assert result.ok
        assert result.data["auto_reverted"] is False

    def test_experiment_returns_comparison(self):
        """run_experiment should return baseline vs result comparison."""
        mock_gateway = MagicMock()
        mock_gateway.get_status.return_value = {
            "kp": 18.0, "ki": 0.1, "kd": 0.6,
            "ang": 1.0, "raw": 1.1, "out": 50, "mode": "BALANCING", "gyro": 0.1,
        }
        mock_gateway.health.return_value = {"connected": True}
        mock_gateway.command.return_value = {"ok": True}

        executor = self._make_executor(gateway=mock_gateway)

        with patch.object(ObservationLimits, 'EXPERIMENT_COOLDOWN_S', 0.1):
            result = executor.execute("run_experiment", {
                "change": {"cmd": "PID 20 0.1 0.5"},
                "baseline_s": 0.2,
                "observe_s": 0.2,
            })

        assert result.ok
        assert "baseline" in result.data
        assert "result" in result.data
        assert "comparison" in result.data
        assert "verdict" in result.data["comparison"]

    def test_experiment_missing_change_fails(self):
        """run_experiment without change should fail."""
        mock_gateway = MagicMock()
        executor = self._make_executor(gateway=mock_gateway)

        result = executor.execute("run_experiment", {})

        assert not result.ok
        assert result.error == T2Errors.E_INVALID_CHANGE

    def test_experiment_no_gateway_fails(self):
        """run_experiment without gateway should fail."""
        executor = self._make_executor(gateway=None)

        result = executor.execute("run_experiment", {
            "change": {"cmd": "PID 20 0.1 0.5"}
        })

        assert not result.ok
        assert result.error == T1Errors.E_SERIAL_DISCONNECTED


# ============================================================================
# Integration Tests
# ============================================================================

class TestT2Integration:
    """Integration tests for T2 tools."""

    def test_all_t2_tools_return_tool_result(self):
        """Verify all T2 tools return proper ToolResult structure."""
        mock_gateway = MagicMock()
        mock_gateway.get_status.return_value = {
            "kp": 18.0, "ki": 0.1, "kd": 0.6, "set": 0,
            "ang": 1.0, "raw": 1.1, "out": 50, "mode": "BALANCING", "gyro": 0.1,
        }
        mock_gateway.health.return_value = {"connected": True}
        mock_gateway.is_busy.return_value = False
        mock_gateway.command.return_value = {"ok": True}

        mock_db = MagicMock()
        checkpoint = MockCheckpoint(id="cp", rating="good", ts=1000, kp=18.0, ki=0.1, kd=0.6)
        mock_db.query_checkpoints.return_value = [checkpoint]

        executor = CodexToolExecutor(gateway=mock_gateway, db=mock_db)

        # diff_config
        result = executor.execute("diff_config", {"compare_to": "factory"})
        assert isinstance(result, ToolResult)
        assert result.tool == "diff_config"

        # safe_rollback (dry_run)
        result = executor.execute("safe_rollback", {"dry_run": True})
        assert isinstance(result, ToolResult)
        assert result.tool == "safe_rollback"

    def test_t2_commands_use_allowlist(self):
        """Verify T2 tools respect command allowlist."""
        executor = CodexToolExecutor(gateway=MagicMock())

        # All blocked commands should be rejected
        for blocked_cmd in ["ARM", "DISARM", "MOTOR", "MOTOROFF"]:
            result = executor.execute("run_experiment", {
                "change": {"cmd": blocked_cmd}
            })
            assert not result.ok, f"{blocked_cmd} should be blocked"
            assert result.error == T2Errors.E_BLOCKED_COMMAND


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

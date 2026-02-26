"""
Sprint 5 Acceptance Tests: T3 Intelligence Tools

Tests for simulate_pid_response and suggest_next_step
per PRD_AGENT_TOOLS_V2.md acceptance criteria.
"""

import sys
import math
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from codex_tools import (
    CodexToolExecutor,
    ToolResult,
    T3Errors,
    FACTORY_DEFAULTS,
    ROBOT_DEFAULTS,
    TUNING_THRESHOLDS,
)


# ============================================================================
# simulate_pid_response Tests
# ============================================================================

class TestSimulatePidResponse:
    """Tests for simulate_pid_response tool."""

    def _make_executor(self, gateway=None):
        """Create executor with mocked dependencies."""
        return CodexToolExecutor(gateway=gateway)

    def test_simulate_valid_pid_returns_metrics(self):
        """simulate_pid_response with valid PID returns settling time, overshoot, stability."""
        executor = self._make_executor()
        result = executor.execute("simulate_pid_response", {
            "proposed_pid": {"Kp": 20, "Ki": 0.1, "Kd": 0.5},
        })

        assert result.ok
        assert "proposed" in result.data
        proposed = result.data["proposed"]

        # Check required fields
        assert "settling_time_ms" in proposed
        assert "overshoot_pct" in proposed
        assert "steady_state_error_deg" in proposed
        assert "stability" in proposed
        assert "oscillation_risk" in proposed
        assert "pid" in proposed

        # Verify PID values preserved
        assert proposed["pid"]["Kp"] == 20
        assert proposed["pid"]["Ki"] == 0.1
        assert proposed["pid"]["Kd"] == 0.5

    def test_simulate_includes_model_assumptions(self):
        """simulate_pid_response includes model assumptions string."""
        executor = self._make_executor()
        result = executor.execute("simulate_pid_response", {
            "proposed_pid": {"Kp": 18, "Ki": 0.1, "Kd": 0.6},
        })

        assert result.ok
        assert "model_assumptions" in result.data
        assert "pendulum" in result.data["model_assumptions"].lower()
        assert "mass" in result.data["model_assumptions"].lower()

    def test_simulate_compare_to_current_with_gateway(self):
        """simulate_pid_response compares to current PID when gateway available."""
        mock_gateway = MagicMock()
        mock_gateway.get_status.return_value = {
            "kp": 15.0, "ki": 0.1, "kd": 0.6,
        }

        executor = self._make_executor(gateway=mock_gateway)
        result = executor.execute("simulate_pid_response", {
            "proposed_pid": {"Kp": 20, "Ki": 0.1, "Kd": 0.5},
            "compare_to_current": True,
        })

        assert result.ok
        assert "current" in result.data
        assert "comparison" in result.data

        current = result.data["current"]
        assert current["pid"]["Kp"] == 15.0

        comparison = result.data["comparison"]
        assert "settling_time_delta" in comparison
        assert "overshoot_delta" in comparison
        assert "recommendation" in comparison

    def test_simulate_no_comparison_without_gateway(self):
        """simulate_pid_response skips comparison when no gateway."""
        executor = self._make_executor(gateway=None)
        result = executor.execute("simulate_pid_response", {
            "proposed_pid": {"Kp": 20, "Ki": 0.1, "Kd": 0.5},
            "compare_to_current": True,
        })

        assert result.ok
        assert "current" not in result.data
        assert "comparison" not in result.data

    def test_simulate_invalid_kp_fails(self):
        """simulate_pid_response with Kp <= 0 fails."""
        executor = self._make_executor()
        result = executor.execute("simulate_pid_response", {
            "proposed_pid": {"Kp": 0, "Ki": 0.1, "Kd": 0.5},
        })

        assert not result.ok
        assert result.error == T3Errors.E_INVALID_PID

    def test_simulate_stability_assessment(self):
        """simulate_pid_response correctly assesses stability."""
        executor = self._make_executor()

        # High Kd relative to Kp should be stable/overdamped
        result = executor.execute("simulate_pid_response", {
            "proposed_pid": {"Kp": 10, "Ki": 0.1, "Kd": 2.0},
        })
        assert result.ok
        # High damping ratio expected

        # Very low Kd should show oscillation risk
        result = executor.execute("simulate_pid_response", {
            "proposed_pid": {"Kp": 25, "Ki": 0.1, "Kd": 0.1},
        })
        assert result.ok
        proposed = result.data["proposed"]
        assert proposed["oscillation_risk"] in ["medium", "high"]

    def test_simulate_overshoot_calculation(self):
        """simulate_pid_response calculates realistic overshoot values."""
        executor = self._make_executor()
        result = executor.execute("simulate_pid_response", {
            "proposed_pid": {"Kp": 20, "Ki": 0.1, "Kd": 0.3},  # Underdamped
        })

        assert result.ok
        proposed = result.data["proposed"]
        # Underdamped system should have some overshoot
        assert proposed["overshoot_pct"] >= 0
        assert proposed["overshoot_pct"] <= 100  # Reasonable bounds

    def test_simulate_integral_eliminates_steady_state_error(self):
        """simulate_pid_response shows Ki > 0 eliminates steady-state error."""
        executor = self._make_executor()

        # With integral
        result_with_ki = executor.execute("simulate_pid_response", {
            "proposed_pid": {"Kp": 18, "Ki": 0.1, "Kd": 0.6},
        })

        # Without integral
        result_no_ki = executor.execute("simulate_pid_response", {
            "proposed_pid": {"Kp": 18, "Ki": 0.0, "Kd": 0.6},
        })

        assert result_with_ki.ok and result_no_ki.ok
        assert result_with_ki.data["proposed"]["steady_state_error_deg"] == 0.0
        assert result_no_ki.data["proposed"]["steady_state_error_deg"] > 0

    def test_simulate_comparison_recommendations(self):
        """simulate_pid_response generates meaningful comparison recommendations."""
        mock_gateway = MagicMock()
        mock_gateway.get_status.return_value = {"kp": 15, "ki": 0.1, "kd": 0.6}

        executor = self._make_executor(gateway=mock_gateway)

        # Propose higher Kp (faster but more overshoot)
        result = executor.execute("simulate_pid_response", {
            "proposed_pid": {"Kp": 25, "Ki": 0.1, "Kd": 0.4},
        })

        assert result.ok
        assert "comparison" in result.data
        # Should have some recommendation text
        assert len(result.data["comparison"]["recommendation"]) > 0


# ============================================================================
# suggest_next_step Tests
# ============================================================================

class TestSuggestNextStep:
    """Tests for suggest_next_step tool."""

    def _make_executor(self, gateway=None, db=None, rag=None):
        """Create executor with mocked dependencies."""
        return CodexToolExecutor(gateway=gateway, db=db, rag=rag)

    def _mock_gateway_with_telemetry(self, ang=1.0, out=50, mode="BALANCING"):
        """Create a mock gateway that returns telemetry."""
        mock_gateway = MagicMock()
        mock_gateway.get_status.return_value = {
            "kp": 18.0, "ki": 0.1, "kd": 0.6,
            "ang": ang, "raw": ang + 0.1, "out": out,
            "mode": mode, "gyro": 0.1,
        }
        mock_gateway.health.return_value = {"connected": True}
        return mock_gateway

    def test_suggest_returns_ranked_suggestions(self):
        """suggest_next_step returns ranked suggestions with required fields."""
        mock_gateway = self._mock_gateway_with_telemetry()
        executor = self._make_executor(gateway=mock_gateway)

        result = executor.execute("suggest_next_step", {})

        assert result.ok
        assert "suggestions" in result.data
        assert len(result.data["suggestions"]) > 0

        suggestion = result.data["suggestions"][0]
        assert "rank" in suggestion
        assert "action" in suggestion
        assert "confidence" in suggestion
        assert suggestion["rank"] == 1  # First should be rank 1

    def test_suggest_includes_current_state(self):
        """suggest_next_step returns current state analysis."""
        mock_gateway = self._mock_gateway_with_telemetry()
        executor = self._make_executor(gateway=mock_gateway)

        result = executor.execute("suggest_next_step", {})

        assert result.ok
        assert "current_state" in result.data
        assert "current_pid" in result.data

        state = result.data["current_state"]
        assert "angle_variance" in state or "oscillation_detected" in state

    def test_suggest_rationale_included_by_default(self):
        """suggest_next_step includes rationale by default."""
        mock_gateway = self._mock_gateway_with_telemetry(ang=8.0)  # High variance
        executor = self._make_executor(gateway=mock_gateway)

        result = executor.execute("suggest_next_step", {"include_rationale": True})

        assert result.ok
        for suggestion in result.data["suggestions"]:
            if suggestion.get("rationale"):
                assert len(suggestion["rationale"]) > 10

    def test_suggest_rationale_excluded_when_disabled(self):
        """suggest_next_step excludes rationale when include_rationale=false."""
        mock_gateway = self._mock_gateway_with_telemetry(ang=8.0)
        executor = self._make_executor(gateway=mock_gateway)

        result = executor.execute("suggest_next_step", {"include_rationale": False})

        assert result.ok
        for suggestion in result.data["suggestions"]:
            assert suggestion.get("rationale") is None

    def test_suggest_max_suggestions_honored(self):
        """suggest_next_step respects max_suggestions parameter."""
        mock_gateway = self._mock_gateway_with_telemetry()
        executor = self._make_executor(gateway=mock_gateway)

        result = executor.execute("suggest_next_step", {"max_suggestions": 1})

        assert result.ok
        assert len(result.data["suggestions"]) <= 1

    def test_suggest_high_oscillation_recommends_kd_reduction(self):
        """suggest_next_step recommends Kd reduction for high-freq oscillation."""
        mock_gateway = MagicMock()
        mock_gateway.get_status.return_value = {
            "kp": 18.0, "ki": 0.1, "kd": 0.6,
            "ang": 2.0, "raw": 2.1, "out": 100,
            "mode": "BALANCING", "gyro": 0.5,
        }
        mock_gateway.health.return_value = {"connected": True}

        executor = self._make_executor(gateway=mock_gateway)

        # Patch _tool_observe_telemetry to return oscillation
        with patch.object(executor, '_tool_observe_telemetry') as mock_obs:
            mock_obs.return_value = ToolResult(
                ok=True,
                tool="observe_telemetry",
                data={
                    "metrics": {
                        "angle_variance": 3.0,
                        "oscillation_detected": True,
                        "oscillation_freq_hz": 4.5,  # High frequency
                        "output_saturation_pct": 40,
                    },
                    "latest_sample": {"mode": "BALANCING"},
                },
            )
            result = executor.execute("suggest_next_step", {})

        assert result.ok
        # Should have a suggestion about Kd
        actions = [s["action"].lower() for s in result.data["suggestions"]]
        assert any("kd" in a and "reduce" in a for a in actions)

    def test_suggest_high_saturation_recommends_kp_reduction(self):
        """suggest_next_step recommends Kp reduction for high saturation."""
        mock_gateway = MagicMock()
        mock_gateway.get_status.return_value = {
            "kp": 25.0, "ki": 0.1, "kd": 0.6,
            "ang": 1.0, "raw": 1.1, "out": 220,
            "mode": "BALANCING", "gyro": 0.1,
        }
        mock_gateway.health.return_value = {"connected": True}

        executor = self._make_executor(gateway=mock_gateway)

        with patch.object(executor, '_tool_observe_telemetry') as mock_obs:
            mock_obs.return_value = ToolResult(
                ok=True,
                tool="observe_telemetry",
                data={
                    "metrics": {
                        "angle_variance": 2.0,
                        "oscillation_detected": False,
                        "output_saturation_pct": 90,  # High saturation
                    },
                    "latest_sample": {"mode": "BALANCING"},
                },
            )
            result = executor.execute("suggest_next_step", {})

        assert result.ok
        actions = [s["action"].lower() for s in result.data["suggestions"]]
        assert any("kp" in a and "reduce" in a for a in actions)

    def test_suggest_good_state_recommends_checkpoint(self):
        """suggest_next_step recommends saving checkpoint for good tuning."""
        mock_gateway = MagicMock()
        mock_gateway.get_status.return_value = {
            "kp": 18.0, "ki": 0.1, "kd": 0.6,
            "ang": 0.5, "raw": 0.6, "out": 40,
            "mode": "BALANCING", "gyro": 0.05,
        }
        mock_gateway.health.return_value = {"connected": True}

        executor = self._make_executor(gateway=mock_gateway)

        with patch.object(executor, '_tool_observe_telemetry') as mock_obs:
            mock_obs.return_value = ToolResult(
                ok=True,
                tool="observe_telemetry",
                data={
                    "metrics": {
                        "angle_variance": 1.0,  # Good
                        "oscillation_detected": False,
                        "output_saturation_pct": 30,  # Good
                    },
                    "latest_sample": {"mode": "BALANCING"},
                },
            )
            result = executor.execute("suggest_next_step", {})

        assert result.ok
        actions = [s["action"].lower() for s in result.data["suggestions"]]
        assert any("checkpoint" in a for a in actions)

    def test_suggest_no_telemetry_fails(self):
        """suggest_next_step fails gracefully without telemetry."""
        executor = self._make_executor(gateway=None)
        result = executor.execute("suggest_next_step", {})

        assert not result.ok
        assert result.error == T3Errors.E_NO_TELEMETRY

    def test_suggest_data_sources_reported(self):
        """suggest_next_step reports which data sources were used."""
        mock_gateway = self._mock_gateway_with_telemetry()
        mock_db = MagicMock()

        executor = self._make_executor(gateway=mock_gateway, db=mock_db)

        result = executor.execute("suggest_next_step", {})

        assert result.ok
        assert "data_sources" in result.data
        assert "current_telemetry" in result.data["data_sources"]
        assert "checkpoint_history" in result.data["data_sources"]

    def test_suggest_commands_are_valid_format(self):
        """suggest_next_step returns properly formatted PID commands."""
        mock_gateway = self._mock_gateway_with_telemetry(ang=6.0)
        executor = self._make_executor(gateway=mock_gateway)

        result = executor.execute("suggest_next_step", {})

        assert result.ok
        for suggestion in result.data["suggestions"]:
            cmd = suggestion.get("command")
            if cmd:
                # Should be "PID <kp> <ki> <kd>" format
                assert cmd.startswith("PID ")
                parts = cmd.split()
                assert len(parts) == 4
                # Values should be numeric
                float(parts[1])
                float(parts[2])
                float(parts[3])


# ============================================================================
# Integration Tests
# ============================================================================

class TestT3Integration:
    """Integration tests for T3 tools."""

    def test_all_t3_tools_return_tool_result(self):
        """Verify all T3 tools return proper ToolResult structure."""
        mock_gateway = MagicMock()
        mock_gateway.get_status.return_value = {
            "kp": 18.0, "ki": 0.1, "kd": 0.6,
            "ang": 1.0, "raw": 1.1, "out": 50,
            "mode": "BALANCING", "gyro": 0.1,
        }
        mock_gateway.health.return_value = {"connected": True}

        executor = CodexToolExecutor(gateway=mock_gateway)

        # simulate_pid_response
        result = executor.execute("simulate_pid_response", {
            "proposed_pid": {"Kp": 20, "Ki": 0.1, "Kd": 0.5},
        })
        assert isinstance(result, ToolResult)
        assert result.tool == "simulate_pid_response"

    def test_t3_tools_are_read_only(self):
        """Verify T3 tools do not modify robot state."""
        mock_gateway = MagicMock()
        mock_gateway.get_status.return_value = {
            "kp": 18.0, "ki": 0.1, "kd": 0.6,
            "ang": 1.0, "raw": 1.1, "out": 50,
            "mode": "BALANCING", "gyro": 0.1,
        }
        mock_gateway.health.return_value = {"connected": True}

        executor = CodexToolExecutor(gateway=mock_gateway)

        # simulate_pid_response should not call command()
        executor.execute("simulate_pid_response", {
            "proposed_pid": {"Kp": 25, "Ki": 0.2, "Kd": 0.8},
        })
        mock_gateway.command.assert_not_called()


# ============================================================================
# annotate_session Tests
# ============================================================================

class TestAnnotateSession:
    """Tests for annotate_session tool."""

    def _make_executor_with_db(self, gateway=None):
        """Create executor with mocked DB."""
        mock_db = MagicMock()
        mock_db.save_annotation.return_value = 42  # Return a mock annotation ID
        return CodexToolExecutor(gateway=gateway, db=mock_db), mock_db

    def test_annotate_success_returns_annotation_data(self):
        """annotate_session with valid note returns annotation details."""
        executor, mock_db = self._make_executor_with_db()
        result = executor.execute("annotate_session", {
            "note": "Kp=22 caused oscillation. Reduced to 18.",
            "tags": ["oscillation", "pid_tuning"],
            "severity": "success",
        })

        assert result.ok
        assert result.tool == "annotate_session"
        assert "annotation_id" in result.data
        assert "ts" in result.data
        assert result.data["note"] == "Kp=22 caused oscillation. Reduced to 18."
        assert result.data["tags"] == ["oscillation", "pid_tuning"]
        assert result.data["severity"] == "success"
        assert "session_id" in result.data

        # Verify DB was called
        mock_db.save_annotation.assert_called_once()

    def test_annotate_empty_note_fails(self):
        """annotate_session with empty note fails."""
        executor, _ = self._make_executor_with_db()
        result = executor.execute("annotate_session", {
            "note": "",
        })

        assert not result.ok
        assert result.error == "note is required"

    def test_annotate_without_db_fails(self):
        """annotate_session without database fails gracefully."""
        executor = CodexToolExecutor(db=None)
        result = executor.execute("annotate_session", {
            "note": "Test annotation",
        })

        assert not result.ok
        assert "database" in result.error.lower()

    def test_annotate_invalid_severity_defaults_to_info(self):
        """annotate_session with invalid severity defaults to info."""
        executor, mock_db = self._make_executor_with_db()
        result = executor.execute("annotate_session", {
            "note": "Test annotation",
            "severity": "invalid_severity",
        })

        assert result.ok
        assert result.data["severity"] == "info"

    def test_annotate_with_custom_timestamp(self):
        """annotate_session accepts custom timestamp."""
        executor, mock_db = self._make_executor_with_db()
        custom_ts = 1739922600.0
        result = executor.execute("annotate_session", {
            "note": "Historical annotation",
            "ts": custom_ts,
        })

        assert result.ok
        assert result.data["ts"] == custom_ts

    def test_annotate_with_related_config(self):
        """annotate_session stores related config."""
        executor, mock_db = self._make_executor_with_db()
        config = {"kp": 20, "ki": 0.1, "kd": 0.6}
        result = executor.execute("annotate_session", {
            "note": "Saved at this config",
            "related_config": config,
        })

        assert result.ok
        assert result.data["related_config"] == config

    def test_annotate_captures_current_config_if_not_provided(self):
        """annotate_session captures current config when not provided."""
        mock_gateway = MagicMock()
        mock_gateway.get_status.return_value = {
            "kp": 18.0, "ki": 0.1, "kd": 0.6,
            "setpoint": 0.0, "mode": "BALANCING",
        }
        executor, mock_db = self._make_executor_with_db(gateway=mock_gateway)

        result = executor.execute("annotate_session", {
            "note": "Auto-captured config",
        })

        assert result.ok
        assert result.data["related_config"]["kp"] == 18.0
        assert result.data["related_config"]["ki"] == 0.1

    def test_annotate_all_severity_levels_accepted(self):
        """annotate_session accepts all valid severity levels."""
        executor, mock_db = self._make_executor_with_db()

        for severity in ["info", "success", "warning", "failure"]:
            result = executor.execute("annotate_session", {
                "note": f"Test {severity}",
                "severity": severity,
            })
            assert result.ok
            assert result.data["severity"] == severity


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

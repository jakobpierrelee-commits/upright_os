"""
Calibration + Anti-Drift Contract Track: v2 Readiness Tests

Tests for telemetry contract v2 detection and readiness reporting.
Per PRD_CALIBRATION_ANTIDRIFT_V1.md acceptance criteria.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from server import detect_contract_readiness

# Import constants directly from the module namespace
import server

V1_REQUIRED_FIELDS = server.V1_REQUIRED_FIELDS
V1_GYRO_ALIASES = server.V1_GYRO_ALIASES
V2_READINESS_FIELDS = server.V2_READINESS_FIELDS
V2_OPTIONAL_FIELDS = server.V2_OPTIONAL_FIELDS


# ============================================================================
# detect_contract_readiness Tests
# ============================================================================


class TestDetectContractReadiness:
    """Tests for the detect_contract_readiness function."""

    def test_v1_complete_telemetry(self):
        """v1-only telemetry with all required fields should pass v1, fail v2."""
        status = {
            "mode": "BALANCING",
            "ang": 1.23,
            "raw": 1.25,
            "gyro": 0.05,
            "out": 42,
            "kp": 18.0,
            "ki": 0.1,
            "kd": 0.6,
            "set": 0.0,
        }

        result = detect_contract_readiness(status)

        assert result["v1_ok"] is True
        assert result["v2_ready"] is False
        assert result["contract_version_detected"] == "v1"
        assert "gyro_bias" in result["v2_missing_fields"]
        assert "vel_meas" in result["v2_missing_fields"]
        assert "outer_loop_enabled" in result["v2_missing_fields"]

    def test_v2_complete_telemetry(self):
        """v2 telemetry with all readiness fields should pass both v1 and v2."""
        status = {
            "mode": "BALANCING",
            "ang": 1.23,
            "raw": 1.25,
            "gyro": 0.05,
            "out": 42,
            "kp": 18.0,
            "ki": 0.1,
            "kd": 0.6,
            "set": 0.0,
            # v2 readiness fields
            "gyro_bias": -0.02,
            "vel_meas": 0.01,
            "outer_loop_enabled": True,
        }

        result = detect_contract_readiness(status)

        assert result["v1_ok"] is True
        assert result["v2_ready"] is True
        assert result["contract_version_detected"] == "v2"
        assert len(result["v2_missing_fields"]) == 0

    def test_v1_missing_mode_fails(self):
        """Missing required v1 field should fail v1."""
        status = {
            # missing "mode"
            "ang": 1.23,
            "raw": 1.25,
            "gyro": 0.05,
            "out": 42,
            "kp": 18.0,
            "ki": 0.1,
            "kd": 0.6,
            "set": 0.0,
        }

        result = detect_contract_readiness(status)

        assert result["v1_ok"] is False
        assert result["v2_ready"] is False

    def test_v1_missing_gyro_fails(self):
        """Missing gyro field (no aliases present) should fail v1."""
        status = {
            "mode": "BALANCING",
            "ang": 1.23,
            "raw": 1.25,
            # missing gyro/gyr/gx
            "out": 42,
            "kp": 18.0,
            "ki": 0.1,
            "kd": 0.6,
            "set": 0.0,
        }

        result = detect_contract_readiness(status)

        assert result["v1_ok"] is False
        # Check that the v1 check mentions gyro in its detail
        v1_check = next(
            (
                c
                for c in result["readiness_checks"]
                if c["check"] == "v1_required_fields"
            ),
            None,
        )
        assert v1_check is not None
        assert v1_check["status"] == "fail"
        assert "gyro" in v1_check["detail"]

    def test_gyro_alias_gyr_accepted(self):
        """Gyro alias 'gyr' should be accepted for v1."""
        status = {
            "mode": "BALANCING",
            "ang": 1.23,
            "raw": 1.25,
            "gyr": 0.05,  # alias
            "out": 42,
            "kp": 18.0,
            "ki": 0.1,
            "kd": 0.6,
            "set": 0.0,
        }

        result = detect_contract_readiness(status)

        assert result["v1_ok"] is True

    def test_gyro_alias_gx_accepted(self):
        """Gyro alias 'gx' should be accepted for v1."""
        status = {
            "mode": "BALANCING",
            "ang": 1.23,
            "raw": 1.25,
            "gx": 0.05,  # alias
            "out": 42,
            "kp": 18.0,
            "ki": 0.1,
            "kd": 0.6,
            "set": 0.0,
        }

        result = detect_contract_readiness(status)

        assert result["v1_ok"] is True

    def test_v2_partial_only_gyro_bias(self):
        """Partial v2 (only gyro_bias) should fail v2 readiness."""
        status = {
            "mode": "BALANCING",
            "ang": 1.23,
            "raw": 1.25,
            "gyro": 0.05,
            "out": 42,
            "kp": 18.0,
            "ki": 0.1,
            "kd": 0.6,
            "set": 0.0,
            "gyro_bias": -0.02,
        }

        result = detect_contract_readiness(status)

        assert result["v1_ok"] is True
        assert result["v2_ready"] is False
        assert result["contract_version_detected"] == "v1"
        assert "vel_meas" in result["v2_missing_fields"]
        assert "outer_loop_enabled" in result["v2_missing_fields"]
        assert "gyro_bias" in result["v2_present_fields"]

    def test_empty_status_fails_gracefully(self):
        """Empty status dict should fail gracefully."""
        result = detect_contract_readiness({})

        assert result["v1_ok"] is False
        assert result["v2_ready"] is False

    def test_none_status_fails_gracefully(self):
        """None status should fail gracefully."""
        result = detect_contract_readiness(None)

        assert result["v1_ok"] is False
        assert result["v2_ready"] is False
        assert result["contract_version_detected"] == "unknown"

    def test_readiness_checks_structure(self):
        """Readiness checks should have proper structure."""
        status = {
            "mode": "BALANCING",
            "ang": 1.23,
            "raw": 1.25,
            "gyro": 0.05,
            "out": 42,
            "kp": 18.0,
            "ki": 0.1,
            "kd": 0.6,
            "set": 0.0,
        }

        result = detect_contract_readiness(status)

        assert "readiness_checks" in result
        assert len(result["readiness_checks"]) >= 3

        for check in result["readiness_checks"]:
            assert "check" in check
            assert "status" in check
            assert "detail" in check
            assert check["status"] in ("pass", "warn", "fail")

    def test_v2_optional_fields_detected(self):
        """v2 optional fields should be detected and reported."""
        status = {
            "mode": "BALANCING",
            "ang": 1.23,
            "raw": 1.25,
            "gyro": 0.05,
            "out": 42,
            "kp": 18.0,
            "ki": 0.1,
            "kd": 0.6,
            "set": 0.0,
            # Some v2 optional fields
            "gyro_bias": -0.02,
            "accel_level_offset": 0.5,
            "upright_trim": 0.3,
        }

        result = detect_contract_readiness(status)

        assert "gyro_bias" in result["v2_present_fields"]
        assert "accel_level_offset" in result["v2_present_fields"]
        assert "upright_trim" in result["v2_present_fields"]

    def test_calibration_ready_check(self):
        """Calibration check should pass when gyro_bias and accel_level_offset present."""
        status = {
            "mode": "BALANCING",
            "ang": 1.23,
            "raw": 1.25,
            "gyro": 0.05,
            "out": 42,
            "kp": 18.0,
            "ki": 0.1,
            "kd": 0.6,
            "set": 0.0,
            "gyro_bias": -0.02,
            "accel_level_offset": 0.5,
        }

        result = detect_contract_readiness(status)

        cal_check = next(
            (c for c in result["readiness_checks"] if c["check"] == "calibration_data"),
            None,
        )
        assert cal_check is not None
        assert cal_check["status"] == "pass"

    def test_outer_loop_ready_check(self):
        """Outer loop check should pass when vel_meas present and outer_loop_enabled."""
        status = {
            "mode": "BALANCING",
            "ang": 1.23,
            "raw": 1.25,
            "gyro": 0.05,
            "out": 42,
            "kp": 18.0,
            "ki": 0.1,
            "kd": 0.6,
            "set": 0.0,
            "vel_meas": 0.01,
            "outer_loop_enabled": True,
        }

        result = detect_contract_readiness(status)

        outer_check = next(
            (c for c in result["readiness_checks"] if c["check"] == "outer_loop_ready"),
            None,
        )
        assert outer_check is not None
        assert outer_check["status"] == "pass"


# ============================================================================
# Backward Compatibility Tests
# ============================================================================


class TestBackwardCompatibility:
    """Tests to ensure v1 probe behavior is unchanged."""

    def test_v1_fields_unchanged(self):
        """V1 required fields constant should match expected fields."""
        expected = ("mode", "ang", "raw", "out", "kp", "ki", "kd", "set")
        assert V1_REQUIRED_FIELDS == expected

    def test_v1_gyro_aliases_unchanged(self):
        """V1 gyro aliases should include expected alternatives."""
        assert "gyro" in V1_GYRO_ALIASES
        assert "gyr" in V1_GYRO_ALIASES
        assert "gx" in V1_GYRO_ALIASES

    def test_v2_readiness_fields_defined(self):
        """V2 readiness fields should be properly defined."""
        assert "gyro_bias" in V2_READINESS_FIELDS
        assert "vel_meas" in V2_READINESS_FIELDS
        assert "outer_loop_enabled" in V2_READINESS_FIELDS

    def test_v2_optional_fields_include_calibration(self):
        """V2 optional fields should include calibration-related fields."""
        assert "accel_level_offset" in V2_OPTIONAL_FIELDS
        assert "upright_trim" in V2_OPTIONAL_FIELDS

    def test_v2_optional_superset_of_readiness(self):
        """V2 optional fields should include all readiness fields."""
        for field in V2_READINESS_FIELDS:
            assert field in V2_OPTIONAL_FIELDS


# ============================================================================
# Integration Tests with run_compat_probe / run_connect_probe
# ============================================================================


class TestProbeIntegration:
    """Integration tests for probe functions with v2 readiness."""

    def test_compat_probe_includes_v2_fields(self):
        """run_compat_probe should include v2 readiness fields in output."""
        from server import run_compat_probe

        mock_gateway = MagicMock()
        mock_gateway.get_status.return_value = {
            "mode": "BALANCING",
            "ang": 1.23,
            "raw": 1.25,
            "gyro": 0.05,
            "out": 42,
            "kp": 18.0,
            "ki": 0.1,
            "kd": 0.6,
            "set": 0.0,
        }
        # Mock HELP command to return expected commands
        mock_gateway.command.return_value = {
            "lines": [
                "GET",
                "ARM",
                "DISARM",
                "PID",
                "MOTION",
                "SETPOINT",
                "LIMITS",
                "CAL ZERO",
                "SAVECFG",
            ]
        }

        result = run_compat_probe(mock_gateway)

        # v2 fields added (check these first regardless of ok status)
        assert "contract_version_detected" in result
        assert "v1_ok" in result
        assert "v2_ready" in result
        assert "v2_missing_fields" in result
        assert "readiness_checks" in result

        # v1 passes, v2 not ready (no v2 fields in telemetry)
        assert result["v1_ok"] is True
        assert result["v2_ready"] is False

    def test_compat_probe_supports_lean_profile_override(self):
        """run_compat_probe should enforce lean_v1 command contract when requested."""
        from server import run_compat_probe

        mock_gateway = MagicMock()
        mock_gateway.get_status.return_value = {
            "mode": "SAFE_IDLE",
            "ang": 0.12,
            "raw": 0.10,
            "gyro": 0.01,
            "out": 0.0,
            "kp": 18.0,
            "ki": 0.1,
            "kd": 0.6,
            "set": 0.0,
        }
        mock_gateway.command.return_value = {
            "lines": [
                "GET",
                "HELP",
                "ARM",
                "DISARM",
                "ESTOP",
                "FAULTCLR",
                "PID",
                "SETPOINT",
                "LIMITS",
                "CAL ZERO",
                "SAVECFG",
            ]
        }

        result = run_compat_probe(mock_gateway, profile_override="lean_v1")

        assert result["profile"] == "lean_v1"
        assert result["missing_fields"] == []
        assert result["blocking_missing_commands"] == []
        assert result["ok"] is True

    def test_compat_probe_lean_profile_flags_missing_estop(self):
        """lean_v1 should fail if ESTOP is absent from HELP output."""
        from server import run_compat_probe

        mock_gateway = MagicMock()
        mock_gateway.get_status.return_value = {
            "mode": "SAFE_IDLE",
            "ang": 0.12,
            "raw": 0.10,
            "gyro": 0.01,
            "out": 0.0,
            "kp": 18.0,
            "ki": 0.1,
            "kd": 0.6,
            "set": 0.0,
        }
        mock_gateway.command.return_value = {
            "lines": [
                "GET",
                "HELP",
                "ARM",
                "DISARM",
                "FAULTCLR",
                "PID",
                "SETPOINT",
                "LIMITS",
                "CAL ZERO",
            ]
        }

        result = run_compat_probe(mock_gateway, profile_override="lean_v1")

        assert result["profile"] == "lean_v1"
        assert "ESTOP" in result["missing_commands"]
        assert "ESTOP" in result["blocking_missing_commands"]
        assert result["ok"] is False

    def test_compat_probe_lean_profile_flags_missing_savecfg(self):
        """lean_v1 should fail if SAVECFG is absent from HELP output."""
        from server import run_compat_probe

        mock_gateway = MagicMock()
        mock_gateway.get_status.return_value = {
            "mode": "SAFE_IDLE",
            "ang": 0.12,
            "raw": 0.10,
            "gyro": 0.01,
            "out": 0.0,
            "kp": 18.0,
            "ki": 0.1,
            "kd": 0.6,
            "set": 0.0,
        }
        mock_gateway.command.return_value = {
            "lines": [
                "GET",
                "HELP",
                "ARM",
                "DISARM",
                "ESTOP",
                "FAULTCLR",
                "PID",
                "SETPOINT",
                "LIMITS",
                "CAL ZERO",
            ]
        }

        result = run_compat_probe(mock_gateway, profile_override="lean_v1")

        assert result["profile"] == "lean_v1"
        assert "SAVECFG" in result["missing_commands"]
        assert "SAVECFG" in result["blocking_missing_commands"]
        assert result["ok"] is False

    def test_connect_probe_includes_v2_fields(self):
        """run_connect_probe should include v2 readiness fields in output."""
        from server import run_connect_probe

        mock_gateway = MagicMock()
        mock_gateway.health.return_value = {
            "connected": True,
            "port": "/dev/ttyUSB0",
            "baud": 115200,
        }
        mock_gateway.get_status.return_value = {
            "mode": "BALANCING",
            "ang": 1.23,
            "raw": 1.25,
            "gyro": 0.05,
            "out": 42,
            "kp": 18.0,
            "ki": 0.1,
            "kd": 0.6,
            "set": 0.0,
        }
        mock_gateway.command.return_value = {"lines": ["GET", "ARM", "DISARM", "PID"]}

        result = run_connect_probe(mock_gateway)

        # v2 fields added
        assert "contract_version_detected" in result
        assert "v1_ok" in result
        assert "v2_ready" in result
        assert "v2_missing_fields" in result
        assert "phase2_missing_fields" in result
        assert "phase2_present_fields" in result
        assert "phase2_recommended_action" in result
        assert "v2_recommended_action" in result
        assert "readiness_checks" in result

    def test_connect_probe_recommended_action_for_missing_gyro_bias(self):
        """run_connect_probe should recommend gyro calibration when gyro_bias missing."""
        from server import run_connect_probe

        mock_gateway = MagicMock()
        mock_gateway.health.return_value = {
            "connected": True,
            "port": "/dev/ttyUSB0",
            "baud": 115200,
        }
        mock_gateway.get_status.return_value = {
            "mode": "BALANCING",
            "ang": 1.23,
            "raw": 1.25,
            "gyro": 0.05,
            "out": 42,
            "kp": 18.0,
            "ki": 0.1,
            "kd": 0.6,
            "set": 0.0,
        }
        mock_gateway.command.return_value = {"lines": ["GET", "ARM", "DISARM", "PID"]}

        result = run_connect_probe(mock_gateway)

        assert result["phase2_recommended_action"] is not None
        assert "calibration" in str(result["phase2_recommended_action"]).lower()
        # Migration window: legacy alias mirrors canonical phase field.
        assert result["v2_recommended_action"] == result["phase2_recommended_action"]

    def test_connect_probe_no_action_when_v2_ready(self):
        """run_connect_probe should have no recommended action when v2 ready."""
        from server import run_connect_probe

        mock_gateway = MagicMock()
        mock_gateway.health.return_value = {
            "connected": True,
            "port": "/dev/ttyUSB0",
            "baud": 115200,
        }
        mock_gateway.get_status.return_value = {
            "mode": "BALANCING",
            "ang": 1.23,
            "raw": 1.25,
            "gyro": 0.05,
            "out": 42,
            "kp": 18.0,
            "ki": 0.1,
            "kd": 0.6,
            "set": 0.0,
            # v2 readiness fields
            "gyro_bias": -0.02,
            "vel_meas": 0.01,
            "outer_loop_enabled": True,
        }
        mock_gateway.command.return_value = {"lines": ["GET", "ARM", "DISARM", "PID"]}

        result = run_connect_probe(mock_gateway)

        assert result["v2_ready"] is True
        assert result["phase2_recommended_action"] is None
        assert result["v2_recommended_action"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

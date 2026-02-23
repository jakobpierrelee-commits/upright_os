import pathlib
import sys

import pytest

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from clean_contracts import (
    validate_clean_preflight_response,
    validate_firmware_targets_response,
    validate_prearm_precheck_response,
)


def test_validate_firmware_targets_response_ok() -> None:
    payload = {
        "ok": True,
        "targets": {"version": 1, "families": [{"id": "arduino_avr"}], "boards": [{"id": "nano"}]},
    }
    validate_firmware_targets_response(payload)


def test_validate_firmware_targets_response_missing_key() -> None:
    payload = {"ok": True, "targets": {"version": 1, "families": []}}
    with pytest.raises(ValueError):
        validate_firmware_targets_response(payload)


def test_validate_prearm_precheck_response_ok() -> None:
    payload = {
        "ok": True,
        "prearm_check": {"ok": True, "checks": []},
        "prearm_safety": {"required": True, "passed": True},
        "action_gates": {"arm_prepare": {"ok": True, "reasons": []}},
    }
    validate_prearm_precheck_response(payload)


def test_validate_prearm_precheck_response_missing_checks() -> None:
    payload = {
        "ok": False,
        "prearm_check": {"ok": False},
        "prearm_safety": {"required": True, "passed": False},
        "action_gates": {},
    }
    with pytest.raises(ValueError):
        validate_prearm_precheck_response(payload)


def test_validate_clean_preflight_response_ok() -> None:
    payload = {
        "ok": True,
        "mode": "app_dev",
        "failures": 0,
        "max_ms": 45000,
        "max_ms_tools": 120000,
        "results": [
            {
                "id": "q1",
                "ok": True,
                "dt_ms": 10,
                "limit_ms": 45000,
                "expect_tools": False,
                "tool_calls": [],
                "error": "",
                "reply": "ok",
            }
        ],
    }
    validate_clean_preflight_response(payload)


def test_validate_clean_preflight_response_invalid_row() -> None:
    payload = {
        "ok": False,
        "mode": "app_dev",
        "failures": 1,
        "max_ms": 45000,
        "max_ms_tools": 120000,
        "results": [{"id": "q1"}],
    }
    with pytest.raises(ValueError):
        validate_clean_preflight_response(payload)

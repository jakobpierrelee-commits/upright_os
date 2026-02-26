import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from clean_legacy_gate import (
    LEGACY_EXEC_ENV_FLAG,
    legacy_execution_block_payload,
    legacy_execution_enabled,
    parse_flag_enabled,
)


def test_parse_flag_enabled_truthy_values() -> None:
    for raw in ("1", "true", "TRUE", "yes", "on"):
        assert parse_flag_enabled(raw) is True


def test_parse_flag_enabled_falsey_values() -> None:
    for raw in ("", "0", "false", "off", "no", "random"):
        assert parse_flag_enabled(raw) is False


def test_legacy_execution_enabled_defaults_off() -> None:
    assert legacy_execution_enabled(env={}) is False


def test_legacy_execution_enabled_on_when_flag_set() -> None:
    assert legacy_execution_enabled(env={LEGACY_EXEC_ENV_FLAG: "1"}) is True


def test_legacy_execution_block_payload_contains_operator_guidance() -> None:
    payload = legacy_execution_block_payload("/agent/chat")
    assert payload["ok"] is False
    assert payload["error"] == "legacy_execution_disabled"
    assert payload["path"] == "/agent/chat"
    assert payload["dev_flag"] == LEGACY_EXEC_ENV_FLAG
    assert payload["clean_lane_default"] is True

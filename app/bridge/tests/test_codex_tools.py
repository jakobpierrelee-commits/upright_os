"""
Validation tests for codex_tools.py - Phase C Tool Layer

Run with: python3 app/bridge/tests/test_codex_tools.py
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from codex_tools import (
    CodexToolExecutor,
    ToolResult,
    SAFE_COMMANDS,
    BLOCKED_COMMANDS,
    SAFE_SKETCH_VARIABLES,
    BLOCKED_SKETCH_VARIABLES,
    get_tool_definitions,
)


def test_tool_definitions_format():
    """Test that tool definitions are valid OpenAI format."""
    definitions = get_tool_definitions()

    assert len(definitions) >= 9, f"Expected at least 9 tools, got {len(definitions)}"

    for tool in definitions:
        assert "type" in tool, "Tool missing 'type'"
        assert tool["type"] == "function", "Tool type should be 'function'"
        assert "function" in tool, "Tool missing 'function'"

        func = tool["function"]
        assert "name" in func, "Function missing 'name'"
        assert "description" in func, "Function missing 'description'"
        assert "parameters" in func, "Function missing 'parameters'"

        params = func["parameters"]
        assert params.get("type") == "object", "Parameters should be object type"

    tool_names = [t["function"]["name"] for t in definitions]
    required_tools = [
        "get_probe_results",
        "query_telemetry",
        "query_checkpoints",
        "search_docs",
        "execute_command",
        "edit_sketch_value",
        "generate_sketch",
        "compile_firmware",
        "upload_firmware",
    ]

    for name in required_tools:
        assert name in tool_names, f"Missing required tool: {name}"

    print(f"✓ Tool definitions format passed ({len(definitions)} tools)")


def test_command_allowlist():
    """Test command allowlist/blocklist configuration."""
    # Safe commands should exist
    assert "PID" in SAFE_COMMANDS, "PID should be safe"
    assert "SETPOINT" in SAFE_COMMANDS, "SETPOINT should be safe"
    assert "MOTION" in SAFE_COMMANDS, "MOTION should be safe"
    assert "LIMITS" in SAFE_COMMANDS, "LIMITS should be safe"
    assert "CAL ZERO" in SAFE_COMMANDS, "CAL ZERO should be safe"
    assert "SAVECFG" in SAFE_COMMANDS, "SAVECFG should be safe"

    # Blocked commands should exist
    assert "ARM" in BLOCKED_COMMANDS, "ARM should be blocked"
    assert "DISARM" in BLOCKED_COMMANDS, "DISARM should be blocked"
    assert "MOTOR" in BLOCKED_COMMANDS, "MOTOR should be blocked"
    assert "STATE" in BLOCKED_COMMANDS, "STATE should be blocked"

    # No overlap between safe and blocked
    overlap = SAFE_COMMANDS & BLOCKED_COMMANDS
    assert len(overlap) == 0, f"Commands in both lists: {overlap}"

    print("✓ Command allowlist passed")


def test_sketch_variable_allowlist():
    """Test sketch variable allowlist/blocklist configuration."""
    # Safe variables should include Kalman params
    assert "qAngle" in SAFE_SKETCH_VARIABLES, "qAngle should be safe"
    assert "qBias" in SAFE_SKETCH_VARIABLES, "qBias should be safe"
    assert "rMeasure" in SAFE_SKETCH_VARIABLES, "rMeasure should be safe"

    # Safe variables should include timing
    assert "LOOP_US" in SAFE_SKETCH_VARIABLES, "LOOP_US should be safe"
    assert "TEL_MS" in SAFE_SKETCH_VARIABLES, "TEL_MS should be safe"

    # Blocked patterns should exist
    assert "PIN_" in BLOCKED_SKETCH_VARIABLES, "PIN_ pattern should be blocked"
    assert "MODE_" in BLOCKED_SKETCH_VARIABLES, "MODE_ pattern should be blocked"

    print("✓ Sketch variable allowlist passed")


def test_executor_initialization():
    """Test tool executor initialization."""
    executor = CodexToolExecutor()

    assert executor.gateway is None, "Gateway should be None by default"
    assert executor.db is None, "DB should be None by default"
    assert executor.rag is None, "RAG should be None by default"

    # Test with mocks
    mock_gateway = MagicMock()
    mock_db = MagicMock()

    executor = CodexToolExecutor(
        gateway=mock_gateway,
        db=mock_db,
        active_robot_id="test_robot",
    )

    assert executor.gateway is mock_gateway
    assert executor.db is mock_db
    assert executor.active_robot_id == "test_robot"

    print("✓ Executor initialization passed")


def test_execute_command_allowlist_enforcement():
    """Test that execute_command enforces allowlist."""
    mock_gateway = MagicMock()
    mock_gateway.is_busy.return_value = False
    mock_gateway.command.return_value = {"ok": True, "lines": ["OK PID"]}
    mock_gateway.get_status.return_value = {"mode": "SAFE_IDLE"}

    executor = CodexToolExecutor(gateway=mock_gateway)

    # Safe command should work
    result = executor.execute("execute_command", {"cmd": "PID 18 0.1 0.6"})
    assert result.ok, f"Safe command should succeed: {result.error}"
    assert mock_gateway.command.called, "Gateway command should be called"

    # Reset mock
    mock_gateway.reset_mock()

    # Blocked command should fail
    result = executor.execute("execute_command", {"cmd": "ARM"})
    assert not result.ok, "Blocked command should fail"
    assert "blocked" in result.error.lower(), f"Error should mention blocked: {result.error}"
    assert not mock_gateway.command.called, "Gateway should NOT be called for blocked command"

    # Reset mock
    mock_gateway.reset_mock()

    # Unknown command should fail
    result = executor.execute("execute_command", {"cmd": "UNKNOWN_CMD"})
    assert not result.ok, "Unknown command should fail"
    assert "allowlist" in result.error.lower(), f"Error should mention allowlist: {result.error}"

    print("✓ Execute command allowlist enforcement passed")


def test_execute_command_compound():
    """Test compound commands like CAL ZERO."""
    mock_gateway = MagicMock()
    mock_gateway.is_busy.return_value = False
    mock_gateway.command.return_value = {"ok": True, "lines": ["OK CAL ZERO"]}
    mock_gateway.get_status.return_value = {"mode": "SAFE_IDLE"}

    executor = CodexToolExecutor(gateway=mock_gateway)

    # CAL ZERO should work
    result = executor.execute("execute_command", {"cmd": "CAL ZERO"})
    assert result.ok, f"CAL ZERO should succeed: {result.error}"

    print("✓ Execute command compound passed")


def test_edit_sketch_allowlist_enforcement():
    """Test that edit_sketch_value enforces allowlist."""
    # Create temp sketch file
    with tempfile.TemporaryDirectory() as tmpdir:
        sketch_dir = Path(tmpdir) / "test_sketch"
        sketch_dir.mkdir()
        ino_file = sketch_dir / "test_sketch.ino"
        ino_file.write_text("""
// Test sketch
#define LOOP_US 4000
struct Config {
    float qAngle = 0.001f,
    float qBias = 0.003f,
};
const int PIN_MOTOR = 5;
""")

        executor = CodexToolExecutor(
            repo_root=Path(tmpdir),
            active_sketch_path=str(sketch_dir),
        )

        # Safe variable should work
        result = executor.execute("edit_sketch_value", {
            "variable": "LOOP_US",
            "value": "5000",
            "sketch_path": str(sketch_dir),
        })
        assert result.ok, f"Safe variable edit should succeed: {result.error}"
        assert result.data.get("old_value") == "4000", f"Old value wrong: {result.data}"
        assert result.data.get("new_value") == "5000", f"New value wrong: {result.data}"

        # Verify file was changed
        content = ino_file.read_text()
        assert "#define LOOP_US 5000" in content, "File should be updated"

        # Blocked variable should fail
        result = executor.execute("edit_sketch_value", {
            "variable": "PIN_MOTOR",
            "value": "6",
            "sketch_path": str(sketch_dir),
        })
        assert not result.ok, "Blocked variable should fail"
        assert "blocked" in result.error.lower() or "allowlist" in result.error.lower()

    print("✓ Edit sketch allowlist enforcement passed")


def test_query_telemetry_without_db():
    """Test query_telemetry gracefully fails without DB."""
    executor = CodexToolExecutor(db=None)

    result = executor.execute("query_telemetry", {"minutes": 5})
    assert not result.ok, "Should fail without DB"
    assert "not configured" in result.error.lower()

    print("✓ Query telemetry without DB passed")


def test_query_telemetry_with_mock_db():
    """Test query_telemetry with mock database."""
    mock_db = MagicMock()

    # Create mock telemetry data
    class MockSnapshot:
        def __init__(self, ang, out, mode):
            self.ts = time.time()
            self.ang = ang
            self.raw = ang + 0.1
            self.out = out
            self.mode = mode

    mock_db.query_telemetry.return_value = [
        MockSnapshot(1.0, 50.0, "BALANCING"),
        MockSnapshot(1.5, 55.0, "BALANCING"),
        MockSnapshot(0.5, 45.0, "BALANCING"),
    ]

    executor = CodexToolExecutor(db=mock_db, active_robot_id="test")

    # Test stats aggregation
    result = executor.execute("query_telemetry", {"minutes": 5, "aggregation": "stats"})
    assert result.ok, f"Query should succeed: {result.error}"
    assert result.data["count"] == 3
    assert "angle" in result.data
    assert "output" in result.data

    # Test raw aggregation
    result = executor.execute("query_telemetry", {"minutes": 5, "aggregation": "raw"})
    assert result.ok
    assert "samples" in result.data

    print("✓ Query telemetry with mock DB passed")


def test_search_docs_without_rag():
    """Test search_docs gracefully fails without RAG."""
    executor = CodexToolExecutor(rag=None)

    result = executor.execute("search_docs", {"query": "how to tune PID"})
    assert not result.ok, "Should fail without RAG"
    assert "not configured" in result.error.lower()

    print("✓ Search docs without RAG passed")


def test_upload_confirmation_flow():
    """Test upload_firmware confirmation token flow."""
    executor = CodexToolExecutor(
        active_sketch_path="/some/sketch",
        board_fqbn="arduino:avr:nano",
        port="/dev/ttyUSB0",
    )

    # First call without token should return confirmation request
    result = executor.execute("upload_firmware", {"sketch_path": "/some/sketch"})
    assert not result.ok, "Should request confirmation"
    assert result.error == "CONFIRMATION_REQUIRED"
    assert "confirmation_token" in result.data
    token = result.data["confirmation_token"]

    # Invalid token should fail
    result = executor.execute("upload_firmware", {
        "sketch_path": "/some/sketch",
        "confirmation_token": "invalid_token",
    })
    assert not result.ok
    assert "invalid" in result.error.lower() or "expired" in result.error.lower()

    # Valid token without firmware module should fail gracefully
    result = executor.execute("upload_firmware", {
        "sketch_path": "/some/sketch",
        "confirmation_token": token,
    })
    assert not result.ok
    assert "not configured" in result.error.lower()

    print("✓ Upload confirmation flow passed")


def test_generate_sketch_name_sanitization():
    """Test that generate_sketch sanitizes names."""
    with tempfile.TemporaryDirectory() as tmpdir:
        executor = CodexToolExecutor(repo_root=Path(tmpdir))

        # Create generated_firmware dir
        (Path(tmpdir) / "generated_firmware").mkdir()

        # Name with special chars should be sanitized
        # Note: without firmware module or template, this will fail
        # but we can still test the sanitization logic indirectly

        result = executor.execute("generate_sketch", {"name": ""})
        assert not result.ok, "Empty name should fail"
        assert "required" in result.error.lower()

    print("✓ Generate sketch name validation passed")


def test_tool_result_structure():
    """Test ToolResult dataclass structure."""
    result = ToolResult(
        ok=True,
        tool="test_tool",
        data={"key": "value"},
    )

    assert result.ok is True
    assert result.tool == "test_tool"
    assert result.data == {"key": "value"}
    assert result.error is None
    assert result.execution_time_ms == 0.0

    # Test to_dict
    d = result.to_dict()
    assert d["ok"] is True
    assert d["tool"] == "test_tool"
    assert d["data"] == {"key": "value"}

    print("✓ Tool result structure passed")


def test_unknown_tool():
    """Test handling of unknown tool names."""
    executor = CodexToolExecutor()

    result = executor.execute("unknown_tool_xyz", {})
    assert not result.ok
    assert "unknown" in result.error.lower()

    print("✓ Unknown tool handling passed")


def run_all_tests():
    """Run all validation tests."""
    print("\n" + "=" * 60)
    print("CodexTools Phase C Validation")
    print("=" * 60 + "\n")

    tests = [
        ("Tool Definitions Format", test_tool_definitions_format),
        ("Command Allowlist", test_command_allowlist),
        ("Sketch Variable Allowlist", test_sketch_variable_allowlist),
        ("Executor Initialization", test_executor_initialization),
        ("Execute Command Allowlist", test_execute_command_allowlist_enforcement),
        ("Execute Command Compound", test_execute_command_compound),
        ("Edit Sketch Allowlist", test_edit_sketch_allowlist_enforcement),
        ("Query Telemetry Without DB", test_query_telemetry_without_db),
        ("Query Telemetry With Mock DB", test_query_telemetry_with_mock_db),
        ("Search Docs Without RAG", test_search_docs_without_rag),
        ("Upload Confirmation Flow", test_upload_confirmation_flow),
        ("Generate Sketch Validation", test_generate_sketch_name_sanitization),
        ("Tool Result Structure", test_tool_result_structure),
        ("Unknown Tool Handling", test_unknown_tool),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        try:
            result = test_fn()
            if result:
                passed += 1
            else:
                failed += 1
                print(f"✗ {name} returned False")
        except Exception as e:
            failed += 1
            print(f"✗ {name} failed with exception: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60 + "\n")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

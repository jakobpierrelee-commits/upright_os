"""
Validation tests for codex_agent.py - Phase D Agent Integration

Run with: python3 app/bridge/tests/test_codex_agent.py
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

from codex_agent import CodexAgent, create_codex_agent, MAX_TOOL_ITERATIONS
from codex_db import CodexDB


def test_agent_initialization():
    """Test agent initializes without dependencies."""
    agent = CodexAgent()

    assert agent.gateway is None
    assert agent.db is not None  # Uses default singleton
    assert agent.rag is None
    assert agent.firmware is None

    print("✓ Agent initialization passed")


def test_agent_with_mocks():
    """Test agent with mock dependencies."""
    mock_gateway = MagicMock()
    mock_db = MagicMock()
    mock_rag = MagicMock()

    agent = CodexAgent(
        gateway=mock_gateway,
        db=mock_db,
        rag=mock_rag,
    )

    assert agent.gateway is mock_gateway
    assert agent.db is mock_db
    assert agent.rag is mock_rag

    print("✓ Agent with mocks passed")


def test_tool_executor_creation():
    """Test that tool executor is created with context."""
    mock_gateway = MagicMock()

    agent = CodexAgent(gateway=mock_gateway)

    executor = agent._get_tool_executor(
        active_sketch_path="/some/sketch",
        active_robot_id="robot_1",
        board_fqbn="arduino:avr:nano",
        port="/dev/ttyUSB0",
    )

    assert executor.gateway is mock_gateway
    assert executor.active_sketch_path == "/some/sketch"
    assert executor.active_robot_id == "robot_1"
    assert executor.board_fqbn == "arduino:avr:nano"
    assert executor.port == "/dev/ttyUSB0"

    print("✓ Tool executor creation passed")


def test_rag_context_injection():
    """Test RAG context injection with mock."""
    mock_rag = MagicMock()
    mock_rag.get_context_for_query.return_value = "Relevant doc content about PID tuning."

    agent = CodexAgent(rag=mock_rag)

    context = agent._inject_rag_context("how do I tune PID?")

    assert context == "Relevant doc content about PID tuning."
    mock_rag.get_context_for_query.assert_called_once()

    print("✓ RAG context injection passed")


def test_rag_context_failure_graceful():
    """Test that RAG failures are handled gracefully."""
    mock_rag = MagicMock()
    mock_rag.get_context_for_query.side_effect = Exception("RAG error")

    agent = CodexAgent(rag=mock_rag)

    # Should not raise, just return empty
    context = agent._inject_rag_context("test query")
    assert context == ""

    print("✓ RAG context failure handling passed")


def test_telemetry_logging():
    """Test telemetry is logged from status context."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    try:
        db = CodexDB(db_path)
        db.init_schema()

        agent = CodexAgent(db=db)

        status = {
            "mode": "BALANCING",
            "ang": 1.5,
            "raw": 1.6,
            "out": 50.0,
            "kp": 18.0,
            "ki": 0.1,
            "kd": 0.6,
        }

        agent._log_telemetry_snapshot(status, "test_robot")

        # Check telemetry was logged
        snapshots = db.query_telemetry(robot_id="test_robot", limit=1)
        assert len(snapshots) == 1
        assert snapshots[0].mode == "BALANCING"
        assert snapshots[0].ang == 1.5

        print("✓ Telemetry logging passed")
    finally:
        db.close()
        db_path.unlink(missing_ok=True)


def test_extract_tool_calls():
    """Test tool call extraction from OpenAI response."""
    agent = CodexAgent()

    # Response with tool calls
    response_with_tools = {
        "choices": [{
            "message": {
                "tool_calls": [
                    {
                        "id": "call_123",
                        "function": {
                            "name": "execute_command",
                            "arguments": '{"cmd": "PID 18 0.1 0.6"}',
                        },
                    }
                ],
            },
        }],
    }

    tool_calls = agent._extract_tool_calls(response_with_tools)
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "execute_command"

    # Response without tool calls
    response_no_tools = {
        "choices": [{
            "message": {
                "content": "Here is my answer.",
            },
        }],
    }

    tool_calls = agent._extract_tool_calls(response_no_tools)
    assert len(tool_calls) == 0

    # Empty response
    tool_calls = agent._extract_tool_calls({})
    assert len(tool_calls) == 0

    print("✓ Extract tool calls passed")


def test_extract_text_content():
    """Test text content extraction from OpenAI response."""
    agent = CodexAgent()

    response = {
        "choices": [{
            "message": {
                "content": "  Here is the answer.  ",
            },
        }],
    }

    text = agent._extract_text_content(response)
    assert text == "Here is the answer."

    # Empty response
    text = agent._extract_text_content({})
    assert text == "(no response)"

    # None content
    response = {"choices": [{"message": {"content": None}}]}
    text = agent._extract_text_content(response)
    assert text == "(no response)"

    print("✓ Extract text content passed")


def test_max_iterations_constant():
    """Test max iterations is set appropriately."""
    assert MAX_TOOL_ITERATIONS >= 3, "Should allow at least 3 iterations"
    assert MAX_TOOL_ITERATIONS <= 10, "Should cap iterations to prevent runaway"

    print(f"✓ Max iterations constant passed (value: {MAX_TOOL_ITERATIONS})")


def test_factory_function():
    """Test create_codex_agent factory function."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    try:
        # Patch the default DB path
        import codex_db
        original_path = codex_db.DEFAULT_DB_PATH
        codex_db.DEFAULT_DB_PATH = db_path
        codex_db._default_db = None  # Reset singleton

        mock_gateway = MagicMock()
        mock_firmware = MagicMock()

        agent = create_codex_agent(
            gateway=mock_gateway,
            firmware_module=mock_firmware,
            repo_root="/tmp",
        )

        assert agent.gateway is mock_gateway
        assert agent.firmware is mock_firmware
        assert agent.db is not None

        print("✓ Factory function passed")
    finally:
        codex_db.DEFAULT_DB_PATH = original_path
        codex_db._default_db = None
        db_path.unlink(missing_ok=True)


def test_chat_requires_api_key():
    """Test chat fails without API key."""
    agent = CodexAgent()

    try:
        agent.chat_with_tools(
            message="test",
            context={},
            api_key="",
            model="gpt-4",
            system_prompt="test",
        )
        assert False, "Should raise for missing API key"
    except RuntimeError as e:
        assert "api_key" in str(e).lower()

    print("✓ Chat requires API key passed")


def test_chat_requires_message():
    """Test chat fails without message."""
    agent = CodexAgent()

    try:
        agent.chat_with_tools(
            message="   ",
            context={},
            api_key="test_key",
            model="gpt-4",
            system_prompt="test",
        )
        assert False, "Should raise for empty message"
    except RuntimeError as e:
        assert "empty" in str(e).lower()

    print("✓ Chat requires message passed")


def run_all_tests():
    """Run all validation tests."""
    print("\n" + "=" * 60)
    print("CodexAgent Phase D Validation")
    print("=" * 60 + "\n")

    tests = [
        ("Agent Initialization", test_agent_initialization),
        ("Agent With Mocks", test_agent_with_mocks),
        ("Tool Executor Creation", test_tool_executor_creation),
        ("RAG Context Injection", test_rag_context_injection),
        ("RAG Context Failure Handling", test_rag_context_failure_graceful),
        ("Telemetry Logging", test_telemetry_logging),
        ("Extract Tool Calls", test_extract_tool_calls),
        ("Extract Text Content", test_extract_text_content),
        ("Max Iterations Constant", test_max_iterations_constant),
        ("Factory Function", test_factory_function),
        ("Chat Requires API Key", test_chat_requires_api_key),
        ("Chat Requires Message", test_chat_requires_message),
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

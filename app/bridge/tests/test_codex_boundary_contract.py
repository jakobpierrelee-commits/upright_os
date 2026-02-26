import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_codex_agent_does_not_construct_toolresult_directly() -> None:
    src = (Path(__file__).parent.parent / "codex_agent.py").read_text(
        encoding="utf-8"
    )
    assert "ToolResult(" not in src


def test_codex_tools_has_no_agent_orchestration_import() -> None:
    src = (Path(__file__).parent.parent / "codex_tools.py").read_text(
        encoding="utf-8"
    )
    assert "codex_agent" not in src


def test_orchestrator_owns_tool_execution_error_type() -> None:
    src = (Path(__file__).parent.parent / "codex_tool_orchestrator.py").read_text(
        encoding="utf-8"
    )
    assert "class ToolExecutionError" in src

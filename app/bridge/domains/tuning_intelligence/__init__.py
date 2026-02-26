"""
Tuning Intelligence Domain

Handles tuning policy, recommendations, and optimization logic.
"""

# Re-export from existing modules (facade pattern)
try:
    from app.bridge.tuning_policy import TuningPolicy, evaluate_tuning_plan
except ImportError:
    try:
        from tuning_policy import TuningPolicy, evaluate_tuning_plan  # type: ignore
    except ImportError:
        TuningPolicy = None
        evaluate_tuning_plan = None

try:
    from app.bridge.codex_tools import CodexToolExecutor, get_tool_definitions
except ImportError:
    try:
        from codex_tools import CodexToolExecutor, get_tool_definitions  # type: ignore
    except ImportError:
        CodexToolExecutor = None
        get_tool_definitions = None

__all__ = [
    "TuningPolicy",
    "evaluate_tuning_plan",
    "CodexToolExecutor",
    "get_tool_definitions",
]

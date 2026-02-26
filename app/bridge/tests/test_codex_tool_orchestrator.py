import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from codex_tool_orchestrator import execute_tool_batch


class _DummyResult:
    def __init__(self, ok: bool, tool: str, error: str = "") -> None:
        self.ok = ok
        self.tool = tool
        self.error = error

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "tool": self.tool,
            "data": {},
            "error": self.error or None,
            "execution_time_ms": 0.0,
        }


class _DummyExecutor:
    def __init__(self, fail_tools: set[str] | None = None) -> None:
        self.fail_tools = fail_tools or set()

    def execute(self, tool_name: str, _args: dict) -> _DummyResult:
        if tool_name in self.fail_tools:
            return _DummyResult(ok=False, tool=tool_name, error="simulated_fail")
        return _DummyResult(ok=True, tool=tool_name)


def test_execute_tool_batch_success_attaches_reasoning_once() -> None:
    response = {
        "choices": [
            {
                "message": {
                    "content": "planner reasoning",
                }
            }
        ]
    }
    tool_calls = [
        {"id": "1", "function": {"name": "query_telemetry", "arguments": "{}"}},
        {"id": "2", "function": {"name": "search_docs", "arguments": "{}"}},
    ]
    executed_tools: list[dict] = []
    audits: list[dict] = []

    out = execute_tool_batch(
        response=response,
        tool_calls=tool_calls,
        tool_executor=_DummyExecutor(),
        executed_tools=executed_tools,
        sketch_request=False,
        sketch_generation_started_at=None,
        log_tool_audit=lambda **kwargs: audits.append(kwargs),
    )

    assert len(out["tool_results"]) == 2
    assert len(executed_tools) == 2
    assert executed_tools[0].get("reasoning") == "planner reasoning"
    assert "reasoning" not in executed_tools[1]
    assert len(audits) == 2
    assert audits[0]["tool"] == "query_telemetry"


def test_execute_tool_batch_handles_bad_json_args() -> None:
    response = {"choices": [{"message": {"content": ""}}]}
    tool_calls = [
        {
            "id": "x",
            "function": {"name": "search_docs", "arguments": "{bad-json"},
        }
    ]
    executed_tools: list[dict] = []

    out = execute_tool_batch(
        response=response,
        tool_calls=tool_calls,
        tool_executor=_DummyExecutor(),
        executed_tools=executed_tools,
        sketch_request=False,
        sketch_generation_started_at=None,
        log_tool_audit=lambda **_kwargs: None,
    )

    payload = json.loads(out["tool_results"][0]["content"])
    assert payload["ok"] is True
    assert executed_tools[0]["args"] == {}


def test_execute_tool_batch_maps_tool_failure_to_structured_error() -> None:
    response = {"choices": [{"message": {"content": ""}}]}
    tool_calls = [
        {"id": "x", "function": {"name": "compile_firmware", "arguments": "{}"}}
    ]
    executed_tools: list[dict] = []

    out = execute_tool_batch(
        response=response,
        tool_calls=tool_calls,
        tool_executor=_DummyExecutor(fail_tools={"compile_firmware"}),
        executed_tools=executed_tools,
        sketch_request=False,
        sketch_generation_started_at=None,
        log_tool_audit=lambda **_kwargs: None,
    )

    payload = json.loads(out["tool_results"][0]["content"])
    assert payload["ok"] is False
    assert payload["tool"] == "compile_firmware"
    assert payload["data"]["recoverable"] is True
    assert "simulated_fail" in str(payload["error"])


def test_execute_tool_batch_marks_sketch_start_on_generate_sketch() -> None:
    response = {"choices": [{"message": {"content": ""}}]}
    tool_calls = [
        {"id": "x", "function": {"name": "generate_sketch", "arguments": "{}"}}
    ]
    executed_tools: list[dict] = []

    out = execute_tool_batch(
        response=response,
        tool_calls=tool_calls,
        tool_executor=_DummyExecutor(),
        executed_tools=executed_tools,
        sketch_request=True,
        sketch_generation_started_at=None,
        log_tool_audit=lambda **_kwargs: None,
    )
    assert isinstance(out["sketch_generation_started_at"], float)

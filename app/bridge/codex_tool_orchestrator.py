"""
Codex tool-call orchestration helpers.

This module owns response/tool-call orchestration logic so `codex_tools.py`
can focus on tool registry + execution only.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ToolExecutionError(Exception):
    """Raised when a tool fails to execute."""

    def __init__(self, tool: str, message: str, recoverable: bool = True):
        self.tool = tool
        self.message = message
        self.recoverable = recoverable
        super().__init__(f"Tool '{tool}' failed: {message}")

    def to_dict(self) -> dict:
        return {
            "error_type": "ToolExecutionError",
            "tool": self.tool,
            "message": self.message,
            "recoverable": self.recoverable,
        }


def _coerce_tool_result(result: Any, *, tool_name: str) -> Dict[str, Any]:
    if hasattr(result, "to_dict") and callable(getattr(result, "to_dict")):
        payload = result.to_dict()
        if isinstance(payload, dict):
            return payload
    if isinstance(result, dict):
        return dict(result)
    return {
        "ok": bool(getattr(result, "ok", False)),
        "tool": tool_name,
        "data": dict(getattr(result, "data", {}) or {}),
        "error": getattr(result, "error", None),
        "execution_time_ms": float(getattr(result, "execution_time_ms", 0.0) or 0.0),
    }


def _error_result(
    *,
    tool_name: str,
    error: str,
    recoverable: bool,
    error_type: str = "ToolExecutionError",
) -> Dict[str, Any]:
    return {
        "ok": False,
        "tool": tool_name,
        "data": {
            "recoverable": recoverable,
            "error_type": error_type,
        },
        "error": error,
        "execution_time_ms": 0.0,
    }


def execute_tool_batch(
    *,
    response: Dict[str, Any],
    tool_calls: List[Dict[str, Any]],
    tool_executor: Any,
    executed_tools: List[Dict[str, Any]],
    sketch_request: bool,
    sketch_generation_started_at: Optional[float],
    log_tool_audit: Callable[..., None],
) -> Dict[str, Any]:
    """
    Execute one model-issued batch of tool calls and return tool-response messages.

    Returns:
      {
        "tool_results": [OpenAI tool messages...],
        "executed_tools": [...],
        "sketch_generation_started_at": float|None
      }
    """
    assistant_msg = response.get("choices", [{}])[0].get("message", {})
    tool_reasoning = str(assistant_msg.get("content") or "").strip()
    attached_reasoning = any("reasoning" in t for t in executed_tools)

    tool_results: List[Dict[str, Any]] = []
    for tc in tool_calls:
        tool_name = str(tc.get("function", {}).get("name", "")).strip()
        tool_args_str = str(tc.get("function", {}).get("arguments", "{}"))
        tool_call_id = str(tc.get("id", ""))

        try:
            tool_args = json.loads(tool_args_str)
            if not isinstance(tool_args, dict):
                tool_args = {}
        except json.JSONDecodeError:
            tool_args = {}

        logger.info(f"Executing tool: {tool_name} with args: {tool_args}")

        tool_start = time.time()
        if (
            sketch_request
            and tool_name == "generate_sketch"
            and sketch_generation_started_at is None
        ):
            sketch_generation_started_at = tool_start

        try:
            raw_result = tool_executor.execute(tool_name, tool_args)
            result = _coerce_tool_result(raw_result, tool_name=tool_name)
            if not bool(result.get("ok", False)):
                raise ToolExecutionError(
                    tool=tool_name,
                    message=str(result.get("error") or "tool_execution_failed"),
                    recoverable=True,
                )
        except ToolExecutionError as te:
            result = _error_result(
                tool_name=tool_name,
                error=te.message,
                recoverable=te.recoverable,
            )
            logger.warning(str(te))
        except Exception as exc:
            result = _error_result(
                tool_name=tool_name,
                error=f"tool_execution_error:{exc}",
                recoverable=True,
            )
            logger.warning(f"Tool '{tool_name}' raised unexpected error: {exc}")

        tool_latency_ms = (time.time() - tool_start) * 1000
        log_tool_audit(
            tool=tool_name,
            args=tool_args,
            ok=bool(result.get("ok", False)),
            latency_ms=tool_latency_ms,
            error=result.get("error"),
        )

        tool_entry = {
            "tool": tool_name,
            "args": tool_args,
            "result": result,
        }
        if tool_reasoning and not attached_reasoning:
            tool_entry["reasoning"] = tool_reasoning
            attached_reasoning = True
        executed_tools.append(tool_entry)

        tool_results.append(
            {
                "tool_call_id": tool_call_id,
                "role": "tool",
                "content": json.dumps(result),
            }
        )

    return {
        "tool_results": tool_results,
        "executed_tools": executed_tools,
        "sketch_generation_started_at": sketch_generation_started_at,
    }


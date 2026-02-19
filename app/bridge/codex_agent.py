"""
Codex Agent Module - Tool-enabled AI agent wrapper.

Wraps AIManager with:
- OpenAI function calling support
- Tool execution via CodexToolExecutor
- RAG context injection
- Telemetry logging

Maintains backward compatibility with existing UPRIGHT_APPLY_JSON flow.
"""

from __future__ import annotations

import json
import logging
import os
import ssl
import time
from typing import Any, Callable, Dict, List, Optional
from urllib import request as urlrequest
from urllib import error as urlerror

try:
    import certifi
except ImportError:
    certifi = None

from codex_db import CodexDB, TelemetrySnapshot, Checkpoint, get_codex_db
from codex_rag import CodexRAG, get_codex_rag
from codex_tools import CodexToolExecutor, ToolResult, get_tool_definitions

logger = logging.getLogger(__name__)

# Max tool call iterations to prevent infinite loops
MAX_TOOL_ITERATIONS = 5

# OpenAI request timeout in seconds
OPENAI_TIMEOUT_S = 45


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


class CodexAgent:
    """
    Tool-enabled AI agent for UpRight.os.
    
    Wraps OpenAI API with function calling and executes tools via CodexToolExecutor.
    Falls back to standard chat if tools are unavailable.
    """

    def __init__(
        self,
        gateway: Any = None,
        db: Optional[CodexDB] = None,
        rag: Optional[CodexRAG] = None,
        firmware_module: Any = None,
        probe_funcs: Optional[Dict[str, Callable]] = None,
        repo_root: Optional[str] = None,
        host_capture: Any = None,
    ):
        self.gateway = gateway
        self.db = db or get_codex_db()
        self.rag = rag
        self.firmware = firmware_module
        self.probe_funcs = probe_funcs or {}
        self.repo_root = repo_root
        self.host_capture = host_capture

        self._ssl_context = self._build_ssl_context()

        # Tool executor - initialized lazily with current context
        self._tool_executor: Optional[CodexToolExecutor] = None

    @staticmethod
    def _build_ssl_context() -> ssl.SSLContext:
        ca_bundle = os.environ.get("OPENAI_CA_BUNDLE", "").strip()
        if ca_bundle:
            return ssl.create_default_context(cafile=ca_bundle)
        if certifi is not None:
            return ssl.create_default_context(cafile=certifi.where())
        return ssl.create_default_context()

    def _get_tool_executor(
        self,
        active_sketch_path: Optional[str] = None,
        active_robot_id: Optional[str] = None,
        board_fqbn: Optional[str] = None,
        port: Optional[str] = None,
    ) -> CodexToolExecutor:
        """Get or create tool executor with current context."""
        return CodexToolExecutor(
            gateway=self.gateway,
            db=self.db,
            rag=self.rag,
            firmware_module=self.firmware,
            probe_funcs=self.probe_funcs,
            repo_root=self.repo_root,
            active_sketch_path=active_sketch_path,
            active_robot_id=active_robot_id,
            board_fqbn=board_fqbn,
            port=port,
            host_capture=self.host_capture,
        )

    def _inject_rag_context(self, user_message: str, max_tokens: int = 1500) -> str:
        """Get relevant RAG context for the user's query."""
        if not self.rag:
            return ""
        try:
            return self.rag.get_context_for_query(user_message, max_tokens=max_tokens)
        except Exception as e:
            logger.warning(f"RAG context injection failed: {e}")
            return ""

    def _log_telemetry_snapshot(self, status: Dict[str, Any], robot_id: str = "default") -> None:
        """Log current status as telemetry snapshot."""
        if not self.db:
            return
        try:
            snapshot = TelemetrySnapshot(
                ts=time.time(),
                robot_id=robot_id,
                mode=str(status.get("mode", "")),
                ang=float(status.get("ang", 0) or 0),
                raw=float(status.get("raw", 0) or 0),
                out=float(status.get("out", 0) or 0),
                kp=float(status.get("kp", 0) or 0),
                ki=float(status.get("ki", 0) or 0),
                kd=float(status.get("kd", 0) or 0),
                kv=float(status.get("kv", 0) or 0),
                kx=float(status.get("kx", 0) or 0),
                setpoint=float(status.get("set", 0) or 0),
                voltage=float(status.get("vbat", 0) or status.get("voltage", 0) or 0),
            )
            self.db.log_telemetry(snapshot)
        except Exception as e:
            logger.debug(f"Telemetry logging failed: {e}")

    def chat_with_tools(
        self,
        *,
        message: str,
        context: Dict[str, Any],
        api_key: str,
        model: str,
        system_prompt: str,
        enable_tools: bool = True,
        active_sketch_path: Optional[str] = None,
        active_robot_id: Optional[str] = None,
        board_fqbn: Optional[str] = None,
        port: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Chat with optional tool calling support.
        
        Args:
            message: User message
            context: Live context (status, serial health, etc.)
            api_key: OpenAI API key
            model: Model name
            system_prompt: System prompt
            enable_tools: Whether to enable tool calling
            active_sketch_path: Current sketch path for tools
            active_robot_id: Current robot ID for tools
            board_fqbn: Board FQBN for firmware tools
            port: Serial port for firmware tools
            
        Returns:
            Dict with: answer, tool_calls (list of executed tools), raw_response
        """
        if not api_key:
            raise RuntimeError("openai_api_key_missing")

        user_msg = message.strip()
        if not user_msg:
            raise RuntimeError("empty_message")

        # Log telemetry from context
        status = context.get("status", {})
        self._log_telemetry_snapshot(status, active_robot_id or "default")

        # Inject RAG context
        rag_context = self._inject_rag_context(user_msg)

        # Build context blob
        context_blob = json.dumps(context, separators=(",", ":"), ensure_ascii=True)

        # Build messages
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": f"live_context={context_blob}"},
        ]

        if rag_context:
            messages.append({
                "role": "system",
                "content": f"relevant_documentation:\n{rag_context}",
            })

        messages.append({"role": "user", "content": user_msg})

        # Get tool definitions if enabled
        tools = get_tool_definitions() if enable_tools else None

        # Initialize tool executor
        tool_executor = self._get_tool_executor(
            active_sketch_path=active_sketch_path,
            active_robot_id=active_robot_id,
            board_fqbn=board_fqbn,
            port=port,
        )

        # Track tool calls for response
        executed_tools: List[Dict[str, Any]] = []
        iterations = 0

        while iterations < MAX_TOOL_ITERATIONS:
            iterations += 1

            # Call OpenAI API
            response = self._call_openai(
                messages=messages,
                api_key=api_key,
                model=model,
                tools=tools,
            )

            # Check for tool calls
            tool_calls = self._extract_tool_calls(response)

            if not tool_calls:
                # No tool calls - extract final answer
                answer = self._extract_text_content(response)
                return {
                    "answer": answer,
                    "tool_calls": executed_tools,
                    "raw_response": response,
                    "iterations": iterations,
                }

            # Execute tool calls
            tool_results = []
            for tc in tool_calls:
                tool_name = tc.get("function", {}).get("name", "")
                tool_args_str = tc.get("function", {}).get("arguments", "{}")
                tool_call_id = tc.get("id", "")

                try:
                    tool_args = json.loads(tool_args_str)
                except json.JSONDecodeError:
                    tool_args = {}

                logger.info(f"Executing tool: {tool_name} with args: {tool_args}")

                tool_start = time.time()
                try:
                    result = tool_executor.execute(tool_name, tool_args)
                    if not result.ok:
                        raise ToolExecutionError(
                            tool=tool_name,
                            message=result.error or "tool_execution_failed",
                            recoverable=True,
                        )
                except ToolExecutionError as te:
                    result = ToolResult(
                        ok=False,
                        tool=tool_name,
                        error=te.message,
                        data={"recoverable": te.recoverable, "error_type": "ToolExecutionError"},
                    )
                    logger.warning(str(te))
                except Exception as exc:
                    result = ToolResult(
                        ok=False,
                        tool=tool_name,
                        error=f"tool_execution_error:{exc}",
                        data={"recoverable": True, "error_type": "ToolExecutionError"},
                    )
                    logger.warning(f"Tool '{tool_name}' raised unexpected error: {exc}")
                tool_latency_ms = (time.time() - tool_start) * 1000

                # Structured JSON log for observability
                self._log_tool_audit(
                    tool=tool_name,
                    args=tool_args,
                    ok=result.ok,
                    latency_ms=tool_latency_ms,
                    error=result.error,
                )

                executed_tools.append({
                    "tool": tool_name,
                    "args": tool_args,
                    "result": result.to_dict(),
                })

                tool_results.append({
                    "tool_call_id": tool_call_id,
                    "role": "tool",
                    "content": json.dumps(result.to_dict()),
                })

            # Add assistant message with tool calls
            assistant_msg = response.get("choices", [{}])[0].get("message", {})
            messages.append(assistant_msg)

            # Add tool results
            messages.extend(tool_results)

        # Max iterations reached
        logger.warning(f"Tool calling reached max iterations ({MAX_TOOL_ITERATIONS})")
        return {
            "answer": "I've reached the maximum number of tool calls. Please try a more specific request.",
            "tool_calls": executed_tools,
            "raw_response": None,
            "iterations": iterations,
            "error": "max_iterations_reached",
        }

    def _call_openai(
        self,
        messages: List[Dict[str, Any]],
        api_key: str,
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Make OpenAI API call."""
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        data = json.dumps(payload).encode("utf-8")

        req = urlrequest.Request(
            f"{base_url.rstrip('/')}/chat/completions",
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )

        try:
            with urlrequest.urlopen(req, timeout=OPENAI_TIMEOUT_S, context=self._ssl_context) as r:
                raw = r.read().decode("utf-8", errors="replace")
            return json.loads(raw)
        except urlerror.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            raise RuntimeError(f"openai_http_error:{exc.code}:{body}") from exc
        except TimeoutError:
            raise RuntimeError("openai_timeout: Request timed out after 45 seconds. Please try again with a simpler request.")
        except Exception as exc:
            emsg = str(exc)
            if "timed out" in emsg.lower() or "timeout" in emsg.lower():
                raise RuntimeError("openai_timeout: Request timed out after 45 seconds. Please try again with a simpler request.")
            if "CERTIFICATE_VERIFY_FAILED" in emsg:
                raise RuntimeError("openai_tls_cert_verify_failed") from exc
            raise RuntimeError(f"openai_request_failed:{exc}") from exc

    def _extract_tool_calls(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract tool calls from OpenAI response."""
        choices = response.get("choices", [])
        if not choices:
            return []

        message = choices[0].get("message", {})
        tool_calls = message.get("tool_calls", [])

        return tool_calls if isinstance(tool_calls, list) else []

    def _extract_text_content(self, response: Dict[str, Any]) -> str:
        """Extract text content from OpenAI response."""
        choices = response.get("choices", [])
        if not choices:
            return "(no response)"

        message = choices[0].get("message", {})
        content = message.get("content", "")

        return content.strip() if content else "(no response)"

    def _log_tool_audit(
        self,
        tool: str,
        args: Dict[str, Any],
        ok: bool,
        latency_ms: float,
        error: Optional[str] = None,
    ) -> None:
        """Log structured JSON audit record for tool execution."""
        import hashlib

        # Create a summary hash of args (for privacy, don't log full args)
        args_json = json.dumps(args, sort_keys=True, default=str)
        args_hash = hashlib.sha256(args_json.encode()).hexdigest()[:12]

        audit_record = {
            "event": "tool_execution",
            "tool": tool,
            "args_hash": args_hash,
            "args_keys": list(args.keys()),
            "ok": ok,
            "latency_ms": round(latency_ms, 2),
            "error": error,
            "ts": time.time(),
        }

        # Log as JSON for structured log aggregation
        logger.info(f"TOOL_AUDIT: {json.dumps(audit_record)}")

        # Persist to database if available
        if self.db:
            try:
                self.db.log_tool_audit(
                    tool=tool,
                    args_hash=args_hash,
                    ok=ok,
                    latency_ms=latency_ms,
                    error=error,
                )
            except Exception as e:
                logger.debug(f"Tool audit DB log failed: {e}")


def create_codex_agent(
    gateway: Any = None,
    firmware_module: Any = None,
    probe_funcs: Optional[Dict[str, Callable]] = None,
    repo_root: Optional[str] = None,
    openai_key: Optional[str] = None,
    host_capture: Any = None,
) -> CodexAgent:
    """
    Factory function to create a CodexAgent with all dependencies.
    
    Args:
        gateway: Serial gateway for commands
        firmware_module: Firmware module for compile/upload
        probe_funcs: Dict mapping probe names to functions
        repo_root: Repository root path
        openai_key: OpenAI API key for RAG embeddings
        host_capture: HostCaptureManager for burst captures
        
    Returns:
        Configured CodexAgent instance
    """
    db = get_codex_db()
    db.init_schema()

    rag = None
    if openai_key:
        rag = get_codex_rag(openai_key)

    return CodexAgent(
        gateway=gateway,
        db=db,
        rag=rag,
        firmware_module=firmware_module,
        probe_funcs=probe_funcs,
        repo_root=repo_root,
        host_capture=host_capture,
    )

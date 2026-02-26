"""
Control Runtime Tools - AI agent tool implementations for command execution.

Extracted from codex_tools.py for domain organization.
Tools: execute_shell, execute_command
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from app.bridge.domains.ai_agent.tool_constants import (
        ToolResult,
        SAFE_COMMANDS,
        BLOCKED_COMMANDS,
    )
except ImportError:
    from domains.ai_agent.tool_constants import (  # type: ignore
        ToolResult,
        SAFE_COMMANDS,
        BLOCKED_COMMANDS,
    )

SHELL_MAX_TIMEOUT_S = int(os.environ.get("CODEX_SHELL_MAX_TIMEOUT_S", "120"))


class ControlTools:
    """Control and command execution tool implementations."""

    def __init__(
        self,
        gateway: Any = None,
        repo_root: Optional[Path] = None,
    ):
        self.gateway = gateway
        self.repo_root = repo_root or Path(__file__).parent.parent.parent.parent

    def execute_shell(self, args: Dict[str, Any]) -> ToolResult:
        """Execute terminal command inside repository workspace."""
        cmd = str(args.get("cmd", "")).strip()
        if not cmd:
            return ToolResult(ok=False, tool="execute_shell", error="cmd is required")

        cwd_raw = str(args.get("cwd", "")).strip()
        repo_root = self.repo_root.resolve()
        if cwd_raw:
            target = (repo_root / cwd_raw).resolve()
            try:
                target.relative_to(repo_root)
            except Exception:
                return ToolResult(
                    ok=False,
                    tool="execute_shell",
                    error="cwd must be inside repository root",
                )
        else:
            target = repo_root

        timeout_s = int(args.get("timeout_s", 60) or 60)
        timeout_s = max(1, min(timeout_s, SHELL_MAX_TIMEOUT_S))

        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                cwd=str(target),
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            partial_out = str((exc.stdout or "") + "\n" + (exc.stderr or "")).strip()
            return ToolResult(
                ok=False,
                tool="execute_shell",
                error=f"timeout_after_{timeout_s}s",
                data={
                    "cmd": cmd,
                    "cwd": str(target),
                    "partial_output": partial_out[-4000:],
                },
            )
        except Exception as exc:
            return ToolResult(
                ok=False,
                tool="execute_shell",
                error=f"shell_exec_failed:{exc}",
                data={"cmd": cmd, "cwd": str(target)},
            )

        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        merged = "\n".join([x for x in [out, err] if x]).strip()

        return ToolResult(
            ok=(proc.returncode == 0),
            tool="execute_shell",
            data={
                "cmd": cmd,
                "cwd": str(target),
                "exit_code": int(proc.returncode),
                "output": merged[-12000:],
            },
            error=None if proc.returncode == 0 else f"exit_code:{proc.returncode}",
        )

    def execute_command(self, args: Dict[str, Any]) -> ToolResult:
        """Execute a serial command with safety enforcement."""
        if not self.gateway:
            return ToolResult(
                ok=False, tool="execute_command", error="Serial gateway not connected"
            )

        # Serial busy guard
        if hasattr(self.gateway, "is_busy") and self.gateway.is_busy():
            return ToolResult(
                ok=False,
                tool="execute_command",
                error="SERIAL_BUSY: Serial port is currently in use. Please wait and try again.",
                data={"retry_after_ms": 500},
            )

        cmd = args.get("cmd", "").strip()
        if not cmd:
            return ToolResult(
                ok=False, tool="execute_command", error="Command is required"
            )

        # Extract command prefix for allowlist check
        cmd_prefix = cmd.split()[0].upper() if cmd.split() else ""

        # Check if command is blocked
        if cmd_prefix in BLOCKED_COMMANDS:
            return ToolResult(
                ok=False,
                tool="execute_command",
                error=f"Command '{cmd_prefix}' is blocked for safety. Use the UI to execute ARM/DISARM/MOTOR commands.",
            )

        # Check if command is in allowlist
        is_safe = False
        for safe_cmd in SAFE_COMMANDS:
            if cmd.upper().startswith(safe_cmd):
                is_safe = True
                break

        if not is_safe:
            return ToolResult(
                ok=False,
                tool="execute_command",
                error=f"Command '{cmd_prefix}' is not in the safe command allowlist: {', '.join(sorted(SAFE_COMMANDS))}",
            )

        # Execute the command
        try:
            result = self.gateway.command(cmd, timeout=3.0)
            status = self.gateway.get_status()

            return ToolResult(
                ok=True,
                tool="execute_command",
                data={
                    "command": cmd,
                    "result": result,
                    "status_after": status,
                },
            )
        except Exception as e:
            return ToolResult(
                ok=False, tool="execute_command", error=f"Command failed: {e}"
            )

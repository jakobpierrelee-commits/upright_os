"""
Firmware Tools - AI agent tool implementations for firmware lifecycle.

Extracted from codex_tools.py for domain organization.
Tools: edit_sketch_value, read_sketch, generate_sketch, compile_firmware, upload_firmware
"""

from __future__ import annotations

import logging
import re
import secrets
import time
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from app.bridge.domains.ai_agent.tool_constants import (
        ToolResult,
        SAFE_SKETCH_VARIABLES,
        BLOCKED_SKETCH_VARIABLES,
    )
except ImportError:
    from domains.ai_agent.tool_constants import (  # type: ignore
        ToolResult,
        SAFE_SKETCH_VARIABLES,
        BLOCKED_SKETCH_VARIABLES,
    )

logger = logging.getLogger(__name__)


class FirmwareTools:
    """Firmware-related tool implementations."""

    def __init__(
        self,
        firmware_module: Any = None,
        repo_root: Optional[Path] = None,
        active_sketch_path: Optional[str] = None,
        board_fqbn: Optional[str] = None,
        port: Optional[str] = None,
    ):
        self.firmware = firmware_module
        self.repo_root = repo_root or Path(__file__).parent.parent.parent.parent
        self.active_sketch_path = active_sketch_path
        self.board_fqbn = board_fqbn or "arduino:avr:nano"
        self.port = port

        # Upload confirmation state
        self._pending_uploads: Dict[str, Dict[str, Any]] = {}
        self._upload_trust_window_s = 900
        self._upload_trust: Optional[Dict[str, Any]] = None

    def _build_upload_signature(
        self, sketch_path: str, board: str, port: Optional[str]
    ) -> str:
        sketch_norm = str(Path(sketch_path).resolve()) if sketch_path else ""
        board_norm = (board or "").strip()
        port_norm = (port or "").strip()
        return f"{sketch_norm}|{board_norm}|{port_norm}"

    def _is_upload_trusted(self, signature: str) -> bool:
        if not self._upload_trust:
            return False
        if self._upload_trust.get("signature") != signature:
            return False
        return time.time() < float(self._upload_trust.get("expires_at", 0))

    def _grant_upload_trust(
        self, sketch_path: str, board: str, port: Optional[str]
    ) -> None:
        now = time.time()
        self._upload_trust = {
            "signature": self._build_upload_signature(sketch_path, board, port),
            "granted_at": now,
            "expires_at": now + self._upload_trust_window_s,
        }

    def edit_sketch_value(self, args: Dict[str, Any]) -> ToolResult:
        """Edit a compile-time constant in sketch with allowlist enforcement."""
        variable = args.get("variable", "")
        value = args.get("value", "")
        sketch_path = args.get("sketch_path", self.active_sketch_path)

        if not variable or not value:
            return ToolResult(
                ok=False,
                tool="edit_sketch_value",
                error="variable and value are required",
            )

        # Check allowlist
        if variable not in SAFE_SKETCH_VARIABLES:
            for blocked in BLOCKED_SKETCH_VARIABLES:
                if variable.upper().startswith(blocked):
                    return ToolResult(
                        ok=False,
                        tool="edit_sketch_value",
                        error=f"Variable '{variable}' is blocked (matches pattern '{blocked}'). Cannot edit pin assignments or mode constants.",
                    )
            return ToolResult(
                ok=False,
                tool="edit_sketch_value",
                error=f"Variable '{variable}' is not in allowlist: {', '.join(sorted(SAFE_SKETCH_VARIABLES))}",
            )

        if not sketch_path:
            return ToolResult(
                ok=False, tool="edit_sketch_value", error="No sketch path configured"
            )

        sketch_dir = Path(sketch_path)
        if not sketch_dir.exists():
            sketch_dir = self.repo_root / sketch_path

        ino_files = list(sketch_dir.glob("*.ino"))
        if not ino_files:
            return ToolResult(
                ok=False,
                tool="edit_sketch_value",
                error=f"No .ino file found in {sketch_path}",
            )

        ino_path = ino_files[0]

        try:
            content = ino_path.read_text(encoding="utf-8")
            if not content.strip():
                return ToolResult(
                    ok=False,
                    tool="edit_sketch_value",
                    error=f"Sketch file is empty: {ino_path}",
                )
            original_content = content

            # Pattern matching for different variable styles
            struct_pattern = rf"(\.{re.escape(variable)}\s*=\s*)([^,;]+)([,;])"
            struct_match = re.search(struct_pattern, content)

            define_pattern = rf"(#define\s+{re.escape(variable)}\s+)(\S+)"
            define_match = re.search(define_pattern, content)

            const_pattern = rf"((?:const\s+)?(?:float|int|uint\d+_t|int\d+_t)\s+{re.escape(variable)}\s*=\s*)([^;]+)(;)"
            const_match = re.search(const_pattern, content)

            old_value = None
            if struct_match:
                old_value = struct_match.group(2).strip()
                content = re.sub(struct_pattern, rf"\g<1>{value}\g<3>", content)
            elif define_match:
                old_value = define_match.group(2).strip()
                content = re.sub(define_pattern, rf"\g<1>{value}", content)
            elif const_match:
                old_value = const_match.group(2).strip()
                content = re.sub(const_pattern, rf"\g<1>{value}\g<3>", content)
            else:
                return ToolResult(
                    ok=False,
                    tool="edit_sketch_value",
                    error=f"Variable '{variable}' not found in sketch.",
                )

            if content == original_content:
                return ToolResult(
                    ok=False,
                    tool="edit_sketch_value",
                    error=f"No changes made. Value may already be '{value}'.",
                )

            ino_path.write_text(content, encoding="utf-8")

            return ToolResult(
                ok=True,
                tool="edit_sketch_value",
                data={
                    "variable": variable,
                    "old_value": old_value,
                    "new_value": value,
                    "file": str(ino_path),
                    "requires_recompile": True,
                },
            )

        except Exception as e:
            return ToolResult(
                ok=False, tool="edit_sketch_value", error=f"Edit failed: {e}"
            )

    def read_sketch(self, args: Dict[str, Any]) -> ToolResult:
        """Read current sketch source for inspection."""
        sketch_path = args.get("sketch_path", self.active_sketch_path)
        max_chars = int(args.get("max_chars", 12000) or 12000)
        max_chars = max(500, min(max_chars, 50000))

        if not sketch_path:
            return ToolResult(
                ok=False, tool="read_sketch", error="No sketch path configured"
            )

        try:
            path = Path(sketch_path)
            if not path.exists():
                path = self.repo_root / str(sketch_path)
            if not path.exists():
                return ToolResult(
                    ok=False,
                    tool="read_sketch",
                    error=f"Sketch path not found: {sketch_path}",
                )

            ino_path: Optional[Path] = None
            if path.is_file():
                if path.suffix.lower() != ".ino":
                    return ToolResult(
                        ok=False,
                        tool="read_sketch",
                        error=f"Expected .ino file, got: {path.name}",
                    )
                ino_path = path
            else:
                ino_files = sorted(path.glob("*.ino"))
                if not ino_files:
                    return ToolResult(
                        ok=False,
                        tool="read_sketch",
                        error=f"No .ino file found in {path}",
                    )
                ino_path = ino_files[0]

            content = ino_path.read_text(encoding="utf-8")
            if not content.strip():
                return ToolResult(
                    ok=False,
                    tool="read_sketch",
                    error=f"Sketch file is empty: {ino_path}",
                )
            truncated = len(content) > max_chars
            if truncated:
                content = content[:max_chars]

            return ToolResult(
                ok=True,
                tool="read_sketch",
                data={
                    "path": str(ino_path),
                    "content": content,
                    "chars": len(content),
                    "truncated": truncated,
                },
            )
        except Exception as e:
            return ToolResult(ok=False, tool="read_sketch", error=f"Read failed: {e}")

    def compile_firmware(self, args: Dict[str, Any]) -> ToolResult:
        """Compile firmware sketch."""
        sketch_path = args.get("sketch_path", self.active_sketch_path)
        board = args.get("board", self.board_fqbn)

        if not sketch_path:
            return ToolResult(
                ok=False, tool="compile_firmware", error="No sketch path specified"
            )

        if not self.firmware:
            return ToolResult(
                ok=False,
                tool="compile_firmware",
                error="Firmware module not configured",
            )

        try:
            result = self.firmware.compile(sketch=sketch_path, fqbn=board)

            if result.get("ok"):
                return ToolResult(
                    ok=True,
                    tool="compile_firmware",
                    data={
                        "sketch": sketch_path,
                        "board": board,
                        "output": result.get("output", ""),
                        "binary_path": result.get("binary_path"),
                        "message": "Compilation successful. Use upload_firmware to flash to robot.",
                    },
                )
            else:
                return ToolResult(
                    ok=False,
                    tool="compile_firmware",
                    error=f"Compilation failed: {result.get('error', 'Unknown error')}",
                    data={"output": result.get("output", "")},
                )
        except Exception as e:
            return ToolResult(
                ok=False, tool="compile_firmware", error=f"Compile error: {e}"
            )

    def upload_firmware(self, args: Dict[str, Any]) -> ToolResult:
        """Upload firmware with confirmation gate."""
        sketch_path = args.get("sketch_path", self.active_sketch_path)
        confirmation_token = args.get("confirmation_token")
        board = args.get("board", self.board_fqbn)
        port = args.get("port", self.port)

        if not sketch_path:
            return ToolResult(
                ok=False, tool="upload_firmware", error="No sketch path specified"
            )

        signature = self._build_upload_signature(sketch_path, board, port)

        # If no confirmation token, check trust or request confirmation
        if not confirmation_token:
            if self._is_upload_trusted(signature):
                return self._do_upload(sketch_path, board, port, "trusted window")

            token = secrets.token_hex(16)
            self._pending_uploads[token] = {
                "sketch_path": sketch_path,
                "board": board,
                "port": port,
                "signature": signature,
                "created_at": time.time(),
            }

            return ToolResult(
                ok=False,
                tool="upload_firmware",
                error="CONFIRMATION_REQUIRED",
                data={
                    "confirmation_token": token,
                    "sketch_path": sketch_path,
                    "board": board,
                    "port": port,
                    "message": "Upload requires user confirmation.",
                    "expires_in_s": 300,
                },
            )

        # Validate confirmation token
        if confirmation_token not in self._pending_uploads:
            return ToolResult(
                ok=False,
                tool="upload_firmware",
                error="Invalid or expired confirmation token.",
            )

        pending = self._pending_uploads.pop(confirmation_token)

        if time.time() - pending["created_at"] > 300:
            return ToolResult(
                ok=False,
                tool="upload_firmware",
                error="Confirmation token expired.",
            )

        self._grant_upload_trust(
            pending["sketch_path"], pending["board"], pending["port"]
        )
        return self._do_upload(
            pending["sketch_path"], pending["board"], pending["port"], "confirmed"
        )

    def _do_upload(
        self, sketch_path: str, board: str, port: Optional[str], source: str
    ) -> ToolResult:
        """Execute the actual upload."""
        if not self.firmware:
            return ToolResult(
                ok=False, tool="upload_firmware", error="Firmware module not configured"
            )

        try:
            result = self.firmware.upload(sketch=sketch_path, fqbn=board, port=port)

            if result.get("ok"):
                return ToolResult(
                    ok=True,
                    tool="upload_firmware",
                    data={
                        "sketch": sketch_path,
                        "board": board,
                        "port": port,
                        "output": result.get("output", ""),
                        "message": f"Upload successful ({source}).",
                    },
                )
            else:
                return ToolResult(
                    ok=False,
                    tool="upload_firmware",
                    error=f"Upload failed: {result.get('error', 'Unknown error')}",
                    data={"output": result.get("output", "")},
                )
        except Exception as e:
            return ToolResult(
                ok=False, tool="upload_firmware", error=f"Upload error: {e}"
            )

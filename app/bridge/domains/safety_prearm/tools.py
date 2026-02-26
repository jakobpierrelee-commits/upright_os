"""
Safety/Prearm Tools - AI agent tool implementations for config diff and rollback.

Extracted from codex_tools.py for domain organization.
Tools: diff_config, safe_rollback
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

try:
    from app.bridge.domains.ai_agent.tool_constants import (
        ToolResult,
        T1Errors,
        T2Errors,
        FACTORY_DEFAULTS,
        RATING_HIERARCHY,
    )
except ImportError:
    from domains.ai_agent.tool_constants import (  # type: ignore
        ToolResult,
        T1Errors,
        T2Errors,
        FACTORY_DEFAULTS,
        RATING_HIERARCHY,
    )


class SafetyTools:
    """Safety, config diff, and rollback tool implementations."""

    def __init__(
        self,
        gateway: Any = None,
        db: Any = None,
        active_robot_id: Optional[str] = None,
        observe_telemetry_fn: Optional[Callable] = None,
    ):
        self.gateway = gateway
        self.db = db
        self.active_robot_id = active_robot_id or "default"
        self._observe_telemetry = observe_telemetry_fn

    def diff_config(self, args: Dict[str, Any]) -> ToolResult:
        """Compare current runtime configuration to a checkpoint or baseline."""
        compare_to = args.get("compare_to", "checkpoint")
        checkpoint_id = args.get("checkpoint_id")

        if not self.gateway:
            return ToolResult(
                ok=False,
                tool="diff_config",
                error=T2Errors.E_NO_DB,
                data={"message": "Gateway not configured, cannot read current config"},
            )

        try:
            current_status = self.gateway.get_status()
            if not current_status:
                return ToolResult(
                    ok=False,
                    tool="diff_config",
                    error=T1Errors.E_SERIAL_DISCONNECTED,
                    data={"message": "Could not read current config from robot"},
                )
        except Exception as e:
            return ToolResult(
                ok=False,
                tool="diff_config",
                error=T1Errors.E_SERIAL_DISCONNECTED,
                data={"message": f"Failed to read config: {e}"},
            )

        current_config = {
            "kp": float(current_status.get("kp", 0)),
            "ki": float(current_status.get("ki", 0)),
            "kd": float(current_status.get("kd", 0)),
            "setpoint": float(
                current_status.get("set", current_status.get("setpoint", 0))
            ),
        }

        reference_config: Dict[str, float] = {}
        reference_meta: Dict[str, Any] = {}

        if compare_to == "factory":
            reference_config = FACTORY_DEFAULTS.copy()
            reference_meta = {"source": "factory", "description": "Factory defaults"}

        elif compare_to == "checkpoint":
            if not self.db:
                return ToolResult(
                    ok=False,
                    tool="diff_config",
                    error=T2Errors.E_NO_DB,
                    data={"message": "Database not configured for checkpoint lookup"},
                )

            try:
                if checkpoint_id:
                    checkpoints = self.db.query_checkpoints(
                        robot_id=self.active_robot_id, limit=100
                    )
                    checkpoint = next(
                        (c for c in checkpoints if c.id == checkpoint_id), None
                    )
                else:
                    for rating in RATING_HIERARCHY:
                        checkpoints = self.db.query_checkpoints(
                            robot_id=self.active_robot_id,
                            min_rating=rating,
                            limit=1,
                        )
                        if checkpoints:
                            checkpoint = checkpoints[0]
                            break
                    else:
                        checkpoint = None

                if not checkpoint:
                    return ToolResult(
                        ok=False,
                        tool="diff_config",
                        error=T2Errors.E_NO_CHECKPOINT,
                        data={"message": "No checkpoint found matching criteria"},
                    )

                reference_config = {
                    "kp": checkpoint.kp,
                    "ki": checkpoint.ki,
                    "kd": checkpoint.kd,
                    "setpoint": getattr(checkpoint, "setpoint", 0.0),
                }
                reference_meta = {
                    "source": "checkpoint",
                    "checkpoint_id": checkpoint.id,
                    "checkpoint_rating": checkpoint.rating,
                    "checkpoint_ts": checkpoint.ts,
                }
            except Exception as e:
                return ToolResult(
                    ok=False,
                    tool="diff_config",
                    error=T2Errors.E_NO_CHECKPOINT,
                    data={"message": f"Checkpoint lookup failed: {e}"},
                )

        elif compare_to == "session_start":
            reference_config = FACTORY_DEFAULTS.copy()
            reference_meta = {
                "source": "session_start",
                "note": "Using factory defaults as session_start fallback",
            }
        else:
            return ToolResult(
                ok=False,
                tool="diff_config",
                error=T2Errors.E_INVALID_CHANGE,
                data={"message": f"Unknown compare_to value: {compare_to}"},
            )

        # Compute diffs
        diffs: List[Dict[str, Any]] = []
        identical: List[str] = []

        for param in ["kp", "ki", "kd", "setpoint"]:
            current_val = current_config.get(param, 0)
            ref_val = reference_config.get(param, 0)

            if abs(current_val - ref_val) < 0.0001:
                identical.append(param)
            else:
                delta_abs = current_val - ref_val
                delta_pct = (
                    f"{delta_abs / ref_val * 100:+.0f}%"
                    if ref_val != 0
                    else f"+{delta_abs}"
                )
                diffs.append(
                    {
                        "param": param,
                        "current": current_val,
                        "reference": ref_val,
                        "delta": delta_pct,
                    }
                )

        if not diffs:
            summary = f"Configuration matches {compare_to}. No differences."
        else:
            changes = ", ".join(f"{d['param']}: {d['delta']}" for d in diffs)
            summary = f"{len(diffs)} parameter(s) differ from {compare_to}: {changes}"

        return ToolResult(
            ok=True,
            tool="diff_config",
            data={
                "compared_to": compare_to,
                **reference_meta,
                "diffs": diffs,
                "identical": identical,
                "summary": summary,
            },
        )

    def safe_rollback(self, args: Dict[str, Any]) -> ToolResult:
        """Revert to a checkpoint with specified minimum rating."""
        min_rating = args.get("min_rating", "good")
        scope = args.get("scope", "pid")
        checkpoint_id = args.get("checkpoint_id")
        dry_run = args.get("dry_run", False)

        if not self.db:
            return ToolResult(
                ok=False,
                tool="safe_rollback",
                error=T2Errors.E_NO_DB,
                data={"message": "Database not configured"},
            )

        if not self.gateway:
            return ToolResult(
                ok=False,
                tool="safe_rollback",
                error=T1Errors.E_SERIAL_DISCONNECTED,
                data={"message": "Gateway not configured"},
            )

        if hasattr(self.gateway, "is_busy") and self.gateway.is_busy():
            return ToolResult(
                ok=False,
                tool="safe_rollback",
                error=T2Errors.E_SERIAL_BUSY,
                data={"message": "Serial port busy, try again", "retry_after_ms": 500},
            )

        # Find matching checkpoint
        try:
            if checkpoint_id:
                checkpoints = self.db.query_checkpoints(
                    robot_id=self.active_robot_id, limit=100
                )
                checkpoint = next(
                    (c for c in checkpoints if c.id == checkpoint_id), None
                )
            else:
                rating_idx = (
                    RATING_HIERARCHY.index(min_rating)
                    if min_rating in RATING_HIERARCHY
                    else 1
                )
                for rating in RATING_HIERARCHY[: rating_idx + 1]:
                    checkpoints = self.db.query_checkpoints(
                        robot_id=self.active_robot_id,
                        min_rating=rating,
                        limit=1,
                    )
                    if checkpoints:
                        checkpoint = checkpoints[0]
                        break
                else:
                    checkpoint = None

            if not checkpoint:
                return ToolResult(
                    ok=False,
                    tool="safe_rollback",
                    error=T2Errors.E_NO_CHECKPOINT,
                    data={
                        "message": f"No checkpoint found with rating >= {min_rating}"
                    },
                )

        except Exception as e:
            return ToolResult(
                ok=False,
                tool="safe_rollback",
                error=T2Errors.E_NO_CHECKPOINT,
                data={"message": f"Checkpoint lookup failed: {e}"},
            )

        # Get current config for comparison
        try:
            current_status = self.gateway.get_status()
            current_kp = float(current_status.get("kp", 0))
            current_ki = float(current_status.get("ki", 0))
            current_kd = float(current_status.get("kd", 0))
        except Exception:
            current_kp = current_ki = current_kd = 0

        # Build commands based on scope
        commands: List[str] = []
        changes: List[Dict[str, Any]] = []

        if scope in ("pid", "all_runtime"):
            target_kp = checkpoint.kp
            target_ki = checkpoint.ki
            target_kd = checkpoint.kd

            if (
                abs(current_kp - target_kp) > 0.001
                or abs(current_ki - target_ki) > 0.001
                or abs(current_kd - target_kd) > 0.001
            ):
                commands.append(f"PID {target_kp} {target_ki} {target_kd}")
                if current_kp != target_kp:
                    changes.append({"param": "Kp", "from": current_kp, "to": target_kp})
                if current_ki != target_ki:
                    changes.append({"param": "Ki", "from": current_ki, "to": target_ki})
                if current_kd != target_kd:
                    changes.append({"param": "Kd", "from": current_kd, "to": target_kd})

        if dry_run:
            return ToolResult(
                ok=True,
                tool="safe_rollback",
                data={
                    "checkpoint_id": checkpoint.id,
                    "checkpoint_rating": checkpoint.rating,
                    "checkpoint_ts": checkpoint.ts,
                    "scope": scope,
                    "changes_preview": changes,
                    "commands_preview": commands,
                    "dry_run": True,
                    "summary": f"Would rollback {scope} to checkpoint '{checkpoint.id}' (rated {checkpoint.rating})",
                },
            )

        # Execute commands
        commands_sent: List[str] = []
        for cmd in commands:
            try:
                result = self.gateway.command(cmd)
                commands_sent.append(cmd)
                if not result.get("ok", True):
                    return ToolResult(
                        ok=False,
                        tool="safe_rollback",
                        error=T2Errors.E_COMMAND_FAILED,
                        data={
                            "message": f"Command failed: {cmd}",
                            "result": result,
                            "commands_sent": commands_sent,
                        },
                    )
            except Exception as e:
                return ToolResult(
                    ok=False,
                    tool="safe_rollback",
                    error=T2Errors.E_COMMAND_FAILED,
                    data={
                        "message": f"Command error: {e}",
                        "commands_sent": commands_sent,
                    },
                )

        change_strs = [f"{c['param']}: {c['from']}→{c['to']}" for c in changes]
        summary = f"Rolled back {scope} to checkpoint '{checkpoint.id}' (rated {checkpoint.rating}). {', '.join(change_strs)}"

        return ToolResult(
            ok=True,
            tool="safe_rollback",
            data={
                "checkpoint_id": checkpoint.id,
                "checkpoint_rating": checkpoint.rating,
                "checkpoint_ts": checkpoint.ts,
                "scope": scope,
                "changes_applied": changes,
                "commands_sent": commands_sent,
                "dry_run": False,
                "summary": summary,
            },
        )

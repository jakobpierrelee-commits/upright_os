"""
Session Tools - AI agent tool implementations for session/checkpoint management.

Extracted from codex_tools.py for domain organization.
Tools: query_checkpoints, search_docs, annotate_session
"""

from __future__ import annotations

from typing import Any, Dict, Optional

try:
    from app.bridge.domains.ai_agent.tool_constants import ToolResult
except ImportError:
    from domains.ai_agent.tool_constants import ToolResult  # type: ignore


class SessionTools:
    """Session and checkpoint tool implementations."""

    def __init__(
        self,
        db: Any = None,
        rag: Any = None,
        active_robot_id: Optional[str] = None,
    ):
        self.db = db
        self.rag = rag
        self.active_robot_id = active_robot_id or "default"

    def query_checkpoints(self, args: Dict[str, Any]) -> ToolResult:
        """Query checkpoints from database."""
        if not self.db:
            return ToolResult(
                ok=False, tool="query_checkpoints", error="Database not configured"
            )

        rating = args.get("rating")
        limit = args.get("limit", 10)

        checkpoints = self.db.query_checkpoints(
            robot_id=self.active_robot_id,
            rating=rating,
            limit=limit,
        )

        data = {
            "count": len(checkpoints),
            "checkpoints": [
                {
                    "id": c.id,
                    "ts": c.ts,
                    "rating": c.rating,
                    "mode": c.mode,
                    "pid": {"kp": c.kp, "ki": c.ki, "kd": c.kd},
                    "motion": {"kv": c.kv, "kx": c.kx},
                    "setpoint": c.setpoint,
                    "notes": c.notes,
                }
                for c in checkpoints
            ],
        }

        return ToolResult(ok=True, tool="query_checkpoints", data=data)

    def search_docs(self, args: Dict[str, Any]) -> ToolResult:
        """Search documentation via RAG."""
        if not self.rag:
            return ToolResult(ok=False, tool="search_docs", error="RAG not configured")

        query = args.get("query", "")
        k = args.get("k", 5)

        if not query:
            return ToolResult(ok=False, tool="search_docs", error="Query is required")

        results = self.rag.search_docs(query, k=k, min_score=0.4)

        data = {
            "count": len(results),
            "results": [
                {
                    "source": r.source_path,
                    "score": round(r.score, 3),
                    "content": r.content[:500] + "..."
                    if len(r.content) > 500
                    else r.content,
                }
                for r in results
            ],
        }

        return ToolResult(ok=True, tool="search_docs", data=data)

    def annotate_session(self, args: Dict[str, Any]) -> ToolResult:
        """Add annotation to current tuning session."""
        if not self.db:
            return ToolResult(
                ok=False, tool="annotate_session", error="Database not configured"
            )

        note = args.get("note", "")
        category = args.get("category", "general")
        importance = args.get("importance", "normal")

        if not note:
            return ToolResult(
                ok=False, tool="annotate_session", error="Note is required"
            )

        try:
            annotation_id = self.db.add_session_annotation(
                robot_id=self.active_robot_id,
                note=note,
                category=category,
                importance=importance,
            )

            return ToolResult(
                ok=True,
                tool="annotate_session",
                data={
                    "annotation_id": annotation_id,
                    "note": note,
                    "category": category,
                    "importance": importance,
                },
            )
        except Exception as e:
            return ToolResult(
                ok=False,
                tool="annotate_session",
                error=f"Failed to save annotation: {e}",
            )

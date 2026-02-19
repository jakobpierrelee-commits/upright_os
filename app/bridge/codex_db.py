"""
Codex Database Module - SQLite storage for telemetry, checkpoints, and RAG embeddings.

Provides:
- Telemetry snapshots (1Hz samples from TelemetryHub)
- Checkpoints (user-rated tuning states)
- Doc chunks (for RAG retrieval)
- Size-based retention with priority for high-rated data

Target: 100MB cap with automatic pruning.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Default DB path relative to this file
DEFAULT_DB_PATH = Path(__file__).parent / "codex.db"

# Retention settings
MAX_DB_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB
PRUNE_BATCH_SIZE = 1000
TELEMETRY_DOWNSAMPLE_HZ = 1.0  # Target 1 sample per second

# Rating priority for retention (higher = keep longer)
RATING_PRIORITY = {
    "great": 4,
    "good": 3,
    "ok": 2,
    "poor": 1,
    None: 0,
}


@dataclass
class TelemetrySnapshot:
    id: Optional[int] = None
    ts: float = 0.0
    robot_id: str = ""
    mode: str = ""
    ang: float = 0.0
    raw: float = 0.0
    out: float = 0.0
    kp: float = 0.0
    ki: float = 0.0
    kd: float = 0.0
    kv: float = 0.0
    kx: float = 0.0
    setpoint: float = 0.0
    enc_l: int = 0
    enc_r: int = 0
    voltage: float = 0.0
    checkpoint_id: Optional[int] = None
    extra_json: str = "{}"


@dataclass
class Checkpoint:
    id: Optional[int] = None
    ts: float = 0.0
    robot_id: str = ""
    rating: Optional[str] = None  # 'poor', 'ok', 'good', 'great'
    mode: str = ""
    ang: float = 0.0
    kp: float = 0.0
    ki: float = 0.0
    kd: float = 0.0
    kv: float = 0.0
    kx: float = 0.0
    setpoint: float = 0.0
    notes: str = ""
    config_json: str = "{}"


@dataclass
class DocChunk:
    id: Optional[int] = None
    source_path: str = ""
    chunk_index: int = 0
    content: str = ""
    embedding_json: str = "[]"  # JSON array of floats
    created_at: float = 0.0
    token_count: int = 0


@dataclass
class EmbeddingMeta:
    id: Optional[int] = None
    source_path: str = ""
    file_hash: str = ""
    chunk_count: int = 0
    embedded_at: float = 0.0
    model: str = "text-embedding-3-small"


@dataclass
class ToolAudit:
    """Audit record for tool execution."""
    id: Optional[int] = None
    ts: float = 0.0
    tool: str = ""
    args_hash: str = ""
    ok: bool = False
    latency_ms: float = 0.0
    error: Optional[str] = None


class CodexDB:
    """Thread-safe SQLite database for Codex agent data."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self._local = threading.local()
        self._init_lock = threading.Lock()
        self._initialized = False
        self._last_telemetry_ts: Dict[str, float] = {}  # robot_id -> last sample ts

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                timeout=30.0,
            )
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn.execute("PRAGMA cache_size=-8000")  # 8MB cache
        return self._local.conn

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()

    def init_schema(self) -> None:
        """Initialize database schema. Safe to call multiple times."""
        with self._init_lock:
            if self._initialized:
                return

            with self._cursor() as cur:
                # Telemetry snapshots table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS telemetry_snapshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts REAL NOT NULL,
                        robot_id TEXT NOT NULL DEFAULT '',
                        mode TEXT NOT NULL DEFAULT '',
                        ang REAL NOT NULL DEFAULT 0.0,
                        raw REAL NOT NULL DEFAULT 0.0,
                        out REAL NOT NULL DEFAULT 0.0,
                        kp REAL NOT NULL DEFAULT 0.0,
                        ki REAL NOT NULL DEFAULT 0.0,
                        kd REAL NOT NULL DEFAULT 0.0,
                        kv REAL NOT NULL DEFAULT 0.0,
                        kx REAL NOT NULL DEFAULT 0.0,
                        setpoint REAL NOT NULL DEFAULT 0.0,
                        enc_l INTEGER NOT NULL DEFAULT 0,
                        enc_r INTEGER NOT NULL DEFAULT 0,
                        voltage REAL NOT NULL DEFAULT 0.0,
                        checkpoint_id INTEGER,
                        extra_json TEXT NOT NULL DEFAULT '{}',
                        FOREIGN KEY (checkpoint_id) REFERENCES checkpoints(id)
                    )
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_ts ON telemetry_snapshots(ts)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_robot ON telemetry_snapshots(robot_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_checkpoint ON telemetry_snapshots(checkpoint_id)")

                # Checkpoints table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS checkpoints (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts REAL NOT NULL,
                        robot_id TEXT NOT NULL DEFAULT '',
                        rating TEXT,
                        mode TEXT NOT NULL DEFAULT '',
                        ang REAL NOT NULL DEFAULT 0.0,
                        kp REAL NOT NULL DEFAULT 0.0,
                        ki REAL NOT NULL DEFAULT 0.0,
                        kd REAL NOT NULL DEFAULT 0.0,
                        kv REAL NOT NULL DEFAULT 0.0,
                        kx REAL NOT NULL DEFAULT 0.0,
                        setpoint REAL NOT NULL DEFAULT 0.0,
                        notes TEXT NOT NULL DEFAULT '',
                        config_json TEXT NOT NULL DEFAULT '{}'
                    )
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_checkpoints_ts ON checkpoints(ts)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_checkpoints_robot ON checkpoints(robot_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_checkpoints_rating ON checkpoints(rating)")

                # Doc chunks table (for RAG)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS doc_chunks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        source_path TEXT NOT NULL,
                        chunk_index INTEGER NOT NULL DEFAULT 0,
                        content TEXT NOT NULL,
                        embedding_json TEXT NOT NULL DEFAULT '[]',
                        created_at REAL NOT NULL,
                        token_count INTEGER NOT NULL DEFAULT 0
                    )
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_doc_chunks_source ON doc_chunks(source_path)")

                # Embeddings metadata table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS embeddings_meta (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        source_path TEXT NOT NULL UNIQUE,
                        file_hash TEXT NOT NULL,
                        chunk_count INTEGER NOT NULL DEFAULT 0,
                        embedded_at REAL NOT NULL,
                        model TEXT NOT NULL DEFAULT 'text-embedding-3-small'
                    )
                """)
                cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_embeddings_path ON embeddings_meta(source_path)")

                # Tool audit table (for observability)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS tool_audit (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts REAL NOT NULL,
                        tool TEXT NOT NULL,
                        args_hash TEXT NOT NULL DEFAULT '',
                        ok INTEGER NOT NULL DEFAULT 1,
                        latency_ms REAL NOT NULL DEFAULT 0.0,
                        error TEXT
                    )
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_tool_audit_ts ON tool_audit(ts)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_tool_audit_tool ON tool_audit(tool)")

            self._initialized = True
            logger.info(f"CodexDB schema initialized at {self.db_path}")

    # -------------------------------------------------------------------------
    # Telemetry Methods
    # -------------------------------------------------------------------------

    def should_sample_telemetry(self, robot_id: str) -> bool:
        """Check if enough time has passed to log another telemetry sample (1Hz target)."""
        now = time.time()
        last_ts = self._last_telemetry_ts.get(robot_id, 0.0)
        interval = 1.0 / TELEMETRY_DOWNSAMPLE_HZ
        return (now - last_ts) >= interval

    def log_telemetry(self, snapshot: TelemetrySnapshot) -> Optional[int]:
        """
        Log a telemetry snapshot. Respects downsampling rate.
        Returns inserted ID or None if skipped.
        """
        if not self.should_sample_telemetry(snapshot.robot_id):
            return None

        self._last_telemetry_ts[snapshot.robot_id] = snapshot.ts or time.time()

        with self._cursor() as cur:
            cur.execute("""
                INSERT INTO telemetry_snapshots 
                (ts, robot_id, mode, ang, raw, out, kp, ki, kd, kv, kx, 
                 setpoint, enc_l, enc_r, voltage, checkpoint_id, extra_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                snapshot.ts or time.time(),
                snapshot.robot_id,
                snapshot.mode,
                snapshot.ang,
                snapshot.raw,
                snapshot.out,
                snapshot.kp,
                snapshot.ki,
                snapshot.kd,
                snapshot.kv,
                snapshot.kx,
                snapshot.setpoint,
                snapshot.enc_l,
                snapshot.enc_r,
                snapshot.voltage,
                snapshot.checkpoint_id,
                snapshot.extra_json,
            ))
            return cur.lastrowid

    def query_telemetry(
        self,
        robot_id: Optional[str] = None,
        start_ts: Optional[float] = None,
        end_ts: Optional[float] = None,
        limit: int = 1000,
    ) -> List[TelemetrySnapshot]:
        """Query telemetry snapshots with filters."""
        conditions = []
        params: List[Any] = []

        if robot_id:
            conditions.append("robot_id = ?")
            params.append(robot_id)
        if start_ts is not None:
            conditions.append("ts >= ?")
            params.append(start_ts)
        if end_ts is not None:
            conditions.append("ts <= ?")
            params.append(end_ts)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        with self._cursor() as cur:
            cur.execute(f"""
                SELECT * FROM telemetry_snapshots
                {where_clause}
                ORDER BY ts DESC
                LIMIT ?
            """, (*params, limit))

            return [self._row_to_telemetry(row) for row in cur.fetchall()]

    def _row_to_telemetry(self, row: sqlite3.Row) -> TelemetrySnapshot:
        return TelemetrySnapshot(
            id=row["id"],
            ts=row["ts"],
            robot_id=row["robot_id"],
            mode=row["mode"],
            ang=row["ang"],
            raw=row["raw"],
            out=row["out"],
            kp=row["kp"],
            ki=row["ki"],
            kd=row["kd"],
            kv=row["kv"],
            kx=row["kx"],
            setpoint=row["setpoint"],
            enc_l=row["enc_l"],
            enc_r=row["enc_r"],
            voltage=row["voltage"],
            checkpoint_id=row["checkpoint_id"],
            extra_json=row["extra_json"],
        )

    # -------------------------------------------------------------------------
    # Checkpoint Methods
    # -------------------------------------------------------------------------

    def save_checkpoint(self, checkpoint: Checkpoint) -> int:
        """Save a checkpoint and return its ID."""
        with self._cursor() as cur:
            cur.execute("""
                INSERT INTO checkpoints 
                (ts, robot_id, rating, mode, ang, kp, ki, kd, kv, kx, setpoint, notes, config_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                checkpoint.ts or time.time(),
                checkpoint.robot_id,
                checkpoint.rating,
                checkpoint.mode,
                checkpoint.ang,
                checkpoint.kp,
                checkpoint.ki,
                checkpoint.kd,
                checkpoint.kv,
                checkpoint.kx,
                checkpoint.setpoint,
                checkpoint.notes,
                checkpoint.config_json,
            ))
            return cur.lastrowid  # type: ignore

    def query_checkpoints(
        self,
        robot_id: Optional[str] = None,
        rating: Optional[str] = None,
        limit: int = 100,
    ) -> List[Checkpoint]:
        """Query checkpoints with filters."""
        conditions = []
        params: List[Any] = []

        if robot_id:
            conditions.append("robot_id = ?")
            params.append(robot_id)
        if rating:
            conditions.append("rating = ?")
            params.append(rating)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        with self._cursor() as cur:
            cur.execute(f"""
                SELECT * FROM checkpoints
                {where_clause}
                ORDER BY ts DESC
                LIMIT ?
            """, (*params, limit))

            return [self._row_to_checkpoint(row) for row in cur.fetchall()]

    def get_checkpoint(self, checkpoint_id: int) -> Optional[Checkpoint]:
        """Get a single checkpoint by ID."""
        with self._cursor() as cur:
            cur.execute("SELECT * FROM checkpoints WHERE id = ?", (checkpoint_id,))
            row = cur.fetchone()
            return self._row_to_checkpoint(row) if row else None

    def _row_to_checkpoint(self, row: sqlite3.Row) -> Checkpoint:
        return Checkpoint(
            id=row["id"],
            ts=row["ts"],
            robot_id=row["robot_id"],
            rating=row["rating"],
            mode=row["mode"],
            ang=row["ang"],
            kp=row["kp"],
            ki=row["ki"],
            kd=row["kd"],
            kv=row["kv"],
            kx=row["kx"],
            setpoint=row["setpoint"],
            notes=row["notes"],
            config_json=row["config_json"],
        )

    # -------------------------------------------------------------------------
    # Doc Chunks Methods (for RAG)
    # -------------------------------------------------------------------------

    def save_doc_chunks(self, chunks: List[DocChunk]) -> int:
        """Save multiple doc chunks. Returns count inserted."""
        if not chunks:
            return 0

        with self._cursor() as cur:
            cur.executemany("""
                INSERT INTO doc_chunks 
                (source_path, chunk_index, content, embedding_json, created_at, token_count)
                VALUES (?, ?, ?, ?, ?, ?)
            """, [
                (c.source_path, c.chunk_index, c.content, c.embedding_json, c.created_at or time.time(), c.token_count)
                for c in chunks
            ])
            return len(chunks)

    def delete_doc_chunks(self, source_path: str) -> int:
        """Delete all chunks for a source path. Returns count deleted."""
        with self._cursor() as cur:
            cur.execute("DELETE FROM doc_chunks WHERE source_path = ?", (source_path,))
            return cur.rowcount

    def get_all_chunks_with_embeddings(self) -> List[DocChunk]:
        """Get all doc chunks that have embeddings (for search)."""
        with self._cursor() as cur:
            cur.execute("""
                SELECT * FROM doc_chunks 
                WHERE embedding_json != '[]'
                ORDER BY source_path, chunk_index
            """)
            return [self._row_to_doc_chunk(row) for row in cur.fetchall()]

    def _row_to_doc_chunk(self, row: sqlite3.Row) -> DocChunk:
        return DocChunk(
            id=row["id"],
            source_path=row["source_path"],
            chunk_index=row["chunk_index"],
            content=row["content"],
            embedding_json=row["embedding_json"],
            created_at=row["created_at"],
            token_count=row["token_count"],
        )

    # -------------------------------------------------------------------------
    # Embeddings Meta Methods
    # -------------------------------------------------------------------------

    def get_embedding_meta(self, source_path: str) -> Optional[EmbeddingMeta]:
        """Get embedding metadata for a source path."""
        with self._cursor() as cur:
            cur.execute("SELECT * FROM embeddings_meta WHERE source_path = ?", (source_path,))
            row = cur.fetchone()
            return self._row_to_embedding_meta(row) if row else None

    def save_embedding_meta(self, meta: EmbeddingMeta) -> int:
        """Save or update embedding metadata. Returns ID."""
        with self._cursor() as cur:
            cur.execute("""
                INSERT INTO embeddings_meta (source_path, file_hash, chunk_count, embedded_at, model)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source_path) DO UPDATE SET
                    file_hash = excluded.file_hash,
                    chunk_count = excluded.chunk_count,
                    embedded_at = excluded.embedded_at,
                    model = excluded.model
            """, (
                meta.source_path,
                meta.file_hash,
                meta.chunk_count,
                meta.embedded_at or time.time(),
                meta.model,
            ))
            return cur.lastrowid  # type: ignore

    def _row_to_embedding_meta(self, row: sqlite3.Row) -> EmbeddingMeta:
        return EmbeddingMeta(
            id=row["id"],
            source_path=row["source_path"],
            file_hash=row["file_hash"],
            chunk_count=row["chunk_count"],
            embedded_at=row["embedded_at"],
            model=row["model"],
        )

    # -------------------------------------------------------------------------
    # Size Management & Retention
    # -------------------------------------------------------------------------

    def get_db_size_bytes(self) -> int:
        """Get current database file size in bytes."""
        try:
            return self.db_path.stat().st_size
        except FileNotFoundError:
            return 0

    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        with self._cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM telemetry_snapshots")
            telemetry_count = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM checkpoints")
            checkpoint_count = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM doc_chunks")
            chunk_count = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM embeddings_meta")
            embedded_docs_count = cur.fetchone()[0]
            cur.execute("SELECT MAX(embedded_at) FROM embeddings_meta")
            latest_embedding_ts = cur.fetchone()[0]

            # Tool audit count
            try:
                cur.execute("SELECT COUNT(*) FROM tool_audit")
                tool_audit_count = cur.fetchone()[0]
            except Exception:
                tool_audit_count = 0

        return {
            "db_size_bytes": self.get_db_size_bytes(),
            "db_size_mb": round(self.get_db_size_bytes() / (1024 * 1024), 2),
            "max_size_mb": MAX_DB_SIZE_BYTES / (1024 * 1024),
            "telemetry_count": telemetry_count,
            "checkpoint_count": checkpoint_count,
            "doc_chunk_count": chunk_count,
            "embedded_docs_count": embedded_docs_count,
            "latest_embedding_ts": float(latest_embedding_ts) if latest_embedding_ts is not None else None,
            "tool_audit_count": tool_audit_count,
        }

    def prune_if_needed(self) -> Dict[str, int]:
        """
        Prune old data if DB exceeds size limit.
        Priority: keep checkpoints with good/great ratings longer.
        Returns dict with counts of pruned items.
        """
        current_size = self.get_db_size_bytes()
        if current_size <= MAX_DB_SIZE_BYTES:
            return {"telemetry_pruned": 0, "checkpoints_pruned": 0}

        logger.info(f"CodexDB pruning: {current_size / (1024*1024):.1f}MB > {MAX_DB_SIZE_BYTES / (1024*1024):.0f}MB limit")

        pruned = {"telemetry_pruned": 0, "checkpoints_pruned": 0}
        target_size = int(MAX_DB_SIZE_BYTES * 0.8)  # Prune to 80% of limit

        # Phase 1: Prune telemetry not linked to checkpoints (oldest first)
        while self.get_db_size_bytes() > target_size:
            with self._cursor() as cur:
                cur.execute("""
                    DELETE FROM telemetry_snapshots
                    WHERE id IN (
                        SELECT id FROM telemetry_snapshots
                        WHERE checkpoint_id IS NULL
                        ORDER BY ts ASC
                        LIMIT ?
                    )
                """, (PRUNE_BATCH_SIZE,))
                deleted = cur.rowcount
                if deleted == 0:
                    break
                pruned["telemetry_pruned"] += deleted
                logger.debug(f"Pruned {deleted} unlinked telemetry rows")

        # Phase 2: Prune telemetry linked to low-rated checkpoints
        for rating in [None, "poor", "ok"]:
            while self.get_db_size_bytes() > target_size:
                with self._cursor() as cur:
                    cur.execute("""
                        DELETE FROM telemetry_snapshots
                        WHERE id IN (
                            SELECT t.id FROM telemetry_snapshots t
                            JOIN checkpoints c ON t.checkpoint_id = c.id
                            WHERE c.rating IS ? OR c.rating = ?
                            ORDER BY t.ts ASC
                            LIMIT ?
                        )
                    """, (rating, rating, PRUNE_BATCH_SIZE))
                    deleted = cur.rowcount
                    if deleted == 0:
                        break
                    pruned["telemetry_pruned"] += deleted

        # Phase 3: Prune checkpoints with low ratings (keep good/great)
        for rating in [None, "poor", "ok"]:
            while self.get_db_size_bytes() > target_size:
                with self._cursor() as cur:
                    cur.execute("""
                        DELETE FROM checkpoints
                        WHERE id IN (
                            SELECT id FROM checkpoints
                            WHERE rating IS ? OR rating = ?
                            ORDER BY ts ASC
                            LIMIT ?
                        )
                    """, (rating, rating, PRUNE_BATCH_SIZE // 10))
                    deleted = cur.rowcount
                    if deleted == 0:
                        break
                    pruned["checkpoints_pruned"] += deleted

        # Vacuum to reclaim space
        self._get_conn().execute("VACUUM")

        logger.info(f"CodexDB pruning complete: {pruned}")
        return pruned

    # -------------------------------------------------------------------------
    # Tool Audit Methods
    # -------------------------------------------------------------------------

    def log_tool_audit(
        self,
        tool: str,
        args_hash: str,
        ok: bool,
        latency_ms: float,
        error: Optional[str] = None,
    ) -> Optional[int]:
        """Log a tool execution audit record. Returns inserted ID."""
        with self._cursor() as cur:
            cur.execute("""
                INSERT INTO tool_audit (ts, tool, args_hash, ok, latency_ms, error)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                time.time(),
                tool,
                args_hash,
                1 if ok else 0,
                latency_ms,
                error,
            ))
            return cur.lastrowid

    def get_tool_metrics(
        self,
        since_ts: Optional[float] = None,
        tool_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get aggregate metrics for tool executions.
        
        Returns safe aggregate counters (no sensitive data).
        """
        conditions = []
        params: List[Any] = []

        if since_ts is not None:
            conditions.append("ts >= ?")
            params.append(since_ts)
        if tool_filter:
            conditions.append("tool = ?")
            params.append(tool_filter)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        # Build clauses that include ok filter
        ok_1_clause = f"{where_clause} AND ok = 1" if where_clause else "WHERE ok = 1"
        ok_0_clause = f"{where_clause} AND ok = 0" if where_clause else "WHERE ok = 0"

        with self._cursor() as cur:
            # Total counts
            cur.execute(f"SELECT COUNT(*) FROM tool_audit {where_clause}", params)
            total_calls = cur.fetchone()[0]

            cur.execute(f"SELECT COUNT(*) FROM tool_audit {ok_1_clause}", params)
            success_calls = cur.fetchone()[0]

            cur.execute(f"SELECT COUNT(*) FROM tool_audit {ok_0_clause}", params)
            failed_calls = cur.fetchone()[0]

            # Average latency
            cur.execute(f"SELECT AVG(latency_ms) FROM tool_audit {where_clause}", params)
            avg_latency = cur.fetchone()[0] or 0.0

            # Per-tool breakdown
            cur.execute(f"""
                SELECT tool, COUNT(*) as cnt, SUM(ok) as successes, AVG(latency_ms) as avg_lat
                FROM tool_audit {where_clause}
                GROUP BY tool
                ORDER BY cnt DESC
                LIMIT 20
            """, params)
            per_tool = [
                {
                    "tool": row[0],
                    "calls": row[1],
                    "successes": row[2] or 0,
                    "failures": row[1] - (row[2] or 0),
                    "avg_latency_ms": round(row[3] or 0.0, 2),
                }
                for row in cur.fetchall()
            ]

            # Recent errors (last 10, redacted)
            error_where = f"{where_clause} AND ok = 0 AND error IS NOT NULL" if where_clause else "WHERE ok = 0 AND error IS NOT NULL"
            cur.execute(f"""
                SELECT tool, error, ts FROM tool_audit
                {error_where}
                ORDER BY ts DESC
                LIMIT 10
            """, params)
            recent_errors = [
                {
                    "tool": row[0],
                    "error": row[1][:100] if row[1] else None,  # Truncate for safety
                    "ts": row[2],
                }
                for row in cur.fetchall()
            ]

        return {
            "total_calls": total_calls,
            "success_calls": success_calls,
            "failed_calls": failed_calls,
            "success_rate": round(success_calls / total_calls, 4) if total_calls > 0 else 1.0,
            "avg_latency_ms": round(avg_latency, 2),
            "per_tool": per_tool,
            "recent_errors": recent_errors,
        }

    def prune_tool_audit(self, max_age_days: int = 7) -> int:
        """Prune old tool audit records. Returns count deleted."""
        cutoff_ts = time.time() - (max_age_days * 24 * 60 * 60)
        with self._cursor() as cur:
            cur.execute("DELETE FROM tool_audit WHERE ts < ?", (cutoff_ts,))
            return cur.rowcount

    def close(self) -> None:
        """Close the database connection for this thread."""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None


# Module-level singleton for convenience
_default_db: Optional[CodexDB] = None


def get_codex_db(db_path: Optional[Path] = None) -> CodexDB:
    """Get or create the default CodexDB instance."""
    global _default_db
    if _default_db is None:
        _default_db = CodexDB(db_path)
        _default_db.init_schema()
    return _default_db

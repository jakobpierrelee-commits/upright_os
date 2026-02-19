"""
Validation tests for codex_db.py - Phase A Foundation

Run with: python -m pytest app/bridge/tests/test_codex_db.py -v
Or standalone: python app/bridge/tests/test_codex_db.py
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from codex_db import (
    CodexDB,
    TelemetrySnapshot,
    Checkpoint,
    DocChunk,
    EmbeddingMeta,
    RATING_PRIORITY,
    MAX_DB_SIZE_BYTES,
)


def test_schema_init():
    """Test that schema initializes correctly."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    try:
        db = CodexDB(db_path)
        db.init_schema()

        # Verify tables exist
        conn = db._get_conn()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]

        assert "telemetry_snapshots" in tables, "telemetry_snapshots table missing"
        assert "checkpoints" in tables, "checkpoints table missing"
        assert "doc_chunks" in tables, "doc_chunks table missing"
        assert "embeddings_meta" in tables, "embeddings_meta table missing"

        print("✓ Schema initialization passed")
    finally:
        db.close()
        db_path.unlink(missing_ok=True)


def test_telemetry_logging():
    """Test telemetry snapshot logging with downsampling."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    try:
        db = CodexDB(db_path)
        db.init_schema()

        # First sample should always be logged
        snap1 = TelemetrySnapshot(
            ts=time.time(),
            robot_id="test_robot",
            mode="BALANCING",
            ang=1.5,
            raw=1.6,
            out=50.0,
            kp=18.0,
            ki=0.1,
            kd=0.6,
        )
        id1 = db.log_telemetry(snap1)
        assert id1 is not None, "First telemetry sample should be logged"

        # Immediate second sample should be skipped (downsample)
        snap2 = TelemetrySnapshot(
            ts=time.time(),
            robot_id="test_robot",
            mode="BALANCING",
            ang=1.6,
        )
        id2 = db.log_telemetry(snap2)
        assert id2 is None, "Immediate second sample should be skipped (1Hz limit)"

        # Query back
        results = db.query_telemetry(robot_id="test_robot", limit=10)
        assert len(results) == 1, f"Expected 1 result, got {len(results)}"
        assert results[0].ang == 1.5, "Angle mismatch"
        assert results[0].mode == "BALANCING", "Mode mismatch"

        print("✓ Telemetry logging with downsampling passed")
    finally:
        db.close()
        db_path.unlink(missing_ok=True)


def test_checkpoint_crud():
    """Test checkpoint create/read operations."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    try:
        db = CodexDB(db_path)
        db.init_schema()

        # Save checkpoints with different ratings
        for rating in ["poor", "ok", "good", "great"]:
            cp = Checkpoint(
                ts=time.time(),
                robot_id="test_robot",
                rating=rating,
                mode="BALANCING",
                ang=0.5,
                kp=18.0,
                ki=0.1,
                kd=0.6,
                notes=f"Test checkpoint with {rating} rating",
            )
            cp_id = db.save_checkpoint(cp)
            assert cp_id > 0, f"Failed to save {rating} checkpoint"

        # Query all checkpoints
        all_cps = db.query_checkpoints(robot_id="test_robot")
        assert len(all_cps) == 4, f"Expected 4 checkpoints, got {len(all_cps)}"

        # Query by rating
        good_cps = db.query_checkpoints(rating="good")
        assert len(good_cps) == 1, "Should have exactly 1 good checkpoint"
        assert good_cps[0].rating == "good", "Rating mismatch"

        # Get single checkpoint
        single = db.get_checkpoint(all_cps[0].id)
        assert single is not None, "Failed to get checkpoint by ID"

        print("✓ Checkpoint CRUD passed")
    finally:
        db.close()
        db_path.unlink(missing_ok=True)


def test_doc_chunks():
    """Test doc chunk operations for RAG."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    try:
        db = CodexDB(db_path)
        db.init_schema()

        # Save chunks
        chunks = [
            DocChunk(
                source_path="/docs/playbook.md",
                chunk_index=i,
                content=f"This is chunk {i} content about balancing robots.",
                embedding_json=json.dumps([0.1 * i] * 10),
                token_count=20,
            )
            for i in range(3)
        ]
        count = db.save_doc_chunks(chunks)
        assert count == 3, f"Expected 3 chunks saved, got {count}"

        # Query chunks with embeddings
        all_chunks = db.get_all_chunks_with_embeddings()
        assert len(all_chunks) == 3, f"Expected 3 chunks, got {len(all_chunks)}"

        # Delete chunks for a source
        deleted = db.delete_doc_chunks("/docs/playbook.md")
        assert deleted == 3, f"Expected 3 deleted, got {deleted}"

        # Verify deletion
        remaining = db.get_all_chunks_with_embeddings()
        assert len(remaining) == 0, "Chunks should be deleted"

        print("✓ Doc chunks operations passed")
    finally:
        db.close()
        db_path.unlink(missing_ok=True)


def test_embedding_meta():
    """Test embedding metadata tracking."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    try:
        db = CodexDB(db_path)
        db.init_schema()

        # Save meta
        meta = EmbeddingMeta(
            source_path="/docs/playbook.md",
            file_hash="abc123",
            chunk_count=5,
            model="text-embedding-3-small",
        )
        meta_id = db.save_embedding_meta(meta)
        assert meta_id > 0, "Failed to save embedding meta"

        # Query meta
        retrieved = db.get_embedding_meta("/docs/playbook.md")
        assert retrieved is not None, "Failed to retrieve embedding meta"
        assert retrieved.file_hash == "abc123", "Hash mismatch"
        assert retrieved.chunk_count == 5, "Chunk count mismatch"

        # Update meta (upsert)
        meta2 = EmbeddingMeta(
            source_path="/docs/playbook.md",
            file_hash="def456",
            chunk_count=10,
            model="text-embedding-3-small",
        )
        db.save_embedding_meta(meta2)

        updated = db.get_embedding_meta("/docs/playbook.md")
        assert updated.file_hash == "def456", "Update failed - hash not changed"
        assert updated.chunk_count == 10, "Update failed - count not changed"

        print("✓ Embedding metadata passed")
    finally:
        db.close()
        db_path.unlink(missing_ok=True)


def test_stats():
    """Test database statistics."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    try:
        db = CodexDB(db_path)
        db.init_schema()

        # Add some data
        db.save_checkpoint(Checkpoint(ts=time.time(), robot_id="r1", rating="good"))
        db._last_telemetry_ts.clear()  # Reset downsample tracker
        db.log_telemetry(TelemetrySnapshot(ts=time.time(), robot_id="r1"))
        db.save_embedding_meta(EmbeddingMeta(source_path="/docs/a.md", file_hash="abc", chunk_count=2, model="m"))

        stats = db.get_stats()
        assert stats["checkpoint_count"] == 1, "Checkpoint count wrong"
        assert stats["telemetry_count"] == 1, "Telemetry count wrong"
        assert stats["db_size_bytes"] > 0, "DB size should be > 0"
        assert "db_size_mb" in stats, "Should have MB stat"
        assert "latest_embedding_ts" in stats, "Should include latest embedding freshness"
        assert stats["latest_embedding_ts"] is not None, "Latest embedding timestamp should be populated"

        print(f"✓ Stats passed: {stats}")
    finally:
        db.close()
        db_path.unlink(missing_ok=True)


def test_retention_priority():
    """Test that retention prioritizes good/great rated data."""
    # This is a logic test - actual pruning requires large data volume
    assert RATING_PRIORITY["great"] > RATING_PRIORITY["good"], "great should be highest"
    assert RATING_PRIORITY["good"] > RATING_PRIORITY["ok"], "good > ok"
    assert RATING_PRIORITY["ok"] > RATING_PRIORITY["poor"], "ok > poor"
    assert RATING_PRIORITY["poor"] > RATING_PRIORITY[None], "poor > None"

    print("✓ Retention priority logic passed")


def test_prune_empty_db():
    """Test that pruning on empty/small DB is a no-op."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    try:
        db = CodexDB(db_path)
        db.init_schema()

        # Prune should do nothing on small DB
        result = db.prune_if_needed()
        assert result["telemetry_pruned"] == 0, "Should not prune empty DB"
        assert result["checkpoints_pruned"] == 0, "Should not prune empty DB"

        print("✓ Prune empty DB passed")
    finally:
        db.close()
        db_path.unlink(missing_ok=True)


def run_all_tests():
    """Run all validation tests."""
    print("\n" + "=" * 60)
    print("CodexDB Phase A Validation")
    print("=" * 60 + "\n")

    tests = [
        ("Schema Init", test_schema_init),
        ("Telemetry Logging", test_telemetry_logging),
        ("Checkpoint CRUD", test_checkpoint_crud),
        ("Doc Chunks", test_doc_chunks),
        ("Embedding Meta", test_embedding_meta),
        ("Stats", test_stats),
        ("Retention Priority", test_retention_priority),
        ("Prune Empty DB", test_prune_empty_db),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        try:
            result = test_fn()
            if result:
                passed += 1
            else:
                failed += 1
                print(f"✗ {name} returned False")
        except Exception as e:
            failed += 1
            print(f"✗ {name} failed with exception: {e}")

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60 + "\n")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

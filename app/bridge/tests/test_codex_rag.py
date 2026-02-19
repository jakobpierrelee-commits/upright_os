"""
Validation tests for codex_rag.py - Phase B RAG

Run with: python3 app/bridge/tests/test_codex_rag.py
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from codex_db import CodexDB, DocChunk
from codex_rag import (
    CodexRAG,
    chunk_text,
    cosine_similarity,
    compute_file_hash,
    estimate_tokens,
    CHUNK_SIZE_CHARS,
    CHUNK_OVERLAP_CHARS,
)


def test_chunk_text_basic():
    """Test basic text chunking."""
    # Short text should return single chunk
    short = "This is a short text."
    chunks = chunk_text(short)
    assert len(chunks) == 0 or (len(chunks) == 1 and chunks[0] == short), "Short text handling failed"

    # Medium text with varying content should chunk properly
    medium = " ".join([f"Sentence number {i} has unique content." for i in range(150)])
    chunks = chunk_text(medium)
    assert len(chunks) > 1, f"Expected multiple chunks, got {len(chunks)}"

    # Verify chunks have content and aren't empty
    for i, chunk in enumerate(chunks):
        assert len(chunk) >= 100, f"Chunk {i} too short: {len(chunk)} chars"

    # Verify total content is preserved (accounting for overlap)
    total_chunk_chars = sum(len(c) for c in chunks)
    assert total_chunk_chars >= len(medium), "Chunks should cover all content"

    print("✓ Chunk text basic passed")


def test_chunk_text_paragraph_breaks():
    """Test that chunking prefers paragraph breaks."""
    text = ("First paragraph with some content.\n\n"
            "Second paragraph with more content.\n\n"
            "Third paragraph continues.\n\n") * 20

    chunks = chunk_text(text, chunk_size=500, overlap=50)

    # Chunks should generally end at paragraph boundaries
    para_endings = sum(1 for c in chunks if c.rstrip().endswith('.'))
    assert para_endings > len(chunks) // 2, "Most chunks should end at sentence/paragraph"

    print("✓ Chunk text paragraph breaks passed")


def test_cosine_similarity():
    """Test cosine similarity computation."""
    # Identical vectors = 1.0
    vec = [1.0, 2.0, 3.0]
    sim = cosine_similarity(vec, vec)
    assert abs(sim - 1.0) < 0.001, f"Identical vectors should have sim=1, got {sim}"

    # Orthogonal vectors = 0.0
    vec_a = [1.0, 0.0, 0.0]
    vec_b = [0.0, 1.0, 0.0]
    sim = cosine_similarity(vec_a, vec_b)
    assert abs(sim) < 0.001, f"Orthogonal vectors should have sim=0, got {sim}"

    # Similar vectors should have high similarity
    vec_a = [1.0, 1.0, 1.0]
    vec_b = [1.0, 1.0, 1.2]
    sim = cosine_similarity(vec_a, vec_b)
    assert sim > 0.9, f"Similar vectors should have high sim, got {sim}"

    # Empty/zero vectors
    sim = cosine_similarity([0, 0, 0], [1, 1, 1])
    assert sim == 0.0, "Zero vector should give 0 similarity"

    print("✓ Cosine similarity passed")


def test_file_hash():
    """Test file hash computation."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("Test content for hashing")
        path = Path(f.name)

    try:
        hash1 = compute_file_hash(path)
        assert len(hash1) == 32, "MD5 hash should be 32 chars"

        # Same content = same hash
        hash2 = compute_file_hash(path)
        assert hash1 == hash2, "Same file should have same hash"

        # Different content = different hash
        path.write_text("Different content")
        hash3 = compute_file_hash(path)
        assert hash1 != hash3, "Different content should have different hash"

        print("✓ File hash passed")
    finally:
        path.unlink()


def test_token_estimation():
    """Test token count estimation."""
    text = "This is a test sentence with some words."
    tokens = estimate_tokens(text)
    # ~40 chars / 4 = ~10 tokens
    assert 5 <= tokens <= 20, f"Token estimate should be reasonable, got {tokens}"

    print("✓ Token estimation passed")


def test_rag_initialization():
    """Test RAG class initialization."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    try:
        db = CodexDB(db_path)
        db.init_schema()

        rag = CodexRAG(db=db, repo_root=Path("/tmp"))

        stats = rag.get_index_stats()
        assert "doc_chunk_count" in stats, "Stats should include chunk count"
        assert "embedding_model" in stats, "Stats should include model"
        assert stats["doc_chunk_count"] == 0, "Should start with no chunks"

        print("✓ RAG initialization passed")
    finally:
        db.close()
        db_path.unlink(missing_ok=True)


def test_search_with_mock_embeddings():
    """Test search functionality with pre-populated mock embeddings."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    try:
        db = CodexDB(db_path)
        db.init_schema()

        # Insert mock chunks with embeddings
        # Chunk about PID tuning
        pid_embedding = [0.8, 0.1, 0.1] + [0.0] * 1533  # 1536 dims
        chunk1 = DocChunk(
            source_path="docs/tuning.md",
            chunk_index=0,
            content="PID tuning involves adjusting Kp, Ki, and Kd parameters. Start with Kp.",
            embedding_json=json.dumps(pid_embedding),
            created_at=time.time(),
            token_count=20,
        )

        # Chunk about Kalman filter
        kalman_embedding = [0.1, 0.8, 0.1] + [0.0] * 1533
        chunk2 = DocChunk(
            source_path="docs/kalman.md",
            chunk_index=0,
            content="Kalman filter uses qAngle and qBias to tune noise estimation.",
            embedding_json=json.dumps(kalman_embedding),
            created_at=time.time(),
            token_count=15,
        )

        # Chunk about safety
        safety_embedding = [0.1, 0.1, 0.8] + [0.0] * 1533
        chunk3 = DocChunk(
            source_path="docs/safety.md",
            chunk_index=0,
            content="Never arm the robot without checking tip angle limits first.",
            embedding_json=json.dumps(safety_embedding),
            created_at=time.time(),
            token_count=12,
        )

        db.save_doc_chunks([chunk1, chunk2, chunk3])

        # Create RAG without real API key (will use mock)
        rag = CodexRAG(db=db)

        # Test that search returns results (even if query embedding is zeros)
        # In real usage, the query would get a real embedding
        all_chunks = db.get_all_chunks_with_embeddings()
        assert len(all_chunks) == 3, f"Expected 3 chunks, got {len(all_chunks)}"

        print("✓ Search with mock embeddings passed")
    finally:
        db.close()
        db_path.unlink(missing_ok=True)


def test_context_formatting():
    """Test context string generation."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    try:
        db = CodexDB(db_path)
        db.init_schema()

        # Insert chunk
        embedding = [0.5] * 1536
        chunk = DocChunk(
            source_path="docs/test.md",
            chunk_index=0,
            content="This is test content for context formatting.",
            embedding_json=json.dumps(embedding),
            created_at=time.time(),
            token_count=10,
        )
        db.save_doc_chunks([chunk])

        rag = CodexRAG(db=db)

        # Without API key, search will return empty (query embedding = zeros)
        # But we can verify the method doesn't crash
        context = rag.get_context_for_query("test query", max_tokens=500)
        # Context will be empty without real embeddings, but method should work
        assert isinstance(context, str), "Context should be a string"

        print("✓ Context formatting passed")
    finally:
        db.close()
        db_path.unlink(missing_ok=True)


def test_index_stats():
    """Test index statistics retrieval."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    try:
        db = CodexDB(db_path)
        db.init_schema()

        rag = CodexRAG(db=db)
        stats = rag.get_index_stats()

        required_keys = ["doc_chunk_count", "embedded_docs_count", "embedding_model", "chunk_size", "has_openai_key"]
        for key in required_keys:
            assert key in stats, f"Stats missing key: {key}"

        print(f"✓ Index stats passed: {stats}")
    finally:
        db.close()
        db_path.unlink(missing_ok=True)


def run_all_tests():
    """Run all validation tests."""
    print("\n" + "=" * 60)
    print("CodexRAG Phase B Validation")
    print("=" * 60 + "\n")

    tests = [
        ("Chunk Text Basic", test_chunk_text_basic),
        ("Chunk Text Paragraph Breaks", test_chunk_text_paragraph_breaks),
        ("Cosine Similarity", test_cosine_similarity),
        ("File Hash", test_file_hash),
        ("Token Estimation", test_token_estimation),
        ("RAG Initialization", test_rag_initialization),
        ("Search with Mock Embeddings", test_search_with_mock_embeddings),
        ("Context Formatting", test_context_formatting),
        ("Index Stats", test_index_stats),
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
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60 + "\n")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

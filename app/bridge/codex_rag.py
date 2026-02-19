"""
Codex RAG Module - Embedding and retrieval for documentation.

Provides:
- Text chunking with overlap
- OpenAI embedding generation (text-embedding-3-small)
- Cosine similarity search
- Reindex functionality for docs and sketches

Embeds:
- docs/assistant_knowledge/*.md
- docs/oracle/*.md
- Root playbooks (BALANCE_V2_PLAYBOOK.md, MISSION_ARCHITECTURE_V1.md, etc.)
- Sketch templates (*.ino files)
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from codex_db import CodexDB, DocChunk, EmbeddingMeta, get_codex_db

logger = logging.getLogger(__name__)

# Chunking settings
CHUNK_SIZE_CHARS = 1500
CHUNK_OVERLAP_CHARS = 200
MIN_CHUNK_CHARS = 100

# Embedding settings
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
MAX_TOKENS_PER_BATCH = 8000  # Conservative batch size

# Default paths to index (relative to repo root)
DEFAULT_DOC_PATHS = [
    "docs/assistant_knowledge",
    "docs/oracle",
    "BALANCE_V2_PLAYBOOK.md",
    "MISSION_ARCHITECTURE_V1.md",
    "SESSION_FAILURE_LEARNINGS.md",
]

DEFAULT_SKETCH_PATHS = [
    "tumbller_v06_nano_balance_v2",
    "generated_firmware",
]


@dataclass
class SearchResult:
    source_path: str
    chunk_index: int
    content: str
    score: float
    token_count: int


def compute_file_hash(path: Path) -> str:
    """Compute MD5 hash of file contents."""
    hasher = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def estimate_tokens(text: str) -> int:
    """Rough token estimate (4 chars per token for English)."""
    return len(text) // 4


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE_CHARS, overlap: int = CHUNK_OVERLAP_CHARS) -> List[str]:
    """
    Split text into overlapping chunks.
    Tries to break at paragraph/sentence boundaries when possible.
    """
    if len(text) <= chunk_size:
        return [text] if len(text) >= MIN_CHUNK_CHARS else []

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        if end >= len(text):
            chunk = text[start:].strip()
            if len(chunk) >= MIN_CHUNK_CHARS:
                chunks.append(chunk)
            break

        # Try to find a good break point (paragraph, then sentence, then word)
        chunk_text_raw = text[start:end]

        # Look for paragraph break
        para_break = chunk_text_raw.rfind("\n\n")
        if para_break > chunk_size // 2:
            end = start + para_break + 2
        else:
            # Look for sentence break
            sentence_breaks = [
                chunk_text_raw.rfind(". "),
                chunk_text_raw.rfind(".\n"),
                chunk_text_raw.rfind("? "),
                chunk_text_raw.rfind("! "),
            ]
            best_break = max(b for b in sentence_breaks if b > chunk_size // 2) if any(b > chunk_size // 2 for b in sentence_breaks) else -1
            if best_break > 0:
                end = start + best_break + 2
            else:
                # Fall back to word break
                word_break = chunk_text_raw.rfind(" ")
                if word_break > chunk_size // 2:
                    end = start + word_break + 1

        chunk = text[start:end].strip()
        if len(chunk) >= MIN_CHUNK_CHARS:
            chunks.append(chunk)

        start = end - overlap

    return chunks


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(vec_a) != len(vec_b):
        return 0.0

    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


class CodexRAG:
    """RAG system for Codex documentation retrieval."""

    def __init__(
        self,
        db: Optional[CodexDB] = None,
        repo_root: Optional[Path] = None,
        openai_api_key: Optional[str] = None,
    ):
        self.db = db or get_codex_db()
        self.repo_root = repo_root or Path(__file__).parent.parent.parent
        self._openai_key = openai_api_key or os.environ.get("OPENAI_API_KEY")
        self._embedding_cache: Dict[str, List[float]] = {}

    def set_openai_key(self, key: str) -> None:
        """Set OpenAI API key at runtime."""
        self._openai_key = key

    def _get_embedding(self, texts: List[str]) -> List[List[float]]:
        """
        Get embeddings from OpenAI API.
        Returns list of embedding vectors.
        """
        if not self._openai_key:
            logger.warning("No OpenAI API key configured for embeddings")
            return [[0.0] * EMBEDDING_DIMENSIONS for _ in texts]

        try:
            import httpx

            response = httpx.post(
                "https://api.openai.com/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {self._openai_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": EMBEDDING_MODEL,
                    "input": texts,
                },
                timeout=60.0,
            )
            response.raise_for_status()
            data = response.json()

            # Sort by index to maintain order
            embeddings = sorted(data["data"], key=lambda x: x["index"])
            return [e["embedding"] for e in embeddings]

        except Exception as e:
            logger.error(f"Embedding API error: {e}")
            return [[0.0] * EMBEDDING_DIMENSIONS for _ in texts]

    def _collect_files(self, paths: List[str], extensions: List[str]) -> List[Path]:
        """Collect all files matching extensions from paths."""
        files = []

        for rel_path in paths:
            full_path = self.repo_root / rel_path
            if not full_path.exists():
                logger.debug(f"Path not found: {full_path}")
                continue

            if full_path.is_file():
                if any(full_path.suffix == ext for ext in extensions):
                    files.append(full_path)
            elif full_path.is_dir():
                for ext in extensions:
                    files.extend(full_path.rglob(f"*{ext}"))

        return files

    def index_docs(
        self,
        doc_paths: Optional[List[str]] = None,
        force_reindex: bool = False,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> Dict[str, Any]:
        """
        Index documentation files for RAG retrieval.

        Args:
            doc_paths: List of paths (relative to repo root) to index
            force_reindex: If True, reindex even if file hasn't changed
            progress_callback: Optional callback(file_path, current, total)

        Returns:
            Dict with indexing statistics
        """
        paths = doc_paths or DEFAULT_DOC_PATHS
        files = self._collect_files(paths, [".md", ".txt"])

        stats = {
            "files_processed": 0,
            "files_skipped": 0,
            "chunks_created": 0,
            "errors": [],
        }

        total = len(files)
        for i, file_path in enumerate(files):
            try:
                rel_path = str(file_path.relative_to(self.repo_root))

                if progress_callback:
                    progress_callback(rel_path, i + 1, total)

                # Check if file has changed
                current_hash = compute_file_hash(file_path)
                existing_meta = self.db.get_embedding_meta(rel_path)

                if existing_meta and existing_meta.file_hash == current_hash and not force_reindex:
                    logger.debug(f"Skipping unchanged file: {rel_path}")
                    stats["files_skipped"] += 1
                    continue

                # Read and chunk file
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                chunks = chunk_text(content)

                if not chunks:
                    logger.debug(f"No chunks from file: {rel_path}")
                    stats["files_skipped"] += 1
                    continue

                # Get embeddings
                embeddings = self._get_embedding(chunks)

                # Delete old chunks for this file
                self.db.delete_doc_chunks(rel_path)

                # Save new chunks
                doc_chunks = [
                    DocChunk(
                        source_path=rel_path,
                        chunk_index=idx,
                        content=chunk,
                        embedding_json=json.dumps(emb),
                        created_at=time.time(),
                        token_count=estimate_tokens(chunk),
                    )
                    for idx, (chunk, emb) in enumerate(zip(chunks, embeddings))
                ]
                self.db.save_doc_chunks(doc_chunks)

                # Update metadata
                self.db.save_embedding_meta(EmbeddingMeta(
                    source_path=rel_path,
                    file_hash=current_hash,
                    chunk_count=len(chunks),
                    embedded_at=time.time(),
                    model=EMBEDDING_MODEL,
                ))

                stats["files_processed"] += 1
                stats["chunks_created"] += len(chunks)
                logger.info(f"Indexed {rel_path}: {len(chunks)} chunks")

            except Exception as e:
                logger.error(f"Error indexing {file_path}: {e}")
                stats["errors"].append({"file": str(file_path), "error": str(e)})

        return stats

    def index_sketches(
        self,
        sketch_paths: Optional[List[str]] = None,
        force_reindex: bool = False,
    ) -> Dict[str, Any]:
        """
        Index Arduino sketch files for RAG retrieval.
        Sketches are useful for generate_sketch tool context.
        """
        paths = sketch_paths or DEFAULT_SKETCH_PATHS
        files = self._collect_files(paths, [".ino", ".h", ".cpp"])

        stats = {
            "files_processed": 0,
            "files_skipped": 0,
            "chunks_created": 0,
            "errors": [],
        }

        for file_path in files:
            try:
                rel_path = str(file_path.relative_to(self.repo_root))

                # Check if file has changed
                current_hash = compute_file_hash(file_path)
                existing_meta = self.db.get_embedding_meta(rel_path)

                if existing_meta and existing_meta.file_hash == current_hash and not force_reindex:
                    stats["files_skipped"] += 1
                    continue

                # Read and chunk file (larger chunks for code)
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                chunks = chunk_text(content, chunk_size=2000, overlap=300)

                if not chunks:
                    stats["files_skipped"] += 1
                    continue

                # Get embeddings
                embeddings = self._get_embedding(chunks)

                # Delete old and save new
                self.db.delete_doc_chunks(rel_path)

                doc_chunks = [
                    DocChunk(
                        source_path=rel_path,
                        chunk_index=idx,
                        content=chunk,
                        embedding_json=json.dumps(emb),
                        created_at=time.time(),
                        token_count=estimate_tokens(chunk),
                    )
                    for idx, (chunk, emb) in enumerate(zip(chunks, embeddings))
                ]
                self.db.save_doc_chunks(doc_chunks)

                self.db.save_embedding_meta(EmbeddingMeta(
                    source_path=rel_path,
                    file_hash=current_hash,
                    chunk_count=len(chunks),
                    embedded_at=time.time(),
                    model=EMBEDDING_MODEL,
                ))

                stats["files_processed"] += 1
                stats["chunks_created"] += len(chunks)
                logger.info(f"Indexed sketch {rel_path}: {len(chunks)} chunks")

            except Exception as e:
                logger.error(f"Error indexing sketch {file_path}: {e}")
                stats["errors"].append({"file": str(file_path), "error": str(e)})

        return stats

    def search_docs(
        self,
        query: str,
        k: int = 5,
        min_score: float = 0.5,
        source_filter: Optional[str] = None,
    ) -> List[SearchResult]:
        """
        Search indexed documents using semantic similarity.

        Args:
            query: Search query
            k: Number of results to return
            min_score: Minimum similarity score (0-1)
            source_filter: Optional regex to filter source paths

        Returns:
            List of SearchResult sorted by score (descending)
        """
        if not query.strip():
            return []

        # Get query embedding
        query_embedding = self._get_embedding([query])[0]

        # Check if embedding is valid (not all zeros)
        if all(v == 0.0 for v in query_embedding):
            logger.warning("Query embedding failed - returning empty results")
            return []

        # Get all chunks with embeddings
        all_chunks = self.db.get_all_chunks_with_embeddings()

        if not all_chunks:
            logger.info("No indexed documents found")
            return []

        # Apply source filter if provided
        if source_filter:
            pattern = re.compile(source_filter, re.IGNORECASE)
            all_chunks = [c for c in all_chunks if pattern.search(c.source_path)]

        # Score all chunks
        scored_results: List[Tuple[float, DocChunk]] = []

        for chunk in all_chunks:
            try:
                chunk_embedding = json.loads(chunk.embedding_json)
                if not chunk_embedding or all(v == 0.0 for v in chunk_embedding):
                    continue

                score = cosine_similarity(query_embedding, chunk_embedding)
                if score >= min_score:
                    scored_results.append((score, chunk))
            except (json.JSONDecodeError, TypeError):
                continue

        # Sort by score and take top k
        scored_results.sort(key=lambda x: x[0], reverse=True)
        top_results = scored_results[:k]

        return [
            SearchResult(
                source_path=chunk.source_path,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                score=score,
                token_count=chunk.token_count,
            )
            for score, chunk in top_results
        ]

    def get_context_for_query(
        self,
        query: str,
        max_tokens: int = 2000,
        include_sources: bool = True,
    ) -> str:
        """
        Get formatted context string for injection into AI prompt.

        Args:
            query: User query
            max_tokens: Maximum tokens to include
            include_sources: Whether to include source citations

        Returns:
            Formatted context string
        """
        results = self.search_docs(query, k=10, min_score=0.4)

        if not results:
            return ""

        context_parts = []
        total_tokens = 0

        for result in results:
            if total_tokens + result.token_count > max_tokens:
                break

            if include_sources:
                context_parts.append(f"[Source: {result.source_path}]\n{result.content}")
            else:
                context_parts.append(result.content)

            total_tokens += result.token_count

        return "\n\n---\n\n".join(context_parts)

    def get_index_stats(self) -> Dict[str, Any]:
        """Get statistics about indexed documents."""
        db_stats = self.db.get_stats()

        return {
            "doc_chunk_count": db_stats["doc_chunk_count"],
            "embedded_docs_count": db_stats["embedded_docs_count"],
            "embedding_model": EMBEDDING_MODEL,
            "chunk_size": CHUNK_SIZE_CHARS,
            "has_openai_key": bool(self._openai_key),
        }


# Module-level singleton
_default_rag: Optional[CodexRAG] = None


def get_codex_rag(openai_key: Optional[str] = None) -> CodexRAG:
    """Get or create the default CodexRAG instance."""
    global _default_rag
    if _default_rag is None:
        _default_rag = CodexRAG(openai_api_key=openai_key)
    elif openai_key:
        _default_rag.set_openai_key(openai_key)
    return _default_rag

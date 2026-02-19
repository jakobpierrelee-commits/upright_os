#!/usr/bin/env python3
"""
RAG Retrieval Quality Harness

Evaluates RAG retrieval quality using known queries with expected source hits.
Computes precision, recall, and MRR (Mean Reciprocal Rank) metrics.

Usage:
    python3 scripts/rag_quality_harness.py [--output report.json] [--verbose]

Requirements:
    - RAG index must be populated before running
    - Set OPENAI_API_KEY environment variable for embeddings
"""

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add app/bridge to path for imports
SCRIPT_DIR = Path(__file__).parent.absolute()
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(REPO_ROOT / "app" / "bridge"))


@dataclass
class QueryExpectation:
    """A test query with expected retrieval results."""
    query: str
    expected_sources: List[str]  # Source path patterns (regex)
    description: str = ""
    min_score: float = 0.5
    top_k: int = 5


@dataclass
class QueryResult:
    """Result of running a single query."""
    query: str
    expected_sources: List[str]
    retrieved_sources: List[str]
    retrieved_scores: List[float]
    hits: List[str]  # Expected sources that were retrieved
    misses: List[str]  # Expected sources not retrieved
    precision: float  # hits / retrieved
    recall: float  # hits / expected
    reciprocal_rank: float  # 1/rank of first hit (0 if no hit)
    latency_ms: float


@dataclass
class HarnessReport:
    """Full report from running the harness."""
    timestamp: str
    total_queries: int
    mean_precision: float
    mean_recall: float
    mean_reciprocal_rank: float
    mean_latency_ms: float
    passing_queries: int
    failing_queries: int
    query_results: List[Dict[str, Any]]
    index_stats: Dict[str, Any]


# Real operator queries with expected source patterns
# These represent typical questions operators ask the Codex assistant
QUALITY_TEST_QUERIES: List[QueryExpectation] = [
    QueryExpectation(
        query="How do I tune PID gains for the balancing controller?",
        expected_sources=[
            r".*PID.*",
            r".*tuning.*",
            r".*control.*",
            r".*balance.*",
        ],
        description="PID tuning documentation lookup",
    ),
    QueryExpectation(
        query="What serial commands are available for the robot?",
        expected_sources=[
            r".*serial.*",
            r".*command.*",
            r".*protocol.*",
        ],
        description="Serial protocol documentation",
    ),
    QueryExpectation(
        query="How do I flash firmware to the Arduino?",
        expected_sources=[
            r".*firmware.*",
            r".*flash.*",
            r".*arduino.*",
            r".*upload.*",
        ],
        description="Firmware upload procedures",
    ),
    QueryExpectation(
        query="What are the safety limits for motor current?",
        expected_sources=[
            r".*safety.*",
            r".*motor.*",
            r".*current.*",
            r".*limit.*",
        ],
        description="Safety parameter documentation",
    ),
    QueryExpectation(
        query="How do I calibrate the IMU sensor?",
        expected_sources=[
            r".*IMU.*",
            r".*calibrat.*",
            r".*sensor.*",
            r".*gyro.*",
        ],
        description="IMU calibration procedures",
    ),
    QueryExpectation(
        query="What telemetry data is logged during experiments?",
        expected_sources=[
            r".*telemetry.*",
            r".*log.*",
            r".*experiment.*",
            r".*data.*",
        ],
        description="Telemetry and logging documentation",
    ),
    QueryExpectation(
        query="How do I configure the Codex assistant behavior?",
        expected_sources=[
            r".*codex.*",
            r".*assistant.*",
            r".*config.*",
            r".*profile.*",
        ],
        description="Codex configuration documentation",
    ),
    QueryExpectation(
        query="What is the RAG indexing process?",
        expected_sources=[
            r".*rag.*",
            r".*index.*",
            r".*embed.*",
            r".*vector.*",
        ],
        description="RAG system documentation",
    ),
]


def source_matches_pattern(source: str, patterns: List[str]) -> bool:
    """Check if source path matches any of the expected patterns."""
    for pattern in patterns:
        if re.search(pattern, source, re.IGNORECASE):
            return True
    return False


def run_single_query(
    rag,
    expectation: QueryExpectation,
    verbose: bool = False,
) -> QueryResult:
    """Run a single query and evaluate results."""
    start_time = time.time()
    
    results = rag.search_docs(
        query=expectation.query,
        k=expectation.top_k,
        min_score=expectation.min_score,
    )
    
    latency_ms = (time.time() - start_time) * 1000
    
    retrieved_sources = [r.source_path for r in results]
    retrieved_scores = [r.score for r in results]
    
    # Compute hits and misses
    hits = []
    misses = []
    
    for pattern in expectation.expected_sources:
        found = False
        for source in retrieved_sources:
            if re.search(pattern, source, re.IGNORECASE):
                if source not in hits:
                    hits.append(source)
                found = True
                break
        if not found:
            misses.append(pattern)
    
    # Compute metrics
    precision = len(hits) / len(retrieved_sources) if retrieved_sources else 0.0
    recall = len(hits) / len(expectation.expected_sources) if expectation.expected_sources else 0.0
    
    # Reciprocal rank: 1/rank of first relevant result
    reciprocal_rank = 0.0
    for idx, source in enumerate(retrieved_sources):
        if source_matches_pattern(source, expectation.expected_sources):
            reciprocal_rank = 1.0 / (idx + 1)
            break
    
    if verbose:
        status = "✓" if recall > 0 else "✗"
        print(f"  {status} {expectation.description}: P={precision:.2f} R={recall:.2f} MRR={reciprocal_rank:.2f}")
    
    return QueryResult(
        query=expectation.query,
        expected_sources=expectation.expected_sources,
        retrieved_sources=retrieved_sources,
        retrieved_scores=retrieved_scores,
        hits=hits,
        misses=misses,
        precision=precision,
        recall=recall,
        reciprocal_rank=reciprocal_rank,
        latency_ms=latency_ms,
    )


def run_harness(
    rag,
    queries: Optional[List[QueryExpectation]] = None,
    verbose: bool = False,
) -> HarnessReport:
    """Run the full quality harness and generate report."""
    queries = queries or QUALITY_TEST_QUERIES
    
    if verbose:
        print(f"\n=== RAG Quality Harness ===")
        print(f"Running {len(queries)} test queries...\n")
    
    results: List[QueryResult] = []
    
    for expectation in queries:
        result = run_single_query(rag, expectation, verbose=verbose)
        results.append(result)
    
    # Aggregate metrics
    mean_precision = sum(r.precision for r in results) / len(results) if results else 0.0
    mean_recall = sum(r.recall for r in results) / len(results) if results else 0.0
    mean_mrr = sum(r.reciprocal_rank for r in results) / len(results) if results else 0.0
    mean_latency = sum(r.latency_ms for r in results) / len(results) if results else 0.0
    
    passing = sum(1 for r in results if r.recall > 0)
    failing = len(results) - passing
    
    # Get index stats
    try:
        index_stats = rag.get_index_stats()
    except Exception:
        index_stats = {}
    
    report = HarnessReport(
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        total_queries=len(queries),
        mean_precision=mean_precision,
        mean_recall=mean_recall,
        mean_reciprocal_rank=mean_mrr,
        mean_latency_ms=mean_latency,
        passing_queries=passing,
        failing_queries=failing,
        query_results=[
            {
                "query": r.query,
                "description": next(
                    (q.description for q in queries if q.query == r.query),
                    "",
                ),
                "precision": r.precision,
                "recall": r.recall,
                "mrr": r.reciprocal_rank,
                "latency_ms": r.latency_ms,
                "hits": r.hits,
                "misses": r.misses,
                "retrieved": list(zip(r.retrieved_sources, r.retrieved_scores)),
            }
            for r in results
        ],
        index_stats=index_stats,
    )
    
    if verbose:
        print(f"\n=== Summary ===")
        print(f"Queries: {passing}/{len(queries)} passing")
        print(f"Mean Precision: {mean_precision:.3f}")
        print(f"Mean Recall: {mean_recall:.3f}")
        print(f"Mean Reciprocal Rank: {mean_mrr:.3f}")
        print(f"Mean Latency: {mean_latency:.1f}ms")
    
    return report


def report_to_dict(report: HarnessReport) -> Dict[str, Any]:
    """Convert report to dictionary for JSON serialization."""
    return {
        "timestamp": report.timestamp,
        "total_queries": report.total_queries,
        "mean_precision": report.mean_precision,
        "mean_recall": report.mean_recall,
        "mean_reciprocal_rank": report.mean_reciprocal_rank,
        "mean_latency_ms": report.mean_latency_ms,
        "passing_queries": report.passing_queries,
        "failing_queries": report.failing_queries,
        "query_results": report.query_results,
        "index_stats": report.index_stats,
    }


def main():
    parser = argparse.ArgumentParser(description="RAG Retrieval Quality Harness")
    parser.add_argument("--output", "-o", help="Output JSON report path")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--dry-run", action="store_true", help="Show queries without running")
    args = parser.parse_args()
    
    if args.dry_run:
        print("=== Quality Test Queries ===\n")
        for i, q in enumerate(QUALITY_TEST_QUERIES, 1):
            print(f"{i}. {q.description}")
            print(f"   Query: {q.query}")
            print(f"   Expected patterns: {q.expected_sources}")
            print()
        return
    
    # Import RAG module
    try:
        from codex_rag import get_codex_rag
    except ImportError as e:
        print(f"Error importing codex_rag: {e}")
        print("Make sure you're running from the repo root.")
        sys.exit(1)
    
    # Get OpenAI key
    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        print("Warning: OPENAI_API_KEY not set. Embedding queries will fail.")
    
    # Initialize RAG
    rag = get_codex_rag(openai_key)
    
    # Check if index is populated
    stats = rag.get_index_stats()
    if stats.get("doc_chunk_count", 0) == 0:
        print("Error: RAG index is empty. Run indexing first:")
        print("  curl -X POST http://localhost:8080/ai/rag/index")
        sys.exit(1)
    
    # Run harness
    report = run_harness(rag, verbose=args.verbose)
    
    # Output report
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(json.dumps(report_to_dict(report), indent=2))
        print(f"\nReport written to: {args.output}")
    else:
        print(json.dumps(report_to_dict(report), indent=2))
    
    # Exit with error if any queries failed
    if report.failing_queries > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

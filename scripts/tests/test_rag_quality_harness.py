"""
Tests for RAG quality harness.

Run with: python3 -m pytest scripts/tests/test_rag_quality_harness.py -v
"""

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from rag_quality_harness import (
    QueryExpectation,
    QueryResult,
    HarnessReport,
    source_matches_pattern,
    run_single_query,
    run_harness,
    report_to_dict,
    QUALITY_TEST_QUERIES,
)


class TestSourceMatching:
    """Test source pattern matching logic."""

    def test_matches_simple_pattern(self):
        assert source_matches_pattern("docs/PID_tuning.md", [r".*PID.*"])
        assert source_matches_pattern("app/bridge/codex_rag.py", [r".*rag.*"])

    def test_matches_case_insensitive(self):
        assert source_matches_pattern("docs/pid_TUNING.md", [r".*PID.*"])
        assert source_matches_pattern("app/bridge/CODEX_RAG.py", [r".*rag.*"])

    def test_matches_any_pattern(self):
        patterns = [r".*serial.*", r".*command.*", r".*protocol.*"]
        assert source_matches_pattern("docs/serial_commands.md", patterns)
        assert source_matches_pattern("docs/protocol_spec.md", patterns)
        assert source_matches_pattern("app/command_handler.py", patterns)

    def test_no_match_returns_false(self):
        assert not source_matches_pattern("docs/readme.md", [r".*PID.*"])
        assert not source_matches_pattern("app/main.py", [r".*serial.*", r".*rag.*"])


class TestQueryExpectation:
    """Test QueryExpectation dataclass."""

    def test_default_values(self):
        qe = QueryExpectation(
            query="test query",
            expected_sources=[".*test.*"],
        )
        assert qe.description == ""
        assert qe.min_score == 0.5
        assert qe.top_k == 5

    def test_custom_values(self):
        qe = QueryExpectation(
            query="test query",
            expected_sources=[".*test.*"],
            description="Test description",
            min_score=0.7,
            top_k=10,
        )
        assert qe.description == "Test description"
        assert qe.min_score == 0.7
        assert qe.top_k == 10


class TestRunSingleQuery:
    """Test single query execution."""

    def test_computes_metrics_correctly(self):
        """Test that precision, recall, and MRR are computed correctly."""
        # Mock RAG with controlled results
        mock_rag = MagicMock()
        
        # Create mock search results
        mock_result_1 = MagicMock()
        mock_result_1.source_path = "docs/PID_tuning.md"
        mock_result_1.score = 0.85
        
        mock_result_2 = MagicMock()
        mock_result_2.source_path = "docs/control_theory.md"
        mock_result_2.score = 0.72
        
        mock_result_3 = MagicMock()
        mock_result_3.source_path = "docs/unrelated.md"
        mock_result_3.score = 0.55
        
        mock_rag.search_docs.return_value = [mock_result_1, mock_result_2, mock_result_3]
        
        expectation = QueryExpectation(
            query="How do I tune PID?",
            expected_sources=[r".*PID.*", r".*control.*"],
            description="PID tuning",
        )
        
        result = run_single_query(mock_rag, expectation)
        
        # 2 hits out of 3 retrieved = 0.67 precision
        assert abs(result.precision - 2/3) < 0.01
        # 2 hits out of 2 expected = 1.0 recall
        assert result.recall == 1.0
        # First result is a hit, so MRR = 1.0
        assert result.reciprocal_rank == 1.0

    def test_handles_no_results(self):
        """Test behavior when RAG returns no results."""
        mock_rag = MagicMock()
        mock_rag.search_docs.return_value = []
        
        expectation = QueryExpectation(
            query="test query",
            expected_sources=[r".*test.*"],
        )
        
        result = run_single_query(mock_rag, expectation)
        
        assert result.precision == 0.0
        assert result.recall == 0.0
        assert result.reciprocal_rank == 0.0
        assert result.hits == []
        assert len(result.misses) == 1

    def test_handles_no_hits(self):
        """Test behavior when results don't match expectations."""
        mock_rag = MagicMock()
        
        mock_result = MagicMock()
        mock_result.source_path = "docs/unrelated.md"
        mock_result.score = 0.6
        
        mock_rag.search_docs.return_value = [mock_result]
        
        expectation = QueryExpectation(
            query="test query",
            expected_sources=[r".*PID.*"],
        )
        
        result = run_single_query(mock_rag, expectation)
        
        assert result.precision == 0.0
        assert result.recall == 0.0
        assert result.reciprocal_rank == 0.0

    def test_mrr_with_late_hit(self):
        """Test MRR when first hit is not first result."""
        mock_rag = MagicMock()
        
        results = []
        for i, name in enumerate(["unrelated1.md", "unrelated2.md", "PID_doc.md"]):
            mock_result = MagicMock()
            mock_result.source_path = f"docs/{name}"
            mock_result.score = 0.9 - i * 0.1
            results.append(mock_result)
        
        mock_rag.search_docs.return_value = results
        
        expectation = QueryExpectation(
            query="test query",
            expected_sources=[r".*PID.*"],
        )
        
        result = run_single_query(mock_rag, expectation)
        
        # Hit is at position 3 (index 2), so MRR = 1/3
        assert abs(result.reciprocal_rank - 1/3) < 0.01


class TestRunHarness:
    """Test full harness execution."""

    def test_aggregates_metrics(self):
        """Test that harness correctly aggregates metrics across queries."""
        mock_rag = MagicMock()
        
        # All queries return one matching result
        mock_result = MagicMock()
        mock_result.source_path = "docs/match.md"
        mock_result.score = 0.8
        mock_rag.search_docs.return_value = [mock_result]
        mock_rag.get_index_stats.return_value = {"doc_chunk_count": 100}
        
        queries = [
            QueryExpectation(query="q1", expected_sources=[r".*match.*"]),
            QueryExpectation(query="q2", expected_sources=[r".*match.*"]),
        ]
        
        report = run_harness(mock_rag, queries)
        
        assert report.total_queries == 2
        assert report.passing_queries == 2
        assert report.failing_queries == 0
        assert report.mean_precision == 1.0
        assert report.mean_recall == 1.0

    def test_counts_failures(self):
        """Test that harness correctly counts failing queries."""
        mock_rag = MagicMock()
        mock_rag.search_docs.return_value = []
        mock_rag.get_index_stats.return_value = {}
        
        queries = [
            QueryExpectation(query="q1", expected_sources=[r".*test.*"]),
            QueryExpectation(query="q2", expected_sources=[r".*test.*"]),
        ]
        
        report = run_harness(mock_rag, queries)
        
        assert report.passing_queries == 0
        assert report.failing_queries == 2


class TestReportSerialization:
    """Test report JSON serialization."""

    def test_report_to_dict(self):
        """Test that report can be serialized to dict."""
        report = HarnessReport(
            timestamp="2026-02-19T00:00:00Z",
            total_queries=2,
            mean_precision=0.75,
            mean_recall=0.80,
            mean_reciprocal_rank=0.90,
            mean_latency_ms=50.0,
            passing_queries=2,
            failing_queries=0,
            query_results=[],
            index_stats={"doc_chunk_count": 100},
        )
        
        d = report_to_dict(report)
        
        assert d["timestamp"] == "2026-02-19T00:00:00Z"
        assert d["mean_precision"] == 0.75
        assert d["mean_recall"] == 0.80
        assert d["index_stats"]["doc_chunk_count"] == 100

    def test_report_json_serializable(self):
        """Test that report dict is JSON serializable."""
        report = HarnessReport(
            timestamp="2026-02-19T00:00:00Z",
            total_queries=1,
            mean_precision=0.5,
            mean_recall=0.5,
            mean_reciprocal_rank=1.0,
            mean_latency_ms=25.0,
            passing_queries=1,
            failing_queries=0,
            query_results=[{
                "query": "test",
                "precision": 0.5,
                "recall": 0.5,
                "mrr": 1.0,
                "hits": ["doc.md"],
                "misses": [],
            }],
            index_stats={},
        )
        
        d = report_to_dict(report)
        json_str = json.dumps(d)
        
        assert isinstance(json_str, str)
        parsed = json.loads(json_str)
        assert parsed["total_queries"] == 1


class TestQualityTestQueries:
    """Test the predefined quality test queries."""

    def test_queries_are_defined(self):
        """Verify we have test queries defined."""
        assert len(QUALITY_TEST_QUERIES) >= 5

    def test_queries_have_required_fields(self):
        """Verify all queries have required fields."""
        for q in QUALITY_TEST_QUERIES:
            assert q.query, "Query must have query text"
            assert q.expected_sources, "Query must have expected sources"
            assert len(q.expected_sources) > 0

    def test_queries_cover_key_domains(self):
        """Verify queries cover important operator domains."""
        all_queries = " ".join(q.query.lower() for q in QUALITY_TEST_QUERIES)
        
        # Should cover key domains
        domains = ["pid", "serial", "firmware", "safety", "telemetry"]
        covered = sum(1 for d in domains if d in all_queries)
        
        assert covered >= 3, f"Queries should cover at least 3 key domains, got {covered}"

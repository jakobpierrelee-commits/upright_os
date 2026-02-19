"""Tests for PRD traceability check script."""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Add parent to path for import
sys.path.insert(0, str(Path(__file__).parent.parent))

from prd_traceability_check import (
    parse_prd_version,
    parse_implementation_matrix,
    infer_test_file,
    FileCheck,
    check_files,
)


class TestParsePrdVersion:
    def test_extracts_version(self):
        content = "**Version:** 1.1\n**Status:** Active"
        assert parse_prd_version(content) == "1.1"

    def test_returns_unknown_if_missing(self):
        content = "# Some PRD\nNo version here"
        assert parse_prd_version(content) == "unknown"


class TestParseImplementationMatrix:
    def test_parses_matrix_table(self):
        content = """
### 2.1 Implementation Matrix

| Capability | Status | Notes | Key Files |
|---|---|---|---|
| RAG core | Implemented | Works | `app/rag.py`, `app/db.py` |
| Tool safety | Partial | WIP | `app/tools.py` |
"""
        result = parse_implementation_matrix(content)
        
        assert len(result) == 2
        assert result[0]["capability"] == "RAG core"
        assert result[0]["status"] == "Implemented"
        assert result[0]["key_files"] == ["app/rag.py", "app/db.py"]
        assert result[1]["capability"] == "Tool safety"
        assert result[1]["status"] == "Partial"
        assert result[1]["key_files"] == ["app/tools.py"]

    def test_returns_empty_if_no_matrix(self):
        content = "# PRD\nNo matrix here"
        result = parse_implementation_matrix(content)
        assert result == []


class TestInferTestFile:
    def test_python_file_in_tests_dir(self, tmp_path):
        # Create structure
        (tmp_path / "app" / "bridge" / "tests").mkdir(parents=True)
        (tmp_path / "app" / "bridge" / "tests" / "test_codex.py").touch()
        
        result = infer_test_file("app/bridge/codex.py", tmp_path)
        assert result == "app/bridge/tests/test_codex.py"

    def test_tsx_file_with_test_sibling(self, tmp_path):
        # Create structure
        (tmp_path / "src" / "features").mkdir(parents=True)
        (tmp_path / "src" / "features" / "Panel.tsx").touch()
        (tmp_path / "src" / "features" / "Panel.test.tsx").touch()
        
        result = infer_test_file("src/features/Panel.tsx", tmp_path)
        assert result == "src/features/Panel.test.tsx"

    def test_returns_none_if_no_test(self, tmp_path):
        (tmp_path / "app").mkdir()
        result = infer_test_file("app/module.py", tmp_path)
        assert result is None


class TestCheckFiles:
    def test_checks_file_existence(self, tmp_path):
        # Create some files
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "existing.py").touch()
        
        capabilities = [
            {"capability": "Feature A", "status": "Implemented", "notes": "", "key_files": ["app/existing.py"]},
            {"capability": "Feature B", "status": "Partial", "notes": "", "key_files": ["app/missing.py"]},
        ]
        
        result = check_files(capabilities, tmp_path)
        
        assert len(result) == 2
        assert result[0].all_files_exist is True
        assert result[1].all_files_exist is False


class TestReportGeneration:
    def test_generates_valid_json_structure(self, tmp_path):
        # Create minimal PRD
        prd_content = """
**Version:** 1.0

### 2.1 Implementation Matrix

| Capability | Status | Notes | Key Files |
|---|---|---|---|
| Test cap | Implemented | OK | `test.py` |
"""
        prd_path = tmp_path / "test_prd.md"
        prd_path.write_text(prd_content)
        (tmp_path / "test.py").touch()
        
        from prd_traceability_check import generate_report
        
        with patch("prd_traceability_check.get_git_info", return_value=("main", "abc123")):
            report = generate_report(prd_path, tmp_path, run_tests=False)
        
        assert report.prd_version == "1.0"
        assert report.branch == "main"
        assert report.commit == "abc123"
        assert len(report.capabilities) == 1
        assert report.summary["total_capabilities"] == 1

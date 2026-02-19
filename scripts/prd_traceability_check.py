#!/usr/bin/env python3
"""
PRD Traceability Check - Automated handoff verification.

Parses PRD implementation matrix and verifies:
1. Referenced source files exist
2. Related test files exist
3. Test commands pass (optional)

Outputs machine-readable JSON artifact for handoff records.

Usage:
    python scripts/prd_traceability_check.py [--run-tests] [--output traceability.json]
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


@dataclass
class FileCheck:
    path: str
    exists: bool
    test_file: Optional[str] = None
    test_exists: bool = False


@dataclass
class CapabilityTrace:
    capability: str
    status: str
    notes: str
    files: list[FileCheck]
    all_files_exist: bool
    has_tests: bool


@dataclass
class TraceabilityReport:
    prd_path: str
    prd_version: str
    branch: str
    commit: str
    generated_at: str
    capabilities: list[CapabilityTrace]
    tests_run: bool
    tests_passed: Optional[bool]
    test_results: Optional[dict]
    summary: dict


def get_git_info(repo_root: Path) -> tuple[str, str]:
    """Get current branch and commit SHA."""
    try:
        branch = subprocess.check_output(
            ["git", "branch", "--show-current"],
            cwd=repo_root,
            text=True,
        ).strip()
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            text=True,
        ).strip()
        return branch, commit
    except subprocess.CalledProcessError:
        return "unknown", "unknown"


def parse_prd_version(prd_content: str) -> str:
    """Extract version from PRD frontmatter."""
    match = re.search(r"\*\*Version:\*\*\s*(\S+)", prd_content)
    return match.group(1) if match else "unknown"


def parse_implementation_matrix(prd_content: str) -> list[dict]:
    """Parse the implementation matrix table from PRD."""
    capabilities = []
    
    # Find the implementation matrix section
    matrix_match = re.search(
        r"### 2\.1 Implementation Matrix\s*\n\s*\|[^\n]+\|\s*\n\s*\|[-\s|]+\|\s*\n((?:\|[^\n]+\|\s*\n)+)",
        prd_content,
        re.MULTILINE,
    )
    
    if not matrix_match:
        return capabilities
    
    table_rows = matrix_match.group(1).strip().split("\n")
    
    for row in table_rows:
        # Parse table row: | Capability | Status | Notes | Key Files |
        cells = [c.strip() for c in row.split("|")[1:-1]]
        if len(cells) >= 4:
            capability = cells[0].strip()
            status = cells[1].strip()
            notes = cells[2].strip()
            key_files_raw = cells[3].strip()
            
            # Extract file paths from backticks
            file_paths = re.findall(r"`([^`]+)`", key_files_raw)
            
            capabilities.append({
                "capability": capability,
                "status": status,
                "notes": notes,
                "key_files": file_paths,
            })
    
    return capabilities


def infer_test_file(source_path: str, repo_root: Path) -> Optional[str]:
    """Infer test file path from source file."""
    p = Path(source_path)
    
    # Python files
    if p.suffix == ".py":
        # app/bridge/codex_tools.py -> app/bridge/tests/test_codex_tools.py
        test_candidates = [
            p.parent / "tests" / f"test_{p.name}",
            p.parent / f"test_{p.name}",
            p.parent.parent / "tests" / f"test_{p.name}",
        ]
        for candidate in test_candidates:
            if (repo_root / candidate).exists():
                return str(candidate)
    
    # TypeScript/TSX files
    if p.suffix in (".ts", ".tsx"):
        # Look for .test.tsx or .test.ts sibling
        test_candidates = [
            p.with_suffix(".test.tsx"),
            p.with_suffix(".test.ts"),
            p.parent / f"{p.stem}.test.tsx",
            p.parent / f"{p.stem}.test.ts",
        ]
        for candidate in test_candidates:
            if (repo_root / candidate).exists():
                return str(candidate)
    
    return None


def check_files(capabilities: list[dict], repo_root: Path) -> list[CapabilityTrace]:
    """Check existence of source and test files."""
    traces = []
    
    for cap in capabilities:
        file_checks = []
        
        for file_path in cap["key_files"]:
            full_path = repo_root / file_path
            exists = full_path.exists()
            
            test_file = infer_test_file(file_path, repo_root)
            test_exists = bool(test_file and (repo_root / test_file).exists())
            
            file_checks.append(FileCheck(
                path=file_path,
                exists=exists,
                test_file=test_file,
                test_exists=test_exists,
            ))
        
        all_exist = all(f.exists for f in file_checks) if file_checks else True
        has_tests = any(f.test_exists for f in file_checks)
        
        traces.append(CapabilityTrace(
            capability=cap["capability"],
            status=cap["status"],
            notes=cap["notes"],
            files=file_checks,
            all_files_exist=all_exist,
            has_tests=has_tests,
        ))
    
    return traces


def run_regression_tests(repo_root: Path) -> tuple[bool, dict]:
    """Run the regression gate tests and return results."""
    results = {
        "python_codex_tools": {"passed": 0, "failed": 0, "ok": False},
        "python_rag": {"passed": 0, "failed": 0, "ok": False},
        "ui_tests": {"passed": 0, "failed": 0, "ok": False},
    }
    
    # Python codex tools tests
    try:
        proc = subprocess.run(
            ["python3", "-m", "pytest", 
             "app/bridge/tests/test_codex_tools.py",
             "app/bridge/tests/test_codex_t2_tools.py",
             "-v", "--tb=no", "-q"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=120,
        )
        # Parse pytest output for pass/fail counts
        match = re.search(r"(\d+) passed", proc.stdout + proc.stderr)
        if match:
            results["python_codex_tools"]["passed"] = int(match.group(1))
        results["python_codex_tools"]["ok"] = proc.returncode == 0
    except Exception as e:
        results["python_codex_tools"]["error"] = str(e)
    
    # Python RAG tests
    try:
        proc = subprocess.run(
            ["python3", "-m", "pytest",
             "app/bridge/tests/test_codex_rag.py",
             "app/bridge/tests/test_codex_pr4_rag.py",
             "-v", "--tb=no", "-q"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=120,
        )
        match = re.search(r"(\d+) passed", proc.stdout + proc.stderr)
        if match:
            results["python_rag"]["passed"] = int(match.group(1))
        results["python_rag"]["ok"] = proc.returncode == 0
    except Exception as e:
        results["python_rag"]["error"] = str(e)
    
    # UI tests
    try:
        proc = subprocess.run(
            ["npm", "test", "--", "--run"],
            cwd=repo_root / "app" / "ui" / "ops-console",
            capture_output=True,
            text=True,
            timeout=120,
        )
        match = re.search(r"(\d+) passed", proc.stdout + proc.stderr)
        if match:
            results["ui_tests"]["passed"] = int(match.group(1))
        results["ui_tests"]["ok"] = proc.returncode == 0
    except Exception as e:
        results["ui_tests"]["error"] = str(e)
    
    all_passed = all(r.get("ok", False) for r in results.values())
    return all_passed, results


def generate_report(
    prd_path: Path,
    repo_root: Path,
    run_tests: bool = False,
) -> TraceabilityReport:
    """Generate full traceability report."""
    
    prd_content = prd_path.read_text()
    prd_version = parse_prd_version(prd_content)
    branch, commit = get_git_info(repo_root)
    
    capabilities = parse_implementation_matrix(prd_content)
    traces = check_files(capabilities, repo_root)
    
    tests_passed = None
    test_results = None
    if run_tests:
        tests_passed, test_results = run_regression_tests(repo_root)
    
    # Summary stats
    total_caps = len(traces)
    implemented = sum(1 for t in traces if t.status == "Implemented")
    partial = sum(1 for t in traces if t.status == "Partial")
    files_ok = sum(1 for t in traces if t.all_files_exist)
    with_tests = sum(1 for t in traces if t.has_tests)
    
    summary = {
        "total_capabilities": total_caps,
        "implemented": implemented,
        "partial": partial,
        "files_verified": files_ok,
        "with_tests": with_tests,
        "coverage_pct": round(100 * files_ok / total_caps, 1) if total_caps else 0,
    }
    
    return TraceabilityReport(
        prd_path=str(prd_path.relative_to(repo_root)),
        prd_version=prd_version,
        branch=branch,
        commit=commit,
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        capabilities=[asdict(t) for t in traces],
        tests_run=run_tests,
        tests_passed=tests_passed,
        test_results=test_results,
        summary=summary,
    )


def main():
    parser = argparse.ArgumentParser(description="PRD traceability check for handoffs")
    parser.add_argument(
        "--prd",
        default="docs/PRD_EMBEDDED_VECTORING.md",
        help="Path to PRD file (relative to repo root)",
    )
    parser.add_argument(
        "--run-tests",
        action="store_true",
        help="Run regression gate tests",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output JSON file path (default: stdout)",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress console summary",
    )
    
    args = parser.parse_args()
    
    # Find repo root
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    prd_path = repo_root / args.prd
    
    if not prd_path.exists():
        print(f"Error: PRD not found at {prd_path}", file=sys.stderr)
        sys.exit(1)
    
    report = generate_report(prd_path, repo_root, run_tests=args.run_tests)
    report_dict = asdict(report)
    
    # Output JSON
    json_output = json.dumps(report_dict, indent=2)
    
    if args.output:
        Path(args.output).write_text(json_output)
        if not args.quiet:
            print(f"Traceability report written to: {args.output}")
    else:
        print(json_output)
    
    # Console summary
    if not args.quiet and args.output:
        s = report.summary
        print(f"\n=== Traceability Summary ===")
        print(f"PRD: {report.prd_path} (v{report.prd_version})")
        print(f"Branch: {report.branch} @ {report.commit}")
        print(f"Capabilities: {s['implemented']} implemented, {s['partial']} partial / {s['total_capabilities']} total")
        print(f"Files verified: {s['files_verified']}/{s['total_capabilities']} ({s['coverage_pct']}%)")
        print(f"With tests: {s['with_tests']}/{s['total_capabilities']}")
        if report.tests_run:
            status = "✓ PASSED" if report.tests_passed else "✗ FAILED"
            print(f"Regression tests: {status}")
    
    # Exit code based on file verification
    if not all(t["all_files_exist"] for t in report_dict["capabilities"]):
        sys.exit(1)
    if report.tests_run and not report.tests_passed:
        sys.exit(1)
    
    sys.exit(0)


if __name__ == "__main__":
    main()

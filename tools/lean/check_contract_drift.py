#!/usr/bin/env python3
"""Detect obvious contract drift in docs/contracts artifacts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

VERSIONED_NAME_RE = re.compile(r"^(.+)_v(\d+)$")
ALLOWED_EXTS = {".md", ".json", ".yaml", ".yml"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contracts-root", required=True, help="Contracts root directory")
    parser.add_argument("--fail-on-drift", action="store_true", help="Exit non-zero on drift")
    args = parser.parse_args()

    root = Path(args.contracts_root)
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"[check_contract_drift] contracts root missing: {root}")

    files = [p for p in root.rglob("*") if p.is_file() and p.suffix in ALLOWED_EXTS]
    if not files:
        raise SystemExit("[check_contract_drift] no contract artifacts found")

    drift: list[str] = []
    versioned = 0

    for file_path in sorted(files):
        if file_path.suffix == ".json":
            try:
                json.loads(file_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                drift.append(f"invalid JSON: {file_path} ({exc})")

        stem = file_path.stem
        if VERSIONED_NAME_RE.match(stem):
            versioned += 1

    if versioned == 0:
        drift.append("no versioned contract files found (expected *_vN naming)")

    if drift:
        status = "FAIL" if args.fail_on_drift else "WARN"
        print(f"[check_contract_drift] {status}")
        for item in drift:
            print(f"- {item}")
        return 1 if args.fail_on_drift else 0

    print(
        "[check_contract_drift] PASS "
        f"(contracts={len(files)}, versioned={versioned}, root={root})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

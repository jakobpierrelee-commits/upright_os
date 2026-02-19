#!/usr/bin/env python3
"""
Trace replay runner for control output regression checks.

Usage:
  python3 tools/trace_replay_runner.py --input tests/results/run_123.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "app" / "bridge"))

from trace_replay import replay_file, to_json  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Path to run CSV trace")
    ap.add_argument("--output", default="", help="Optional JSON output path")
    ap.add_argument("--i-limit", type=float, default=70.0)
    ap.add_argument("--out-limit", type=float, default=180.0)
    ap.add_argument("--cmd-vel", type=float, default=0.0)
    ap.add_argument("--cmd-rmse-max", type=float, default=6.0)
    ap.add_argument("--cmd-abs-max", type=float, default=20.0)
    args = ap.parse_args()

    trace = Path(args.input)
    if not trace.exists():
        print(to_json({"ok": False, "error": f"input_not_found: {trace}"}))
        return 2

    report = replay_file(
        trace,
        i_limit=args.i_limit,
        out_limit=args.out_limit,
        cmd_vel=args.cmd_vel,
        cmd_rmse_max=args.cmd_rmse_max,
        cmd_abs_max=args.cmd_abs_max,
    )
    text = to_json(report)
    print(text)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + "\n", encoding="utf-8")

    result = report.get("result", {})
    if not result.get("ok"):
        return 2
    return 0 if result.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())

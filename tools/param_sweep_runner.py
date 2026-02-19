#!/usr/bin/env python3
"""
Hardware PID parameter sweep runner.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "app" / "bridge"))

from param_sweep import (  # noqa: E402
    ParameterSweepRunner,
    SweepConfig,
    parse_range_spec,
)
from serial_gateway import NanoSerialGateway  # noqa: E402


def _to_json(data: object) -> str:
    return json.dumps(data, indent=2, sort_keys=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--kp", default="30:33:1")
    ap.add_argument("--ki", default="0.04:0.08:0.02")
    ap.add_argument("--kd", default="1.0:1.4:0.2")
    ap.add_argument("--settle-s", type=float, default=1.0)
    ap.add_argument("--observe-s", type=float, default=3.0)
    ap.add_argument("--sample-rate-hz", type=float, default=8.0)
    ap.add_argument("--max-angle-variance", type=float, default=8.0)
    ap.add_argument("--max-output-saturation-pct", type=float, default=85.0)
    ap.add_argument("--require-no-oscillation", action="store_true")
    ap.add_argument("--max-candidates", type=int, default=120)
    ap.add_argument("--rollback-on-fail", action="store_true", default=True)
    ap.add_argument("--no-rollback-on-fail", action="store_true")
    ap.add_argument("--restore-baseline-at-end", action="store_true", default=True)
    ap.add_argument("--no-restore-baseline-at-end", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    rollback_on_fail = args.rollback_on_fail and not args.no_rollback_on_fail
    restore_baseline_at_end = args.restore_baseline_at_end and not args.no_restore_baseline_at_end

    config = SweepConfig(
        kp_values=parse_range_spec(args.kp),
        ki_values=parse_range_spec(args.ki),
        kd_values=parse_range_spec(args.kd),
        settle_s=args.settle_s,
        observe_s=args.observe_s,
        sample_rate_hz=args.sample_rate_hz,
        max_angle_variance=args.max_angle_variance,
        max_output_saturation_pct=args.max_output_saturation_pct,
        require_no_oscillation=args.require_no_oscillation,
        max_candidates=args.max_candidates,
        rollback_on_fail=rollback_on_fail,
        restore_baseline_at_end=restore_baseline_at_end,
        dry_run=args.dry_run,
    )

    gateway = NanoSerialGateway(port=args.port, baud=args.baud)
    try:
        gateway.connect()
        gateway.wait_ready(timeout=15.0)
        runner = ParameterSweepRunner(gateway)
        report = runner.run(config)
        text = _to_json(report)
        print(text)
        if args.output:
            out = Path(args.output)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text + "\n", encoding="utf-8")
        return 0
    except Exception as exc:
        print(_to_json({"ok": False, "error": str(exc)}))
        return 2
    finally:
        gateway.close()


if __name__ == "__main__":
    raise SystemExit(main())

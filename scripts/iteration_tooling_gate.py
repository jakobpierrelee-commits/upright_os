#!/usr/bin/env python3
"""
Phase 4 acceptance/regression gate for iteration tooling.

Runs non-hardware checks by default:
- Control math parity tests
- Trace replay tests
- Parameter sweep tests
- Trace replay runner nominal pass / regressed fail checks

Optional hardware check can be enabled via --with-hardware.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class StepResult:
    name: str
    cmd: List[str]
    returncode: int
    expected_codes: List[int]
    ok: bool
    stdout_tail: str
    stderr_tail: str


def _tail(text: str, max_lines: int = 14) -> str:
    lines = text.splitlines()
    return "\n".join(lines[-max_lines:])


def _run_step(name: str, cmd: List[str], expected_codes: List[int]) -> StepResult:
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    ok = proc.returncode in expected_codes
    return StepResult(
        name=name,
        cmd=cmd,
        returncode=proc.returncode,
        expected_codes=expected_codes,
        ok=ok,
        stdout_tail=_tail(proc.stdout),
        stderr_tail=_tail(proc.stderr),
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-hardware", action="store_true", help="Run hardware sweep command (requires serial device)")
    ap.add_argument("--port", default="", help="Serial port for hardware sweep (required with --with-hardware)")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument(
        "--output",
        default="tests/results/iteration_tooling/phase4_gate_report.json",
        help="JSON report output path",
    )
    args = ap.parse_args()

    steps: List[StepResult] = []
    started = time.time()

    steps.append(
        _run_step(
            "pytest:control_math_parity",
            ["python3", "-m", "pytest", "app/bridge/tests/test_control_math_parity.py", "-q"],
            [0],
        )
    )
    steps.append(
        _run_step(
            "pytest:trace_replay",
            ["python3", "-m", "pytest", "app/bridge/tests/test_trace_replay_runner.py", "-q"],
            [0],
        )
    )
    steps.append(
        _run_step(
            "pytest:param_sweep",
            ["python3", "-m", "pytest", "app/bridge/tests/test_param_sweep_runner.py", "-q"],
            [0],
        )
    )
    steps.append(
        _run_step(
            "trace_replay_runner:nominal",
            [
                "python3",
                "tools/trace_replay_runner.py",
                "--input",
                "app/bridge/tests/fixtures/trace_replay_nominal.csv",
                "--cmd-rmse-max",
                "1",
                "--cmd-abs-max",
                "3",
            ],
            [0],
        )
    )
    steps.append(
        _run_step(
            "trace_replay_runner:regressed_expected_fail",
            [
                "python3",
                "tools/trace_replay_runner.py",
                "--input",
                "app/bridge/tests/fixtures/trace_replay_regressed.csv",
                "--cmd-rmse-max",
                "5",
                "--cmd-abs-max",
                "10",
            ],
            [1],
        )
    )

    if args.with_hardware:
        if not args.port:
            print("ERROR: --port is required with --with-hardware")
            return 2
        steps.append(
            _run_step(
                "param_sweep_runner:hardware_smoke",
                [
                    "python3",
                    "tools/param_sweep_runner.py",
                    "--port",
                    args.port,
                    "--baud",
                    str(args.baud),
                    "--kp",
                    "31,32",
                    "--ki",
                    "0.05",
                    "--kd",
                    "1.05",
                    "--observe-s",
                    "1.5",
                    "--settle-s",
                    "0.5",
                    "--max-candidates",
                    "10",
                    "--output",
                    "tests/results/iteration_tooling/hardware_sweep_smoke.json",
                    "--csv-output",
                    "tests/results/iteration_tooling/hardware_sweep_smoke.csv",
                ],
                [0],
            )
        )

    overall_ok = all(step.ok for step in steps)
    report = {
        "ok": overall_ok,
        "duration_s": round(time.time() - started, 3),
        "step_count": len(steps),
        "passed_steps": sum(1 for step in steps if step.ok),
        "steps": [
            {
                "name": step.name,
                "ok": step.ok,
                "returncode": step.returncode,
                "expected_codes": step.expected_codes,
                "cmd": step.cmd,
                "stdout_tail": step.stdout_tail,
                "stderr_tail": step.stderr_tail,
            }
            for step in steps
        ],
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Gate: {'PASS' if overall_ok else 'FAIL'} ({report['passed_steps']}/{report['step_count']})")
    print(f"Report: {out_path}")
    for step in steps:
        status = "PASS" if step.ok else "FAIL"
        print(f"- {status} {step.name} (rc={step.returncode}, expected={step.expected_codes})")

    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

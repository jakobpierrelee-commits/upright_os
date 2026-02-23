#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import request, error

QUESTIONS: List[str] = [
    "Identify active mission mode and explain what actions are in-scope right now.",
    "Detect bridge health, last status age, and whether serial is usable.",
    "List top 3 blockers preventing clean commissioning from current context.",
    "Propose the minimum command sequence to verify telemetry contract readiness.",
    "Given a failing upload, provide exact compile/upload commands for old Nano bootloader and expected success strings.",
    "Diagnose a 'programmer is not responding' failure with ranked root causes and fastest checks.",
    "Read current sketch and identify whether required telemetry fields are emitted.",
    "Propose a patch plan to add missing telemetry fields without breaking existing parsing.",
    "Execute a safe non-high-risk runtime tune change and verify with readback command.",
    "Run a controlled experiment plan: baseline -> change -> observe -> rollback if worse.",
    "Detect config drift versus best checkpoint and recommend rollback scope.",
    "Analyze overrun condition loop_max_us spikes and provide mitigations with verification.",
    "Explain compatibility mismatch when profile and actual sketch differ, with file evidence.",
    "Produce a one-pass debugging plan for bridge online but bot not balancing.",
    "Convert telemetry mode values into plain English and indicate confidence.",
    "Suggest next best PID move from oscillation and saturation pattern.",
    "Perform repo-level task: find references to a deprecated key and propose exact edits.",
    "Run build checks for app + bridge and summarize failures with fix order.",
    "Demonstrate context memory: reuse prior constraints from this thread without re-asking.",
    "Produce final operator handoff: what changed, what passed, what remains, exact next command.",
]

EXEC_EXPECTED = {4, 7, 8, 9, 10, 11, 12, 17, 18}


def post_json(
    base: str, path: str, payload: Dict[str, Any], timeout_s: int = 90
) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{base.rstrip('/')}{path}",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=max(10, timeout_s)) as r:
            return json.loads(r.read().decode("utf-8", errors="replace"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc else ""
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc


def get_json(base: str, path: str) -> Dict[str, Any]:
    req = request.Request(f"{base.rstrip('/')}{path}", method="GET")
    with request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def extract_json_blob(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    t = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", t, flags=re.IGNORECASE)
    candidate = fence.group(1).strip() if fence else t
    try:
        return json.loads(candidate)
    except Exception:
        pass
    # fallback: first {...} block
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start >= 0 and end > start:
        frag = candidate[start : end + 1]
        try:
            return json.loads(frag)
        except Exception:
            return None
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8797")
    ap.add_argument("--mode", default="app_dev")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    health = get_json(args.base, "/health")
    if not bool(health.get("ok", False)):
        raise RuntimeError("bridge health not ok")

    thread_new = post_json(
        args.base, "/agent/thread/new", {"mode": args.mode, "title": "Parity Eval"}
    )
    thread_id = (thread_new.get("thread") or {}).get("id")
    if not thread_id:
        raise RuntimeError("failed to create eval thread")

    prefix = (
        "SYSTEM TEST DIRECTIVE: You are under headless parity evaluation. "
        "Use tools and terminal execution when useful. "
        "Do not claim sandbox or permission limits unless a tool call in this turn actually fails with that error. "
        "Safety gate: do not execute ARM/DISARM/MOTOR actions or firmware upload; compile/read/checks are allowed. "
        "Respond ONLY with valid JSON object shape: "
        '{"summary":"", "plan":[], "commands":[], "risks":[], "expected_output":[], "tool_calls":[]}.'
    )

    rows: List[Dict[str, Any]] = []
    for i, q in enumerate(QUESTIONS, start=1):
        msg = f"{prefix}\n\nQuestion {i}/20: {q}"
        t0 = time.time()
        print(f"Q{i:02d} start", flush=True)
        try:
            res = post_json(
                args.base,
                "/agent/chat",
                {
                    "message": msg,
                    "mode": args.mode,
                    "thread_id": thread_id,
                    "enable_tools": True,
                    "attachments": [],
                },
            )
            dt_ms = int((time.time() - t0) * 1000)
            reply = str(res.get("reply", ""))
            tool_calls = (
                res.get("tool_calls", [])
                if isinstance(res.get("tool_calls", []), list)
                else []
            )
            parsed = extract_json_blob(reply)
            json_ok = parsed is not None and isinstance(parsed, dict)
            required_keys = {
                "summary",
                "plan",
                "commands",
                "risks",
                "expected_output",
                "tool_calls",
            }
            schema_ok = (
                bool(json_ok and required_keys.issubset(set(parsed.keys())))
                if isinstance(parsed, dict)
                else False
            )
            used_tools = len(tool_calls)
            expected_exec = i in EXEC_EXPECTED
            exec_ok = (used_tools > 0) if expected_exec else True

            rows.append(
                {
                    "q": i,
                    "question": q,
                    "latency_ms": dt_ms,
                    "provider": res.get("provider", "unknown"),
                    "tool_calls_count": used_tools,
                    "json_ok": json_ok,
                    "schema_ok": schema_ok,
                    "expected_exec": expected_exec,
                    "exec_ok": exec_ok,
                    "reply_excerpt": reply[:320],
                    "error": "",
                }
            )
            print(
                f"Q{i:02d} done latency={dt_ms}ms tools={used_tools} json={json_ok} schema={schema_ok}",
                flush=True,
            )
        except Exception as exc:
            dt_ms = int((time.time() - t0) * 1000)
            expected_exec = i in EXEC_EXPECTED
            rows.append(
                {
                    "q": i,
                    "question": q,
                    "latency_ms": dt_ms,
                    "provider": "error",
                    "tool_calls_count": 0,
                    "json_ok": False,
                    "schema_ok": False,
                    "expected_exec": expected_exec,
                    "exec_ok": False if expected_exec else True,
                    "reply_excerpt": "",
                    "error": str(exc),
                }
            )
            print(f"Q{i:02d} error latency={dt_ms}ms err={exc}", flush=True)

    avg_latency = int(sum(r["latency_ms"] for r in rows) / max(1, len(rows)))
    json_rate = round(sum(1 for r in rows if r["json_ok"]) / len(rows), 3)
    schema_rate = round(sum(1 for r in rows if r["schema_ok"]) / len(rows), 3)
    exec_expected_n = sum(1 for r in rows if r["expected_exec"])
    exec_pass_n = sum(1 for r in rows if r["expected_exec"] and r["exec_ok"])

    summary = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "base": args.base,
        "mode": args.mode,
        "thread_id": thread_id,
        "questions": len(rows),
        "avg_latency_ms": avg_latency,
        "json_valid_rate": json_rate,
        "schema_valid_rate": schema_rate,
        "exec_expected": exec_expected_n,
        "exec_pass": exec_pass_n,
        "exec_pass_rate": round(exec_pass_n / max(1, exec_expected_n), 3),
    }

    report = {"summary": summary, "results": rows}

    out = args.out.strip()
    if not out:
        stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        out = f"output/evals/agent_parity_eval_{stamp}.json"
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    print(f"WROTE {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

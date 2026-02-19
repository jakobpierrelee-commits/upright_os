#!/usr/bin/env python3
"""Embedded Vectoring smoke checks.

Validates endpoint availability and auth/error contracts for key surfaces:
- RAG stats/index
- Thread APIs
- Playground tooling APIs

Usage:
  python3 scripts/embedded_vectoring_smoke.py --base http://127.0.0.1:8787
  python3 scripts/embedded_vectoring_smoke.py --base http://127.0.0.1:8787 --token <session_token>
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Iterable, Optional, Tuple


@dataclass
class Check:
    name: str
    method: str
    path: str
    expected_codes: Tuple[int, ...]
    body: Optional[dict] = None


def _req(base: str, check: Check, token: Optional[str]) -> Tuple[int, str]:
    url = f"{base.rstrip('/')}{check.path}"
    payload = None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if check.body is not None:
        payload = json.dumps(check.body).encode("utf-8")

    req = urllib.request.Request(url, data=payload, method=check.method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return int(resp.status), body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return int(exc.code), body
    except urllib.error.URLError as exc:
        return -1, f"url_error:{exc}"
    except Exception as exc:
        return -1, f"request_error:{exc}"


def _contains_any(text: str, patterns: Iterable[str]) -> bool:
    low = text.lower()
    return any(p.lower() in low for p in patterns)


def run(base: str, token: Optional[str]) -> int:
    checks = [
        Check("health", "GET", "/health", (200,)),
        Check("rag_stats", "GET", "/ai/rag/stats", (200, 401, 503)),
        Check("rag_index", "POST", "/ai/rag/index", (200, 400, 401, 503), {"force_reindex": False}),
        Check("ai_status", "GET", "/ai/status", (200,)),
        Check("ai_threads", "GET", "/ai/threads", (200, 401)),
        Check("ai_thread_new", "POST", "/ai/thread/new", (200, 401), {"title": "Smoke"}),
        Check("tooling_traces", "GET", "/tooling/traces", (200,)),
        Check("tooling_surrogate", "POST", "/tooling/surrogate/simulate", (200, 400, 422), {
            "trace_paths": [],
            "kp": 31.0,
            "ki": 0.05,
            "kd": 1.05,
            "setpoint": 0.0,
            "duration_s": 2.0,
        }),
        Check("tooling_trace_replay", "POST", "/tooling/trace-replay", (200, 400, 404), {
            "trace_path": "",
        }),
        Check("tooling_param_sweep", "POST", "/tooling/param-sweep", (200, 500), {
            "kp_spec": "31",
            "ki_spec": "0.05",
            "kd_spec": "1.05",
            "dry_run": True,
        }),
    ]

    failures = []
    print("== Embedded Vectoring Smoke ==")
    print(f"base={base}")
    print(f"token={'yes' if token else 'no'}")

    for c in checks:
        code, body = _req(base, c, token)
        ok = code in c.expected_codes

        # Validate JSON-ish response contract where relevant.
        if ok and c.name in {"ai_status", "health", "tooling_traces"}:
            ok = _contains_any(body, ["\"ok\"", "\"health\"", "\"traces\""])

        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {c.name}: code={code} expected={c.expected_codes}")

        if not ok:
            failures.append((c.name, code, c.expected_codes, body[:240]))

    if failures:
        print("\nFailures:")
        for name, code, expected, snippet in failures:
            print(f"- {name}: code={code}, expected={expected}, body={snippet}")
        return 1

    print("\nAll smoke checks passed.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8787")
    ap.add_argument("--token", default="")
    args = ap.parse_args()
    return run(args.base, args.token.strip() or None)


if __name__ == "__main__":
    raise SystemExit(main())

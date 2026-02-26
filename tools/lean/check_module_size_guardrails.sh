#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONFIG_PATH="${ROOT_DIR}/tools/lean/module_size_guardrails.json"

if [[ ! -f "${CONFIG_PATH}" ]]; then
  echo "[check_module_size_guardrails] missing config: ${CONFIG_PATH}"
  exit 1
fi

python3 - "${ROOT_DIR}" "${CONFIG_PATH}" <<'PY'
import ast
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
config_path = Path(sys.argv[2])
cfg = json.loads(config_path.read_text(encoding="utf-8"))

tracked = list(cfg.get("tracked_files") or [])
defaults = dict(cfg.get("defaults") or {})
exceptions = list(cfg.get("exceptions") or [])

if not tracked:
    raise SystemExit("[check_module_size_guardrails] tracked_files is empty")

exc_map = {}
for ex in exceptions:
    if not isinstance(ex, dict):
        raise SystemExit("[check_module_size_guardrails] invalid exception entry")
    path = str(ex.get("path", "")).strip()
    owner = str(ex.get("owner", "")).strip()
    reason = str(ex.get("reason", "")).strip()
    if not path or not owner or not reason:
        raise SystemExit(
            "[check_module_size_guardrails] exception missing required fields (path/owner/reason)"
        )
    if path in exc_map:
        raise SystemExit(
            f"[check_module_size_guardrails] duplicate exception path: {path}"
        )
    exc_map[path] = ex

for path in exc_map:
    if path not in tracked:
        raise SystemExit(
            f"[check_module_size_guardrails] exception path not in tracked_files: {path}"
        )

max_lines_by_ext = dict(defaults.get("max_lines_by_ext") or {})
max_functions_by_ext = dict(defaults.get("max_functions_by_ext") or {})
max_function_lines_by_ext = dict(defaults.get("max_function_lines_by_ext") or {})
max_selectors_by_ext = dict(defaults.get("max_selectors_by_ext") or {})

failures = []

def selector_count(lines: list[str]) -> int:
    count = 0
    for ln in lines:
        s = ln.strip()
        if not s or s.startswith("@"):
            continue
        if "{" in s:
            count += 1
    return count

def py_metrics(text: str) -> dict:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return {"parse_error": f"{exc}"}
    funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    spans = []
    for fn in funcs:
        end = getattr(fn, "end_lineno", None)
        if isinstance(end, int):
            spans.append(end - fn.lineno + 1)
    return {
        "functions": len(funcs),
        "max_function_lines": max(spans) if spans else 0,
    }

print("[check_module_size_guardrails] evaluating tracked files...")
for rel in tracked:
    path = root / rel
    if not path.exists():
        failures.append(f"{rel}: missing file")
        continue

    ext = path.suffix.lower()
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    metrics = {"lines": len(lines)}

    if ext == ".py":
        metrics.update(py_metrics(text))
        if "parse_error" in metrics:
            failures.append(f"{rel}: python_parse_error={metrics['parse_error']}")
            continue
    if ext == ".css":
        metrics["selectors"] = selector_count(lines)

    thresholds = {
        "max_lines": max_lines_by_ext.get(ext),
        "max_functions": max_functions_by_ext.get(ext),
        "max_function_lines": max_function_lines_by_ext.get(ext),
        "max_selectors": max_selectors_by_ext.get(ext),
    }

    ex = exc_map.get(rel)
    if ex:
        allow = ex.get("allow") or {}
        for key in ("max_lines", "max_functions", "max_function_lines", "max_selectors"):
            if key in allow:
                thresholds[key] = allow[key]

    checks = [
        ("lines", "max_lines"),
        ("functions", "max_functions"),
        ("max_function_lines", "max_function_lines"),
        ("selectors", "max_selectors"),
    ]

    status = "PASS"
    for metric_key, threshold_key in checks:
        threshold = thresholds.get(threshold_key)
        value = metrics.get(metric_key)
        if threshold is None or value is None:
            continue
        if int(value) > int(threshold):
            status = "FAIL"
            failures.append(
                f"{rel}: {metric_key}={value} exceeds {threshold_key}={threshold}"
            )

    ex_tag = " exception" if ex else ""
    detail = ", ".join([f"{k}={v}" for k, v in metrics.items()])
    print(f"  [{status}]{ex_tag} {rel} :: {detail}")

if failures:
    print("[check_module_size_guardrails] FAIL")
    for f in failures:
        print(f"  - {f}")
    raise SystemExit(1)

print("[check_module_size_guardrails] PASS")
PY

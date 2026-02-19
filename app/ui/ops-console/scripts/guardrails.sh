#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SRC_DIR="$ROOT_DIR/src"

violations=0
check() {
  local name="$1"
  local pattern="$2"
  if rg -n --pcre2 "$pattern" "$SRC_DIR" -g'*.ts' -g'*.tsx' >/tmp/guardrail_hits.txt; then
    echo "[FAIL] $name"
    cat /tmp/guardrail_hits.txt
    violations=1
  else
    echo "[OK]   $name"
  fi
}

check "No inline JSX styles" 'style=\{\{'
check "No ts-ignore / ts-expect-error" '@ts-ignore|@ts-expect-error|ts-nocheck'
check "No any-casts" 'as\s+any\b'
check "No prototype mutation patterns" '(^|[^A-Za-z])([A-Za-z_$][A-Za-z0-9_$]*)\.prototype\.[A-Za-z_$][A-Za-z0-9_$]*\s*='
check "No global/window monkey-patch assignment" '(window|globalThis)\.[A-Za-z_$][A-Za-z0-9_$]*\s*='
check "No Object.defineProperty monkey-patch" 'Object\.defineProperty\s*\('

if [[ "$violations" -ne 0 ]]; then
  echo "\nGuardrail violations found."
  exit 1
fi

echo "\nGuardrails passed."

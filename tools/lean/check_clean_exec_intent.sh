#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-http://127.0.0.1:8797}"
MODE="${MODE:-app_dev}"

need_jq() { command -v jq >/dev/null 2>&1; }
if ! need_jq; then
  echo "[check_clean_exec_intent] jq is required"
  exit 1
fi

echo "[check_clean_exec_intent] BASE=${BASE} MODE=${MODE}"

payload="$(jq -nc --arg mode "${MODE}" '{mode:$mode,with_compile:false}')"
resp="$(curl -fsS -X POST "${BASE}/agent/clean/preflight" -H 'Content-Type: application/json' -d "${payload}")"

echo "${resp}" | jq -e '.ok == true' >/dev/null
echo "${resp}" | jq -e '.failures == 0' >/dev/null
echo "${resp}" | jq -e '([.results[] | select(.expect_tools == true)] | length) >= 2' >/dev/null
echo "${resp}" | jq -e 'all(.results[] | select(.expect_tools == true); (.tool_calls | length) > 0)' >/dev/null

pass_n="$(echo "${resp}" | jq -r '[.results[] | select(.ok == true)] | length')"
total_n="$(echo "${resp}" | jq -r '.results | length')"
echo "[check_clean_exec_intent] PASS (${pass_n}/${total_n})"

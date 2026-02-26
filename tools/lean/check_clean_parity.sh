#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-http://127.0.0.1:8797}"
MODE="${MODE:-app_dev}"
MAX_MS="${MAX_MS:-45000}"
MAX_MS_TOOLS="${MAX_MS_TOOLS:-120000}"
Q_COUNT=6

need_jq() { command -v jq >/dev/null 2>&1; }
if ! need_jq; then
  echo "[check_clean_parity] jq is required"
  exit 1
fi

questions=(
  "one line only: parity check q1 ok"
  "run connect probe [tool:connect_probe] and summarize in one line"
  "run compat probe [tool:compat_probe] and summarize in one line"
  "compile profiled runtime [tool:compile_profiled_runtime_v1] and report one-line result"
  "one line: confirm clean lane is codex-cli runtime"
  "one line only: parity check complete"
)

echo "[check_clean_parity] BASE=${BASE} MODE=${MODE} MAX_MS=${MAX_MS} MAX_MS_TOOLS=${MAX_MS_TOOLS}"

health="$(curl -fsS "${BASE}/health")"
echo "${health}" | jq -e '.ok == true' >/dev/null

status="$(curl -fsS "${BASE}/agent/clean/status?mode=${MODE}")"
echo "${status}" | jq -e '.ok == true' >/dev/null
echo "${status}" | jq -e '.agent.provider == "codex_cli"' >/dev/null

thread="$(curl -fsS -X POST "${BASE}/agent/clean/thread/new" \
  -H 'Content-Type: application/json' \
  -d "{\"mode\":\"${MODE}\",\"title\":\"Clean Parity\"}")"
echo "${thread}" | jq -e '.ok == true' >/dev/null
thread_id="$(echo "${thread}" | jq -r '.thread.id')"

sum_ms=0
max_seen=0
failures=0

for ((i=0; i<${Q_COUNT}; i++)); do
  q="${questions[$i]}"
  auto_tools=false
  expect_tools=false
  limit_ms="${MAX_MS}"
  if [ "$i" -eq 1 ] || [ "$i" -eq 2 ] || [ "$i" -eq 3 ]; then
    auto_tools=true
    expect_tools=true
    limit_ms="${MAX_MS_TOOLS}"
  fi
  payload="$(jq -nc --arg mode "${MODE}" --arg message "${q}" --arg thread_id "${thread_id}" \
    --argjson auto_tools "${auto_tools}" \
    '{mode:$mode,message:$message,thread_id:$thread_id,auto_tools:$auto_tools}')"
  t0="$(python3 - <<'PY'
import time
print(int(time.time()*1000))
PY
)"
  resp="$(curl -sS -X POST "${BASE}/agent/clean/chat" -H 'Content-Type: application/json' -d "${payload}")"
  t1="$(python3 - <<'PY'
import time
print(int(time.time()*1000))
PY
)"
  dt=$((t1 - t0))
  sum_ms=$((sum_ms + dt))
  if [ "${dt}" -gt "${max_seen}" ]; then max_seen="${dt}"; fi

  ok="$(echo "${resp}" | jq -r '.ok // false')"
  provider="$(echo "${resp}" | jq -r '.provider // ""')"
  executor="$(echo "${resp}" | jq -r '.executor // ""')"
  reply_len="$(echo "${resp}" | jq -r '.reply // "" | length')"
  tool_calls_n="$(echo "${resp}" | jq -r '(.tool_calls // []) | length')"
  if [ "${ok}" != "true" ] || [ "${provider}" != "codex_cli" ] || [ "${executor}" != "codex_cli_exec" ] || [ "${reply_len}" -le 0 ]; then
    failures=$((failures + 1))
    echo "[check_clean_parity] q$((i+1)) FAIL dt_ms=${dt} resp=$(echo "${resp}" | tr '\n' ' ' | cut -c1-220)"
    continue
  fi
  if [ "${expect_tools}" = "true" ] && [ "${tool_calls_n}" -le 0 ]; then
    failures=$((failures + 1))
    echo "[check_clean_parity] q$((i+1)) NO_TOOLS dt_ms=${dt}"
    continue
  fi
  if [ "${dt}" -gt "${limit_ms}" ]; then
    failures=$((failures + 1))
    echo "[check_clean_parity] q$((i+1)) SLOW dt_ms=${dt} > ${limit_ms}"
    continue
  fi
  echo "[check_clean_parity] q$((i+1)) PASS dt_ms=${dt} tool_calls=${tool_calls_n}"
done

avg_ms=$((sum_ms / Q_COUNT))
echo "[check_clean_parity] avg_ms=${avg_ms} max_ms=${max_seen} failures=${failures}"

if [ "${failures}" -gt 0 ]; then
  echo "[check_clean_parity] FAIL"
  exit 1
fi

echo "[check_clean_parity] PASS"

#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-http://127.0.0.1:8797}"
MODE="${MODE:-app_dev}"
PROMPT="${PROMPT:-one line only: clean lane acceptance ok}"

need_jq() {
  command -v jq >/dev/null 2>&1
}

if ! need_jq; then
  echo "[check_clean_lane] jq is required"
  exit 1
fi

echo "[check_clean_lane] BASE=${BASE} MODE=${MODE}"

health="$(curl -fsS "${BASE}/health")"
echo "${health}" | jq -e '.ok == true' >/dev/null

status="$(curl -fsS "${BASE}/agent/clean/status?mode=${MODE}")"
echo "${status}" | jq -e '.ok == true' >/dev/null
echo "${status}" | jq -e '.agent.provider == "codex_cli"' >/dev/null
echo "${status}" | jq -e '.agent.executor == "codex_cli_exec" or .agent.executor == "blocked"' >/dev/null

thread="$(curl -fsS -X POST "${BASE}/agent/clean/thread/new" \
  -H 'Content-Type: application/json' \
  -d "{\"mode\":\"${MODE}\",\"title\":\"Clean Acceptance\"}")"
echo "${thread}" | jq -e '.ok == true' >/dev/null
thread_id="$(echo "${thread}" | jq -r '.thread.id')"

chat_payload="$(jq -nc --arg mode "${MODE}" --arg message "${PROMPT}" --arg thread_id "${thread_id}" \
  '{mode:$mode,message:$message,thread_id:$thread_id}')"
chat="$(curl -fsS -X POST "${BASE}/agent/clean/chat" \
  -H 'Content-Type: application/json' \
  -d "${chat_payload}" )"
echo "${chat}" | jq -e '.ok == true' >/dev/null
echo "${chat}" | jq -e '.provider == "codex_cli"' >/dev/null
echo "${chat}" | jq -e '.executor == "codex_cli_exec"' >/dev/null
echo "${chat}" | jq -e '(.reply|type) == "string" and (.reply|length) > 0' >/dev/null

echo "[check_clean_lane] PASS"
echo "[check_clean_lane] thread_id=${thread_id}"
echo "[check_clean_lane] reply=$(echo "${chat}" | jq -r '.reply' | tr '\n' ' ' | cut -c1-180)"

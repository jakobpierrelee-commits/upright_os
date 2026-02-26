#!/usr/bin/env bash
set -euo pipefail

BRIDGE_URL="${BRIDGE_URL:-http://127.0.0.1:8797/command}"

# Expected values for current test phase.
EXP_KP="${EXP_KP:-30.0000}"
EXP_KI="${EXP_KI:-0.0000}"
EXP_KD="${EXP_KD:-2.1000}"
EXP_KV="${EXP_KV:-0.0048}"
EXP_KX="${EXP_KX:-0.0002}"

raw="$(curl -s "$BRIDGE_URL" -H 'Content-Type: application/json' -d '{"cmd":"GET"}')"
if printf '%s' "$raw" | rg -q '"ok": false'; then
  err="$(printf '%s' "$raw" | sed -n 's/.*"error": "\([^"]*\)".*/\1/p')"
  echo "FAIL: bridge error: ${err:-unknown}"
  exit 2
fi

status="$(printf '%s' "$raw" | perl -ne 'if(/"matched"\s*:\s*"([^"]*)"/){print $1; exit}')"
if [[ -z "$status" ]]; then
  status="$(printf '%s' "$raw" | perl -ne 'if(/"lines"\s*:\s*\["([^"]*)"/){print $1; exit}')"
fi

if [[ -z "$status" ]]; then
  echo "FAIL: could not parse STATUS from bridge response"
  exit 2
fi

get_field() {
  local key="$1"
  printf '%s\n' "$status" | tr ' ' '\n' | awk -F= -v k="$key" '$1==k{print $2; exit}'
}

act_kp="$(get_field kp)"
act_ki="$(get_field ki)"
act_kd="$(get_field kd)"
act_kv="$(get_field kv)"
act_kx="$(get_field kx)"

fail=0
check_eq() {
  local name="$1" act="$2" exp="$3"
  if [[ "$act" != "$exp" ]]; then
    echo "MISMATCH: $name actual=$act expected=$exp"
    fail=1
  fi
}

check_eq kp "$act_kp" "$EXP_KP"
check_eq ki "$act_ki" "$EXP_KI"
check_eq kd "$act_kd" "$EXP_KD"
check_eq kv "$act_kv" "$EXP_KV"
check_eq kx "$act_kx" "$EXP_KX"

if [[ "$fail" -ne 0 ]]; then
  exit 1
fi

echo "OK: kp=$act_kp ki=$act_ki kd=$act_kd kv=$act_kv kx=$act_kx"

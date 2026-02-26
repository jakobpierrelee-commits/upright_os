#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-http://127.0.0.1:8797}"
MAX_TIME="${MAX_TIME:-20}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

if ! command -v jq >/dev/null 2>&1; then
  echo "[check_hardware_registry_contract] jq is required"
  exit 1
fi

echo "[check_hardware_registry_contract] BASE=${BASE}"

targets_json="${TMP_DIR}/targets.json"
profiles_json="${TMP_DIR}/profiles.json"

curl -fsS --max-time "${MAX_TIME}" "${BASE}/firmware/targets" > "${targets_json}"
curl -fsS --max-time "${MAX_TIME}" "${BASE}/profiles/hardware" > "${profiles_json}"

jq -e '.ok == true and .targets.ok == true and (.targets.version|type=="number") and (.targets.families|type=="array" and length>0) and (.targets.boards|type=="array" and length>0)' "${targets_json}" >/dev/null
jq -e '.ok == true and .registry.ok == true and (.registry.version|type=="number") and (.registry.families|type=="array" and length>0) and (.registry.boards|type=="array" and length>0)' "${profiles_json}" >/dev/null

jq -e '[.targets.families[].id] | unique | length > 0' "${targets_json}" >/dev/null
jq -e '[.registry.families[].id] | unique | length > 0' "${profiles_json}" >/dev/null

jq -e 'all(.targets.boards[]; (type=="object") and ((.id|type)=="string") and ((.id|length)>0) and ((.family|type)=="string") and ((.family|length)>0) and ((.fqbn_base|type)=="string") and ((.fqbn_base|length)>0) and ((.bootloaders|type)=="array") and ((.bootloaders|length)>0))' "${targets_json}" >/dev/null

jq -e 'all(.registry.boards[]; (type=="object") and ((.id|type)=="string") and ((.id|length)>0) and ((.family|type)=="string") and ((.family|length)>0) and ((.capabilities|type)=="object") and ((.required_runtime_fields|type)=="array") and ((.required_runtime_fields|length)>0))' "${profiles_json}" >/dev/null

jq -r '.targets.families[].id' "${targets_json}" | sort -u > "${TMP_DIR}/targets_families.txt"
jq -r '.registry.families[].id' "${profiles_json}" | sort -u > "${TMP_DIR}/profiles_families.txt"
diff -u "${TMP_DIR}/targets_families.txt" "${TMP_DIR}/profiles_families.txt" >/dev/null

jq -r '.targets.boards[].id' "${targets_json}" | sort -u > "${TMP_DIR}/targets_boards.txt"
jq -r '.registry.boards[].id' "${profiles_json}" | sort -u > "${TMP_DIR}/profiles_boards.txt"
diff -u "${TMP_DIR}/targets_boards.txt" "${TMP_DIR}/profiles_boards.txt" >/dev/null

echo "[check_hardware_registry_contract] PASS"

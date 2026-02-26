#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

DOC_PATH="${DOC_PATH:-docs/OVERHAUL_SPRINT_SCORECARD.md}"
RUN_GATES=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-gates)
      RUN_GATES=1
      shift
      ;;
    --doc)
      DOC_PATH="${2:-}"
      shift 2
      ;;
    *)
      echo "[update_scorecard] unknown arg: $1"
      echo "usage: $0 [--run-gates] [--doc <path>]"
      exit 1
      ;;
  esac
done

if [[ ! -f "${DOC_PATH}" ]]; then
  echo "[update_scorecard] missing doc: ${DOC_PATH}"
  exit 1
fi

if [[ "${RUN_GATES}" == "1" ]]; then
  echo "[update_scorecard] running clean gates..."
  ./tools/lean/check_clean_lane.sh
  ./tools/lean/check_clean_parity.sh
  ./tools/lean/check_clean_exec_intent.sh
  ./tools/lean/preflight_clean.sh
fi

TOTAL="$(grep -E '^- \[[ x]\]' "${DOC_PATH}" | wc -l | tr -d ' ')"
PASSED="$(grep -E '^- \[x\]' "${DOC_PATH}" | wc -l | tr -d ' ')"

if [[ "${TOTAL}" -eq 0 ]]; then
  echo "[update_scorecard] no checklist items found in ${DOC_PATH}"
  exit 1
fi

PCT="$(( (PASSED * 100) / TOTAL ))"
NEW_LINE="- Current sprint score: \`${PASSED} / ${TOTAL}\` (${PCT}%)"

TMP_FILE="$(mktemp)"
awk -v repl="${NEW_LINE}" '
  BEGIN { updated = 0 }
  {
    if (!updated && $0 ~ /^- Current sprint score:/) {
      print repl
      updated = 1
    } else {
      print $0
    }
  }
  END {
    if (!updated) {
      # Keep file valid even if the score line was removed; append at end.
      print ""
      print repl
    }
  }
' "${DOC_PATH}" > "${TMP_FILE}"

mv "${TMP_FILE}" "${DOC_PATH}"
echo "[update_scorecard] updated ${DOC_PATH}: ${PASSED}/${TOTAL} (${PCT}%)"

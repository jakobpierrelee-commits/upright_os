#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNLOG_DIR="${ROOT_DIR}/.runlogs"
mkdir -p "${RUNLOG_DIR}"

DEFAULT_BASELINE="recover/uiux-restore-2026-02-19"
EXPECTED_BASELINE="${1:-${EXPECTED_BASELINE_BRANCH:-${DEFAULT_BASELINE}}}"
STATE_FILE="${BRANCH_DRIFT_STATE_FILE:-${RUNLOG_DIR}/branch_drift_known_branches.txt}"

current_branch="$(git -C "${ROOT_DIR}" rev-parse --abbrev-ref HEAD)"
current_sha="$(git -C "${ROOT_DIR}" rev-parse --short HEAD)"
status_short="$(git -C "${ROOT_DIR}" status --short)"

latest_branch="$(git -C "${ROOT_DIR}" for-each-ref --sort=-committerdate --format='%(refname:short)' refs/heads | head -n 1)"
latest_branch_time="$(git -C "${ROOT_DIR}" for-each-ref --sort=-committerdate --format='%(committerdate:iso8601)' refs/heads | head -n 1)"

branch_snapshot_file="${RUNLOG_DIR}/branch_drift_current_branches.txt"
git -C "${ROOT_DIR}" for-each-ref --format='%(refname:short)' refs/heads | sort >"${branch_snapshot_file}"

new_branches=""
if [ -f "${STATE_FILE}" ]; then
  new_branches="$(comm -13 "${STATE_FILE}" "${branch_snapshot_file}" || true)"
fi

cp "${branch_snapshot_file}" "${STATE_FILE}"

reasons=()
if [ "${current_branch}" != "${EXPECTED_BASELINE}" ]; then
  reasons+=("active branch '${current_branch}' differs from expected baseline '${EXPECTED_BASELINE}'")
fi

if [ "${latest_branch}" != "${EXPECTED_BASELINE}" ]; then
  reasons+=("most recently updated branch is '${latest_branch}' (updated ${latest_branch_time}), not baseline '${EXPECTED_BASELINE}'")
fi

if [ -n "${new_branches}" ]; then
  reasons+=("new branch(es) detected since last check: ${new_branches//$'\n'/, }")
fi

if [ -n "${status_short}" ]; then
  reasons+=("working tree is dirty (uncommitted changes present)")
fi

echo "[branch-drift] branch=${current_branch} sha=${current_sha}"
echo "[branch-drift] baseline=${EXPECTED_BASELINE}"
echo "[branch-drift] latest_branch=${latest_branch} latest_branch_time=${latest_branch_time}"
if [ -n "${status_short}" ]; then
  echo "[branch-drift] git status --short:"
  echo "${status_short}"
else
  echo "[branch-drift] git status --short: clean"
fi

if [ "${#reasons[@]}" -gt 0 ]; then
  echo "[branch-drift] DRIFT_DETECTED"
  for reason in "${reasons[@]}"; do
    echo "- ${reason}"
  done
  echo "[branch-drift] Clarification required before implementation:"
  echo "1) Which branch is source of truth for this task?"
  echo "2) Should work continue on '${current_branch}' or another branch?"
  echo "3) Are current uncommitted changes intentional for this task scope?"
  exit 2
fi

echo "[branch-drift] no drift detected"

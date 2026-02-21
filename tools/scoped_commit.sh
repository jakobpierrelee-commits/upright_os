#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  tools/scoped_commit.sh -m "commit message" <path> [<path> ...]

Examples:
  tools/scoped_commit.sh -m "ui(setup): spacing polish" \
    app/ui/ops-console/src/styles.css \
    app/ui/ops-console/src/styles/themes.css
USAGE
}

msg=""
while getopts ":m:h" opt; do
  case "$opt" in
    m) msg="$OPTARG" ;;
    h)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 1
      ;;
  esac
done
shift $((OPTIND - 1))

if [[ -z "$msg" || "$#" -eq 0 ]]; then
  usage >&2
  exit 1
fi

if [[ -n "$(git rev-parse --is-inside-work-tree 2>/dev/null || true)" ]]; then
  :
else
  echo "Not inside a git repository." >&2
  exit 1
fi

branch="$(git branch --show-current)"
echo "Branch: ${branch}"
echo "Adding paths:"
for p in "$@"; do
  echo "  - ${p}"
  git add -- "$p"
done

echo
echo "Staged files:"
git diff --cached --name-only -- "$@"

echo
echo "Staged diffstat:"
git diff --cached --stat -- "$@"

echo
git commit -m "$msg"
echo "Committed scoped changes on ${branch}."

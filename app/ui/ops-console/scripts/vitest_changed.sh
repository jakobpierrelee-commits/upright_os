#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root/app/ui/ops-console"

changed_files="$(
  git -C "$repo_root" diff --name-only HEAD \
    | grep -E '^app/ui/ops-console/.*\.(ts|tsx)$' \
    | sed -e 's#^app/ui/ops-console/##' \
    | tr '\n' ' ' || true
)"

if [[ -z "${changed_files// }" ]]; then
  echo "No changed TS/TSX files detected. Running full vitest suite."
  exec npx vitest run
fi

echo "Running vitest related for changed files: ${changed_files}"
# shellcheck disable=SC2086
exec npx vitest related --run ${changed_files}

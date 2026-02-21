#!/usr/bin/env bash
set -euo pipefail

if python3 -c "import xdist" >/dev/null 2>&1; then
  exec python3 -m pytest -n auto "$@"
fi

exec python3 -m pytest "$@"

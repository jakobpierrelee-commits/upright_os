#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

echo "== Lean Inventory: high-surface UI files =="
rg -n "setup|playground|codex|tooling|wizard|mission" app/ui/ops-console/src/App.tsx app/ui/ops-console/src/pages app/ui/ops-console/src/features | sed -n '1,200p'

echo
echo "== Lean Inventory: bridge endpoints =="
rg -n "u.path ==" app/bridge/server.py | sed -n '1,260p'

echo
echo "== Lean Inventory: contract gates =="
rg -n "telemetry_contract_incomplete|probe/compat|probe/connect|action_gates" app/bridge/server.py app/ui/ops-console/src | sed -n '1,220p'

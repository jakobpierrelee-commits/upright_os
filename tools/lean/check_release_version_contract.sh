#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

echo "[check_release_version_contract] validating release.json sync..."
python3 tools/lean/sync_release_metadata.py --check
echo "[check_release_version_contract] PASS"

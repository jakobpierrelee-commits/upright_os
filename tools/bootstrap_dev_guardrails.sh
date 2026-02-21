#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

echo "Installing Python guardrails (pre-commit, ruff, pytest-xdist)..."
python3 -m pip install --upgrade pip
python3 -m pip install pre-commit ruff pytest-xdist

echo "Installing pre-commit hooks..."
pre-commit install

echo "Installing UI Playwright dependency..."
cd "$repo_root/app/ui/ops-console"
npm install
npx playwright install chromium

echo "Bootstrap complete."

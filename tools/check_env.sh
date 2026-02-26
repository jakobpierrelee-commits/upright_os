#!/usr/bin/env bash
set -euo pipefail

ok=0
warn=0

info() { printf "[INFO] %s\n" "$1"; }
pass() { printf "[OK]   %s\n" "$1"; ok=$((ok + 1)); }
fail() { printf "[MISS] %s\n" "$1"; warn=$((warn + 1)); }

has_cmd() {
  command -v "$1" >/dev/null 2>&1
}

py_user_bin="$(python3 -c 'import site; print(site.USER_BASE + "/bin")')"

info "Checking core tools"
has_cmd git && pass "git: $(git --version | head -n1)" || fail "git not found"
has_cmd python3 && pass "python3: $(python3 --version 2>&1)" || fail "python3 not found"
has_cmd npm && pass "npm: $(npm --version)" || fail "npm not found"
has_cmd npx && pass "npx available" || fail "npx not found"

echo
info "Checking Python dev tools"
if has_cmd pre-commit; then
  pass "pre-commit in PATH: $(pre-commit --version 2>/dev/null)"
else
  if python3 -m pre_commit --version >/dev/null 2>&1; then
    fail "pre-commit installed but not in PATH"
    echo "      Add to ~/.bashrc: export PATH=\"$py_user_bin:\$PATH\""
  else
    fail "pre-commit not installed"
    echo "      Install: python3 -m pip install --user pre-commit"
  fi
fi

if has_cmd ruff; then
  pass "ruff in PATH: $(ruff --version 2>/dev/null)"
else
  if python3 -m ruff --version >/dev/null 2>&1; then
    fail "ruff installed but not in PATH"
    echo "      Add to ~/.bashrc: export PATH=\"$py_user_bin:\$PATH\""
  else
    fail "ruff not installed"
    echo "      Install: python3 -m pip install --user ruff"
  fi
fi

if python3 -c "import xdist" >/dev/null 2>&1; then
  pass "pytest-xdist importable"
else
  fail "pytest-xdist missing"
  echo "      Install: python3 -m pip install --user pytest-xdist"
fi

echo
info "Checking ops-console tooling"
repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
ui_dir="$repo_root/app/ui/ops-console"

if [[ -d "$ui_dir" ]]; then
  pass "ops-console path exists: $ui_dir"
else
  fail "ops-console path missing: $ui_dir"
fi

if [[ -f "$ui_dir/node_modules/.bin/playwright" ]]; then
  pass "@playwright/test installed in ops-console"
else
  fail "@playwright/test not installed in ops-console"
  echo "      Install: cd app/ui/ops-console && npm install"
fi

if [[ -d "$HOME/Library/Caches/ms-playwright" ]]; then
  pass "Playwright browser cache exists"
else
  fail "Playwright browsers not detected"
  echo "      Install: cd app/ui/ops-console && npx playwright install chromium"
fi

echo
info "Summary"
printf "  OK:   %d\n" "$ok"
printf "  MISS: %d\n" "$warn"

if [[ "$warn" -eq 0 ]]; then
  echo "Environment looks ready."
  exit 0
fi

echo "Environment has missing items. Run the suggested commands above."
exit 1

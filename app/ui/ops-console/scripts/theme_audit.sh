#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MAIN_TSX="$ROOT_DIR/src/main.tsx"
STYLES_CSS="$ROOT_DIR/src/styles.css"
THEMES_CSS="$ROOT_DIR/src/styles/themes.css"

fail=0

echo "[theme-audit] Checking import order..."
if ! rg -n "import './styles.css';" "$MAIN_TSX" >/dev/null; then
  echo "[theme-audit] ERROR: main.tsx missing styles.css import"
  fail=1
fi
if ! rg -n "import './styles/themes.css';" "$MAIN_TSX" >/dev/null; then
  echo "[theme-audit] ERROR: main.tsx missing themes.css import"
  fail=1
fi
styles_line=$(rg -n "import './styles.css';" "$MAIN_TSX" | head -n1 | cut -d: -f1)
themes_line=$(rg -n "import './styles/themes.css';" "$MAIN_TSX" | head -n1 | cut -d: -f1)
if [[ -n "${styles_line:-}" && -n "${themes_line:-}" && "$themes_line" -le "$styles_line" ]]; then
  echo "[theme-audit] ERROR: themes.css must be imported after styles.css"
  fail=1
fi

if rg -n "@import './styles/themes.css'" "$STYLES_CSS" >/dev/null; then
  echo "[theme-audit] ERROR: styles.css should not import themes.css"
  fail=1
fi

echo "[theme-audit] Checking midnight selectors location..."
if rg -n "theme-midnight" "$STYLES_CSS" >/dev/null; then
  echo "[theme-audit] ERROR: theme-midnight selectors found in styles.css (must live in themes.css)"
  rg -n "theme-midnight" "$STYLES_CSS"
  fail=1
fi

echo "[theme-audit] Checking known blue-leak literals in base styles..."
BLUE_PATTERNS='62, 151, 255|109, 176, 228|115, 186, 247|86, 167, 238|108, 170, 224|106, 196, 255|113, 181, 244|118, 208, 255|101, 158, 227|122, 184, 243|114, 174, 239|#59c7ff|#5e8de4'
if rg -n "$BLUE_PATTERNS" "$STYLES_CSS" >/dev/null; then
  echo "[theme-audit] ERROR: found known blue literal leaks in styles.css"
  rg -n "$BLUE_PATTERNS" "$STYLES_CSS"
  fail=1
fi

if [[ "$fail" -ne 0 ]]; then
  echo "[theme-audit] FAILED"
  exit 1
fi

echo "[theme-audit] PASSED"

# UI Style Token Guide

Purpose: keep UI edits fast, consistent, and low-risk by changing shared tokens instead of one-off component styles.

Primary token source:
- `app/ui/ops-console/src/styles.css` (`:root` section at top of file)

Token groups:

1. Typography
- `--font-ui`, `--font-display`, `--font-mono`

2. Core surfaces and text
- `--bg-*`, `--surface-*`, `--text-*`

3. Lines and separators
- `--line-*`, `--hairline-*`, `--depth-sep-*`

4. Status and accents
- `--status-good`, `--status-warn`, `--status-bad`, `--status-unknown`
- `--accent-*`

5. Controls and tabs
- `--control-*`, `--tab-*`

6. Burst/tuning visuals
- `--burst-beam-*`

7. Glass/dock/alerts
- `--glass-*`, `--dock-*`, `--alert-*`

Rules:
- Do not introduce hardcoded color values in component blocks unless there is no existing token fit.
- Prefer mapping new UI elements to existing token families first.
- If a new visual concept is required, add one token in `:root` and reference it from component styles.
- Keep behavior and safety UI states (`ok/warn/fail`) bound to `--status-*` tokens.

Quick edit workflow:
1. Locate desired visual family (text/surface/status/control).
2. Update token(s) in `:root`.
3. Run `npm --prefix app/ui/ops-console run build`.
4. Validate clean app views (`Workflow`, `Split`, `Codex`, `Tuning`).


# UpRight.os Session Handoff

## Current Snapshot
- Repo root: `UpRight.os`
- Primary app: `app/ui/ops-console` (React + TS + Vite)
- Bridge/backend: `app/bridge/server.py`
- Firmware target in active testing: Nano balance v2 profile

## What Is Working
- Ops console UI with left/right HUD rails, center workflow module, bottom telemetry visuals.
- Firmware Workbench drawer includes:
  - Sketch editor (Monaco)
  - Board scan + FQBN/port selection
  - Compile/Upload/Guarded Flash flow
  - Serial send/tail
  - Codex tab
- Guarded flash path exists and uses preflight modal checks.
- Connect wizard + compatibility probe + local robot profile save/load/export/import.
- Codex user auth flow (local account):
  - Register/Login/Logout
  - Per-user OpenAI key save/delete
  - Per-user model + chat history
- In-app feedback improvements:
  - Codex auth/status chips
  - Inline auth alerts
  - Global system alerts panel in center module
- OpenAI TLS reliability improved in bridge:
  - Uses CA bundle (`certifi`) when available
  - Better TLS failure surfacing (`openai_tls_cert_verify_failed`)

## Known Issues / Risks
- System alerts currently live in center module; desired location is global fixed rail (bottom/top-right) across all tabs.
- Codex currently chat-only; it does not execute app actions/tools yet.
- Local auth is app-specific (not OAuth/OpenAI login).
- Runtime auth files are local-only (`app/bridge/.auth_secret`, `app/bridge/upright_auth.db`).

## Core Product Principles (Locked)
- No inline styles; CSS tokenized and theme-ready.
- No monkey patches / one-off hacks.
- Strong modularity (components should be extractable and independently tunable).
- Workflow clarity over cleverness; predictable controls and explicit state.
- Safety-first: staged actions, confirmation gates, e-stop integrity.
- Excellent operator feedback: clear pass/fail/error/success at point-of-action.
- Single-user first; architecture should still be clean for future expansion.

## Near-Term Priorities (Next Chat)
1. Move system alerts to fixed global location (outside tuning module) with severity filters.
2. Build full preflight pipeline page/checklist (connect → static checks → dynamic checks).
3. Add Codex safe action-execution framework:
   - allowlist actions
   - dry-run preview
   - confirmation gate for risky operations
   - action audit log
4. Refactor HUD/telemetry into modular components for independent iteration.
5. Keep tuning flow stable while closing UI layout polish gaps.

## Suggested Immediate Task
- Implement global fixed alert rail:
  - pinned errors until dismissed
  - transient success/info with fade + history
  - consistent placement across tabs and workbench views

## Runbook
- Bridge:
  - `python3 app/bridge/server.py --http-port 8787 --telemetry-port 8788`
- UI:
  - `tools/start_ops_console.sh` (recommended; starts/validates bridge then runs UI in foreground)
  - or `tools/restart_ops_console.sh` (kills stale UI listeners and relaunches in foreground)
  - direct fallback: `cd app/ui/ops-console && npm run dev -- --host 0.0.0.0 --port 5173 --strictPort`
- Build check:
  - `cd app/ui/ops-console && npm run build`

## Dev Process Reliability Standard
- Keep bridge and UI in separate dedicated terminal tabs.
- Do not rely on detached/background UI launches for day-to-day development in this environment.
- UI process is expected to run in foreground; if the terminal closes, UI stops.

## Notes
- `.gitignore` now excludes local editor/runtime state:
  - `.vscode/`
  - `app/bridge/.auth_secret`
  - `app/bridge/upright_auth.db`

## Required Session Handoff Template
Copy and fill this block at every agent handoff:

```
## Handoff Snapshot
- Branch: <branch>
- Head SHA: <sha>
- Working Tree: <clean|dirty> (+ short summary)

## Scope Completed
- Files changed:
  - <path>
  - <path>
- Behavior changes:
  - <what changed>
  - <what changed>

## Verification
- Commands run:
  - <command>
  - <command>
- Results:
  - <exact pass/fail summary>

## Risks / Open Issues
- <risk or blocker>
- <risk or blocker>

## Next Task
- <single highest-priority next action>
```

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Commit: 9cc4c62
- Files Changed:
  - app/ui/ops-console/src/styles.css
  - docs/SESSION_HANDOFF.md
- Tests Run:
  - cd app/ui/ops-console && npm run -s build: passed
  - cd app/ui/ops-console && npm test -- --run: 3 files passed, 38 tests passed
- Open Risks / Blockers:
  - Theme-heavy CSS pass is complete, but no manual visual QA pass was run on every viewport/tab state yet.
- Next Recommended Task:
  - Run a manual visual sweep across Setup/Tune/IDE/Codex/Playground at desktop and mobile breakpoints, then tune any contrast/spacing misses.

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 1a6c518
- Working Tree: dirty (broad in-progress UI/bridge/theme/flow work across tracked and untracked files)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/styles.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Removed remaining outer Setup tab/workspace frame border (`ops-main` + panel shell) while preserving internal content dividers.
  - Increased Setup-step spacing/padding globally (flow strip, stage nav, section nav, setup cards, wizard section spacing) for better readability.

## Verification
- Commands run:
  - cd app/ui/ops-console && npm run build
- Results:
  - build passed (vite production build successful)

## Risks / Open Issues
- Working tree contains many unrelated in-flight changes; do not assume commit-ready state without scoping.
- Visual QA still needed on Setup step spacing at multiple widths (1366x768 and larger) to confirm no regressions in compact states.

## Next Task
- Continue Setup workflow polish by tightening spacing scale responsively, then run manual visual QA and prepare a scoped commit for UI-only changes.

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 1a6c518
- Working Tree: dirty (broad in-progress tracked/untracked work across bridge + UI; this pass scoped to Setup UI CSS + handoff only)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/styles.css
  - app/ui/ops-console/src/styles/themes.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Added Setup-only responsive spacing tokens and viewport-height scaling (denser at short desktop heights, roomier at large desktop heights) for flow strip, stage/section nav, Setup card padding/margins, phase-column spacing, and key content row spacing.
  - Removed Midnight-theme reintroduction of outer `.ops-main` frame styling so Setup keeps the borderless outer workspace surface.

## Verification
- Commands run:
  - `cd app/ui/ops-console && npm run dev -- --host 127.0.0.1 --port 4173 --strictPort`
  - `export CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"; export PWCLI="$CODEX_HOME/skills/playwright/scripts/playwright_cli.sh"; "$PWCLI" open http://127.0.0.1:4173/`
  - `"$PWCLI" resize 1366 768 && "$PWCLI" screenshot --full-page --filename output/playwright/setup-before-1366x768.png`
  - `"$PWCLI" resize 1920 1080 && "$PWCLI" screenshot --full-page --filename output/playwright/setup-before-1920x1080.png`
  - `"$PWCLI" goto http://127.0.0.1:4173/?tab=setup`
  - `"$PWCLI" resize 1366 768 && "$PWCLI" screenshot --full-page --filename output/playwright/setup-after-1366x768.png`
  - `"$PWCLI" resize 1920 1080 && "$PWCLI" screenshot --full-page --filename output/playwright/setup-after-1920x1080.png`
  - `"$PWCLI" eval "() => { const el = document.querySelector('.ops-main'); if (!el) return null; const cs = getComputedStyle(el); return { borderTop: cs.borderTopWidth + ' ' + cs.borderTopStyle, boxShadow: cs.boxShadow, backgroundImage: cs.backgroundImage, backgroundColor: cs.backgroundColor, borderRadius: cs.borderRadius }; }"`
  - `cd app/ui/ops-console && npm run build`
- Results:
  - Setup baseline + post-change screenshots captured at both target desktop sizes under `output/playwright/`.
  - `.ops-main` computed style check returned `borderTop: 0px none`, `boxShadow: none`, `backgroundImage: none`, `backgroundColor: rgba(0, 0, 0, 0)`, `borderRadius: 0px`.
  - Build passed (`tsc -b && vite build`; Vite build completed successfully).

## Risks / Open Issues
- Runtime console still logs repeated bridge/network errors in local dev (`Failed to fetch` paths); unchanged by this UI-only pass.
- Working tree remains broadly dirty, so commit must be path-scoped to avoid pulling unrelated in-flight changes.

## Next Task
- Prepare and create a scoped UI-only commit containing only `app/ui/ops-console/src/styles.css` and `app/ui/ops-console/src/styles/themes.css` (plus handoff doc if desired), then run a quick Setup sanity sweep on Parts/Sketch/Deploy stages.

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 894b601
- Working Tree: dirty (broad in-progress repo state; this pass changed only Setup-focused UI CSS + handoff)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/styles.css
  - app/ui/ops-console/src/styles/themes.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Shifted UI toward monochrome tactical look: near-black base tokens, flatter surface fills, reduced glow/gradient noise, and lower border/shadow contrast for less segment separation.
  - Tuned Setup workflow spacing defaults slightly denser while preserving responsive short-height and large-height scaling behavior.
  - Neutralized Setup deployment visual emphasis from blue pulse/glow to subdued grayscale surface treatment; preserved structure/flow and interaction behavior.
  - Confirmed no outer frame regression around `.ops-main` (still borderless/transparent/no box shadow).

## Verification
- Commands run:
  - `export CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"; export PWCLI="$CODEX_HOME/skills/playwright/scripts/playwright_cli.sh"; "$PWCLI" open http://127.0.0.1:4173/?tab=setup`
  - `"$PWCLI" resize 1366 768 && "$PWCLI" screenshot --full-page --filename output/playwright/setup-mono-before-1366x768.png`
  - `"$PWCLI" resize 1920 1080 && "$PWCLI" screenshot --full-page --filename output/playwright/setup-mono-before-1920x1080.png`
  - `"$PWCLI" goto http://127.0.0.1:4173/?tab=setup`
  - `"$PWCLI" resize 1366 768 && "$PWCLI" screenshot --full-page --filename output/playwright/setup-mono-after-1366x768.png`
  - `"$PWCLI" resize 1920 1080 && "$PWCLI" screenshot --full-page --filename output/playwright/setup-mono-after-1920x1080.png`
  - `"$PWCLI" eval "() => { const el = document.querySelector('.ops-main'); if (!el) return null; const cs = getComputedStyle(el); return { borderTop: cs.borderTopWidth + ' ' + cs.borderTopStyle, boxShadow: cs.boxShadow, backgroundImage: cs.backgroundImage, backgroundColor: cs.backgroundColor, borderRadius: cs.borderRadius }; }"`
  - `cd app/ui/ops-console && npm run build`
- Results:
  - Viewport QA captured at both required sizes; after images show a more unified near-black canvas with reduced panel segmentation:
    - `output/playwright/setup-mono-after-1366x768.png`
    - `output/playwright/setup-mono-after-1920x1080.png`
  - `.ops-main` computed style check returned: `borderTop: 0px none`, `boxShadow: none`, `backgroundImage: none`, `backgroundColor: rgba(0, 0, 0, 0)`, `borderRadius: 0px`.
  - Build passed (`tsc -b && vite build` completed successfully).

## Risks / Open Issues
- This pass also adjusts shared Midnight visual tokens, so non-Setup tabs may need a quick visual sweep for contrast/separation balance.
- Existing runtime console/auth warnings (401s and related local environment noise) remain unchanged and are out of scope.

## Next Task
- Run a quick manual monochrome consistency sweep across IDE/Tune/Playground and then prepare a scoped UI-only commit for `styles.css` + `styles/themes.css` (plus handoff doc if desired).

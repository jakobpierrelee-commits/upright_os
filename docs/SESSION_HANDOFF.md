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

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 32dcc71
- Working Tree: dirty (broad in-progress tracked/untracked repo state; this pass changed only divider CSS in `styles.css` plus handoff doc)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/styles.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Added reusable vertical-separator clip tokens and applied them to shared vertical separator rendering so separators can be clipped from the top/bottom without changing thickness/brightness logic.
  - Updated `.ops-layout::after` to clip from below the main tab baseline/intersection band so no divider segment renders above the Setup/IDE/Tune/Playground selector baseline.

## Verification
- Commands run:
  - `cd app/ui/ops-console && npm run build`
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:4173/?tab=ide' /Users/jvke/Documents/UpRight.os/output/playwright/codex-divider-1366x768.png`
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:4173/?tab=setup' /Users/jvke/Documents/UpRight.os/output/playwright/codex-divider-setup-1366x768.png`
- Results:
  - Build passed (`tsc -b && vite build`; Vite production build completed successfully).
  - 1366x768 screenshots captured successfully at:
    - `output/playwright/codex-divider-1366x768.png`
    - `output/playwright/codex-divider-setup-1366x768.png`

## Risks / Open Issues
- Working tree is broadly dirty from unrelated in-flight work; any commit must be path-scoped.
- Screenshot capture uses local preview URL state; if routing defaults change, retake screenshots on the intended tab URL.

## Next Task
- Run a quick visual pass across 1366x768 for all primary tabs (Setup/IDE/Tune/Playground) and then create a path-scoped UI-only commit for `styles.css` + handoff doc.

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 32dcc71
- Working Tree: dirty (broad in-progress repo state; this pass scoped to black-theme CSS in `styles.css` + handoff)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/styles.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Per user constraint, applied black-theme-only neutralization of navigation/control surfaces in base styles: removed newly introduced blue-tinted backgrounds/borders in tab controls, status bar, codex rail shell, and base form/button controls.
  - Introduced neutral control tokens (`--control-*`) and switched focus/active rings to grayscale values while preserving existing layout and interaction hierarchy.

## Verification
- Commands run:
  - `cd app/ui/ops-console && npm run build`
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:4173/?tab=setup' /Users/jvke/Documents/UpRight.os/output/playwright/black-theme-pass-setup-1366x768.png`
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:4173/?tab=ide' /Users/jvke/Documents/UpRight.os/output/playwright/black-theme-pass-ide-1366x768.png`
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:4173/?tab=tune' /Users/jvke/Documents/UpRight.os/output/playwright/black-theme-pass-tune-1366x768.png`
- Results:
  - Build passed (`tsc -b && vite build`; Vite production build completed successfully).
  - 1366x768 screenshots captured successfully:
    - `output/playwright/black-theme-pass-setup-1366x768.png`
    - `output/playwright/black-theme-pass-ide-1366x768.png`
    - `output/playwright/black-theme-pass-tune-1366x768.png`

## Risks / Open Issues
- `styles.css` still contains legacy blue accents in untouched feature-specific components; this pass neutralizes primary black-theme shell/control surfaces only.
- Working tree remains broadly dirty; any commit should be strictly path-scoped.

## Next Task
- Continue black-theme-only sweep for remaining blue-tinted component backgrounds/borders in `styles.css` (feature sections only) while preserving non-background semantic status colors.

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 32dcc71
- Working Tree: dirty (broad in-progress repo state; this pass scoped to additional black-theme neutralization in `styles.css` + handoff)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/styles.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Confirmed calibration/tuning state colors are preserved (`good/warn/bad` mappings remain green/yellow/red in telemetry + status tokens).
  - Continued black-theme-only sweep for remaining blue-tinted component backgrounds/borders (setup side panels, firmware tabs/editor/docs surfaces, serial diag card, codex send button + scrollbars) using neutral grayscale values.

## Verification
- Commands run:
  - `cd app/ui/ops-console && npm run build`
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:4173/?tab=setup' /Users/jvke/Documents/UpRight.os/output/playwright/black-theme-pass2-setup-1366x768.png`
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:4173/?tab=ide' /Users/jvke/Documents/UpRight.os/output/playwright/black-theme-pass2-ide-1366x768.png`
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:4173/?tab=tune' /Users/jvke/Documents/UpRight.os/output/playwright/black-theme-pass2-tune-1366x768.png`
- Results:
  - Build passed (`tsc -b && vite build`; Vite production build completed successfully).
  - 1366x768 screenshots captured successfully:
    - `output/playwright/black-theme-pass2-setup-1366x768.png`
    - `output/playwright/black-theme-pass2-ide-1366x768.png`
    - `output/playwright/black-theme-pass2-tune-1366x768.png`

## Risks / Open Issues
- Some blue-toned values remain for semantic/non-surface usages (e.g., data-viz strokes and a few accent-driven utility elements), intentionally untouched this pass.
- Working tree remains broadly dirty; any commit must remain path-scoped.

## Next Task
- Continue a final blacklist sweep in `styles.css` for any residual blue-tinted backgrounds/borders in feature subsections while preserving semantic status and data-viz colors.

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 32dcc71
- Working Tree: dirty (broad in-progress repo state; this pass scoped to Codex chat neutralization in `styles.css` + handoff)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/styles.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Neutralized remaining blue Codex chat box/text styling: user message bubble, thread list surfaces, active thread item surface, thinking-stream text, message body text, and message metadata now use grayscale/neutral token-based values.
  - Preserved calibration/tuning state colors (`--accent-ok`, `--accent-warn`, `--accent-bad` and telemetry good/warn/bad mappings) unchanged.

## Verification
- Commands run:
  - `cd app/ui/ops-console && npm run build`
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:4173/?tab=ide' /Users/jvke/Documents/UpRight.os/output/playwright/black-theme-codex-text-pass-ide-1366x768.png`
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:4173/?tab=tune' /Users/jvke/Documents/UpRight.os/output/playwright/black-theme-codex-text-pass-tune-1366x768.png`
- Results:
  - Build passed (`tsc -b && vite build`; Vite production build completed successfully).
  - 1366x768 screenshots captured successfully:
    - `output/playwright/black-theme-codex-text-pass-ide-1366x768.png`
    - `output/playwright/black-theme-codex-text-pass-tune-1366x768.png`

## Risks / Open Issues
- Some non-Codex blue-toned values still exist in unrelated feature-specific sections (intentional for now unless requested).
- Working tree remains broadly dirty; any commit must remain path-scoped.

## Next Task
- Run a final, section-by-section blacklist sweep in `styles.css` for residual blue *background/border* values outside Codex, while preserving state and data-viz semantics.

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 32dcc71
- Working Tree: dirty (broad in-progress repo state; this pass scoped to Codex readability updates in `styles.css` + handoff)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/styles.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Improved Codex chat readability with larger body text, shorter line-length target, stronger message separation, and clearer metadata hierarchy.
  - Kept black-theme-only styling and avoided blue background/border reintroduction in the touched Codex chat pane styles.

## Verification
- Commands run:
  - `cd app/ui/ops-console && npm run build`
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:4173/?tab=ide' /Users/jvke/Documents/UpRight.os/output/playwright/codex-readability-pass-ide-1366x768.png`
- Results:
  - Build passed (`tsc -b && vite build`; Vite production build completed successfully).
  - 1366x768 screenshot captured successfully:
    - `output/playwright/codex-readability-pass-ide-1366x768.png`

## Risks / Open Issues
- Additional readability tuning may still be desired for tool-call cards and network banner typography/surface contrast.
- Working tree remains broadly dirty; any commit must remain path-scoped.

## Next Task
- Do a second Codex readability micro-pass focused on tool-call cards + banner + thread item density (still black-theme-only, no blue background/border additions).

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 32dcc71
- Working Tree: dirty (broad in-progress repo state; this pass scoped to stronger Codex readability changes in `styles.css` + handoff)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/styles.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Applied stronger, visibly obvious readability improvements in Codex chat pane: larger message text, larger input text, more breathing room, clearer neutral panel contrast, and improved metadata legibility.
  - Preserved black-theme-only constraints and did not introduce blue backgrounds or borders in touched Codex chat surfaces.

## Verification
- Commands run:
  - `cd app/ui/ops-console && npm run build`
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:4173/?tab=ide' /Users/jvke/Documents/UpRight.os/output/playwright/codex-readability-pass2-ide-1366x768.png`
- Results:
  - Build passed (`tsc -b && vite build`; Vite production build completed successfully).
  - 1366x768 screenshot captured successfully:
    - `output/playwright/codex-readability-pass2-ide-1366x768.png`

## Risks / Open Issues
- Tool-call cards and network banner may still benefit from a final readability tune pass for consistency with the updated chat message typography.
- Working tree remains broadly dirty; any commit must remain path-scoped.

## Next Task
- Do a final Codex readability polish pass on tool-call cards/banner spacing + type scale, then capture a fresh screenshot of an active chat with mixed user/assistant/tool entries.

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 32dcc71
- Working Tree: dirty (broad in-progress repo state; this pass scoped to Codex Rail+Bubble message-box aesthetic in `styles.css` + handoff)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/styles.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Implemented Rail + Bubble Hybrid aesthetic in Codex messages: assistant messages now use a subtle left rail + neutral card surface; user messages are more compact right-side bubbles.
  - Rolled back the larger type push to a milder size while keeping improved spacing and preserving black-theme/no-blue-surface constraints.

## Verification
- Commands run:
  - `cd app/ui/ops-console && npm run build`
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:4173/?tab=ide' /Users/jvke/Documents/UpRight.os/output/playwright/codex-rail-bubble-pass-ide-1366x768.png`
- Results:
  - Build passed (`tsc -b && vite build`; Vite production build completed successfully).
  - 1366x768 screenshot captured successfully:
    - `output/playwright/codex-rail-bubble-pass-ide-1366x768.png`

## Risks / Open Issues
- Tool-call cards and network banner still use their prior style and may feel visually adjacent-but-different from the new message boxes.
- Working tree remains broadly dirty; any commit must remain path-scoped.

## Next Task
- If approved, apply the same Rail+Bubble visual language to tool-call cards and banner strips for full Codex pane consistency.

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 32dcc71
- Working Tree: dirty (broad in-progress repo state; this pass scoped to active-theme-layer Codex fix in `styles/themes.css` + handoff)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/styles/themes.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Root cause identified: Codex message styles in `styles.css` were being overridden by active `.app-shell.theme-blueprint.surface-floating` rules with `!important` in `styles/themes.css`.
  - Added Rail+Bubble Codex message-box overrides directly in that active black-theme layer so visual changes are now effective in the running UI.

## Verification
- Commands run:
  - `cd app/ui/ops-console && npm run build`
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:4173/?tab=ide' /Users/jvke/Documents/UpRight.os/output/playwright/codex-effective-theme-layer-pass-ide-1366x768.png`
- Results:
  - Build passed (`tsc -b && vite build`; Vite production build completed successfully).
  - 1366x768 screenshot captured successfully:
    - `output/playwright/codex-effective-theme-layer-pass-ide-1366x768.png`

## Risks / Open Issues
- There are still many legacy visual overrides in `styles/themes.css`; future Codex changes should target the active `.theme-blueprint.surface-floating` layer first.
- Working tree remains broadly dirty; any commit must remain path-scoped.

## Next Task
- If you want, I can now unify tool-call cards + banner to the same effective Rail+Bubble styling layer so the full Codex pane is visually coherent.

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 32dcc71
- Working Tree: dirty (broad in-progress repo state; this pass scoped to active theme-layer grayscale cleanup in `styles/themes.css` + handoff)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/styles/themes.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Neutralized remaining blue-leaning **background/border** values in the active `theme-blueprint` / `surface-floating` override path by shifting key theme tokens and high-impact surface rules to grayscale.
  - Preserved semantic status colors (good/warn/bad) and data-viz mappings (raw/kf/output/ref) while cleaning non-semantic UI surfaces.
  - Removed the residual blue-leaning text-strip feel behind Codex message text by ensuring active-layer Codex rules own the message surface treatment.

## Verification
- Commands run:
  - `cd app/ui/ops-console && npm run build`
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:4173/?tab=setup' /Users/jvke/Documents/UpRight.os/output/playwright/theme-layer-cleanup-setup-1366x768.png`
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:4173/?tab=ide' /Users/jvke/Documents/UpRight.os/output/playwright/theme-layer-cleanup-ide-1366x768.png`
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:4173/?tab=tune' /Users/jvke/Documents/UpRight.os/output/playwright/theme-layer-cleanup-tune-1366x768.png`
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:4173/?tab=playground' /Users/jvke/Documents/UpRight.os/output/playwright/theme-layer-cleanup-playground-1366x768.png`
- Results:
  - Build passed (`tsc -b && vite build`; Vite production build completed successfully).
  - 1366x768 screenshots captured successfully:
    - `output/playwright/theme-layer-cleanup-setup-1366x768.png`
    - `output/playwright/theme-layer-cleanup-ide-1366x768.png`
    - `output/playwright/theme-layer-cleanup-tune-1366x768.png`
    - `output/playwright/theme-layer-cleanup-playground-1366x768.png`

## Risks / Open Issues
- A few visualization-specific fills/strokes still intentionally contain blue hues (e.g., graph traces and certain KP motion fills), preserved by design per semantic/data-viz rule.
- Working tree remains broadly dirty; any commit must remain path-scoped.

## Next Task
- If desired, run one last targeted pass on **non-semantic** decorative accents in Playground (not status/data-viz) for complete grayscale consistency.

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 32dcc71
- Working Tree: dirty (broad in-progress repo state; this pass scoped to IDE/Codex residual blue sweep in `styles.css` + handoff)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/styles.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Neutralized remaining IDE/Codex blue-leaning utility surfaces in base styles (`logbox`, tool-call cards, upload progress/overlay, firmware docs close controls, Codex profile cards, overwatch summary/check cards).
  - Preserved semantic status/data-viz colors while removing non-semantic blue backgrounds/borders in the touched areas.

## Verification
- Commands run:
  - `cd app/ui/ops-console && npm run build`
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:4173/?tab=ide' /Users/jvke/Documents/UpRight.os/output/playwright/ide-blue-sweep-followup-1366x768.png`
- Results:
  - Build passed (`tsc -b && vite build`; Vite production build completed successfully).
  - 1366x768 screenshot captured successfully:
    - `output/playwright/ide-blue-sweep-followup-1366x768.png`

## Risks / Open Issues
- Some visual traces in Playground and graph/data-viz elements intentionally remain non-grayscale for semantic meaning and were not altered in this IDE-focused pass.
- Working tree remains broadly dirty; any commit must remain path-scoped.

## Next Task
- If IDE still appears blue in specific widgets, provide a screenshot of that section and I’ll target those exact selectors in the active override layer.

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 32dcc71
- Working Tree: dirty (broad in-progress repo state; this pass scoped to final whole-app monochrome lock in `styles/themes.css`)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/styles/themes.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Added a final authoritative **Monochrome Lock** for `.app-shell.theme-blueprint.surface-floating` to neutralize residual cool/blue tints across major non-semantic surfaces (IDE shells, HUD cards, form inputs, top bars, tabs, codex utility shells).
  - Updated active theme tokens and high-priority selectors with `!important` in the effective layer so grayscale treatment wins consistently.
  - Preserved semantic status and data-viz colors (good/warn/bad + trace semantics) by design.

## Verification
- Commands run:
  - `cd app/ui/ops-console && npm run build`
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:4173/?tab=ide' /Users/jvke/Documents/UpRight.os/output/playwright/whole-app-monochrome-lock-ide-1366x768.png`
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:4173/?tab=setup' /Users/jvke/Documents/UpRight.os/output/playwright/whole-app-monochrome-lock-setup-1366x768.png`
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:4173/?tab=tune' /Users/jvke/Documents/UpRight.os/output/playwright/whole-app-monochrome-lock-tune-1366x768.png`
- Results:
  - Build passed (`tsc -b && vite build`; Vite production build completed successfully).
  - 1366x768 screenshots captured successfully:
    - `output/playwright/whole-app-monochrome-lock-ide-1366x768.png`
    - `output/playwright/whole-app-monochrome-lock-setup-1366x768.png`
    - `output/playwright/whole-app-monochrome-lock-tune-1366x768.png`

## Risks / Open Issues
- Some semantic graph/trace fills intentionally retain blue hues due data-viz meaning and were intentionally untouched.
- Working tree remains broadly dirty; any commit must remain path-scoped.

## Next Task
- If you want absolute zero blue (including data-viz traces), run a final opt-in semantic-color removal pass.

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 32dcc71
- Working Tree: dirty (broad in-progress repo state; this pass scoped to small-radius inheritance in active floating theme)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/styles/themes.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Added shared small radius tokens in active floating theme (`--radius-sm: 6px`, `--radius-md: 8px`, `--radius-lg: 10px`).
  - Applied radius inheritance to box-like controls and surfaces: buttons, step tabs, firmware tab buttons, input fields, textareas/selects, card-like panels, rig cards, tool-call cards, and utility boxes.

## Verification
- Commands run:
  - `cd app/ui/ops-console && npm run build`
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:4173/?tab=ide' /Users/jvke/Documents/UpRight.os/output/playwright/small-radius-inheritance-ide-1366x768.png`
- Results:
  - Build passed (`tsc -b && vite build`; Vite production build completed successfully).
  - 1366x768 screenshot captured successfully:
    - `output/playwright/small-radius-inheritance-ide-1366x768.png`

## Risks / Open Issues
- Rounded treatment now applies broadly to box-like controls; if you want certain components to remain square (e.g. top tabs or HUD tiles), we can carve out exceptions by selector.
- Working tree remains broadly dirty; any commit must remain path-scoped.

## Next Task
- Optionally define a stricter radius hierarchy (`2px/4px/6px`) if you want an even tighter industrial look.

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 32dcc71
- Working Tree: dirty (broad in-progress repo state; this pass scoped to reverting the radius inheritance change in `styles/themes.css`)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/styles/themes.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Reverted the previously added small-radius inheritance pass per user request.
  - Removed floating-theme radius token overrides and broad border-radius forcing selectors for buttons/fields/boxes.

## Verification
- Commands run:
  - `cd app/ui/ops-console && npm run build`
- Results:
  - Build passed (`tsc -b && vite build`; Vite production build completed successfully).

## Risks / Open Issues
- UI corner radii now return to prior behavior controlled by existing non-reverted selectors/tokens.
- Working tree remains broadly dirty; any commit must remain path-scoped.

## Next Task
- If you want a subtler version later, apply radius only to a narrow subset (e.g., inputs only) instead of global inheritance.

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 32dcc71
- Working Tree: dirty (broad in-progress repo state; this pass scoped to targeted radius selectors in `styles/themes.css`)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/styles/themes.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Applied **targeted** corner radius only to:
    - box-like button controls (global buttons, step tabs, ops/tabs/workflow tabs, firmware tab buttons, codex send/rag pill buttons),
    - Codex modal status blocks (`.codex-status-row` badges/pills/indicator-value/rag-pill),
    - Codex chat message blocks (`.codex-msg.user` and `.codex-msg.assistant`).
  - Did **not** reintroduce global radius inheritance for all fields/boxes.

## Verification
- Commands run:
  - `cd app/ui/ops-console && npm run build`
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:4173/?tab=ide' /Users/jvke/Documents/UpRight.os/output/playwright/targeted-radius-buttons-status-messages-ide-1366x768.png`
- Results:
  - Build passed (`tsc -b && vite build`; Vite production build completed successfully).
  - 1366x768 screenshot captured successfully:
    - `output/playwright/targeted-radius-buttons-status-messages-ide-1366x768.png`

## Risks / Open Issues
- Other non-target components remain square by design after this scoped pass.
- Working tree remains broadly dirty; any commit must remain path-scoped.

## Next Task
- If you want, we can tweak only chat message radius (e.g., 4px vs 6px) without touching button/status chips.

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 32dcc71
- Working Tree: dirty (broad in-progress repo state; this pass scoped to IDE live HUD divider-line styling in `styles/themes.css`)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/styles/themes.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - In IDE Live Input HUD area, removed boxed cell borders for `input-hud-card` / `transport-quality-item` and switched to a shared tokenized divider-grid treatment.
  - Divider lines now use tokenized widths/colors (`--hairline-divider-w`, `--line-1`) with top+left grid rails and right+bottom per-cell separators.

## Verification
- Commands run:
  - `cd app/ui/ops-console && npm run build`
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:4173/?tab=ide' /Users/jvke/Documents/UpRight.os/output/playwright/ide-hud-divider-grid-pass-1366x768.png`
- Results:
  - Build passed (`tsc -b && vite build`; Vite production build completed successfully).
  - 1366x768 screenshot captured successfully:
    - `output/playwright/ide-hud-divider-grid-pass-1366x768.png`

## Risks / Open Issues
- This is intentionally scoped to IDE live HUD selectors only (`.ide-theme-zone`) so Tune HUD remains unchanged.
- Working tree remains broadly dirty; any commit must remain path-scoped.

## Next Task
- If desired, apply the same divider-grid language to Tune HUD for visual parity.

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 32dcc71
- Working Tree: dirty (broad in-progress repo state; this pass scoped to IDE HUD internal-only divider refactor in `styles/themes.css`)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/styles/themes.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Refactored IDE Live Input HUD divider treatment to show **internal lines only** (no outer wrap rails).
  - Implementation uses tokenized divider width/color through grid-gap linework (`--hairline-divider-w`, `--line-1`) and removes per-cell box borders.

## Verification
- Commands run:
  - `cd app/ui/ops-console && npm run build`
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:4173/?tab=ide' /Users/jvke/Documents/UpRight.os/output/playwright/ide-hud-internal-divider-only-1366x768.png`
- Results:
  - Build passed (`tsc -b && vite build`; Vite production build completed successfully).
  - 1366x768 screenshot captured successfully:
    - `output/playwright/ide-hud-internal-divider-only-1366x768.png`

## Risks / Open Issues
- Scoped to IDE live HUD selectors only; Tune HUD remains on its previous divider treatment.
- Working tree remains broadly dirty; any commit must remain path-scoped.

## Next Task
- If requested, mirror the same internal-only divider treatment into Tune HUD selectors.

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 32dcc71
- Working Tree: dirty (broad in-progress repo state; this pass scoped to IDE HUD divider clarity refinement in `styles/themes.css`)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/styles/themes.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Refined IDE HUD divider implementation to keep **internal-only lines** while restoring per-cell panel fill for readability.
  - Increased divider visibility by using `--line-0` mix for the grid line color and `--ui-input-bg` fill for cells.
  - Maintained no outer-wrap borders and no per-cell explicit border lines.

## Verification
- Commands run:
  - `cd app/ui/ops-console && npm run build`
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:4173/?tab=ide' /Users/jvke/Documents/UpRight.os/output/playwright/ide-hud-divider-clarity-pass-1366x768.png`
- Results:
  - Build passed (`tsc -b && vite build`; Vite production build completed successfully).
  - 1366x768 screenshot captured successfully:
    - `output/playwright/ide-hud-divider-clarity-pass-1366x768.png`

## Risks / Open Issues
- Treatment remains scoped to IDE live HUD selectors only.
- Working tree remains broadly dirty; any commit must remain path-scoped.

## Next Task
- If needed, tune divider contrast up/down (`--line-0` mix percent) based on your preferred visual strength.

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 32dcc71
- Working Tree: dirty (broad in-progress repo state; this pass scoped to IDE HUD divider color+glow token refinement)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/styles/themes.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Kept IDE HUD internal-only divider behavior and updated divider color to match the vertical separator language.
  - Added subtle tokenized glow on HUD divider grid using structural depth-separator glow tokens (`--depth-sep-glow-near-structural`, `--depth-sep-glow-far-structural`) and core separator strength token (`--depth-sep-core-strength-structural`).

## Verification
- Commands run:
  - `cd app/ui/ops-console && npm run build`
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:4173/?tab=ide' /Users/jvke/Documents/UpRight.os/output/playwright/ide-hud-divider-color-glow-pass-1366x768.png`
- Results:
  - Build passed (`tsc -b && vite build`; Vite production build completed successfully).
  - 1366x768 screenshot captured successfully:
    - `output/playwright/ide-hud-divider-color-glow-pass-1366x768.png`

## Risks / Open Issues
- Glow is intentionally subtle; if stronger emission is desired, increase structural glow token strengths.
- Working tree remains broadly dirty; any commit must remain path-scoped.

## Next Task
- Optionally tune only divider glow intensity (no color change) for final polish.

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 32dcc71
- Working Tree: dirty (broad in-progress repo state; this pass scoped to additive internal-line HUD refactor in `styles/themes.css`)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/styles/themes.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Replaced the subtractive HUD divider approach (grid background fill) with **positive additive line overlays**.
  - IDE HUD cards/items now render on transparent background, while divider lines are drawn by `::after` overlays per cell with structural separator tokens.
  - Removed outer-wrap effect by stripping right-edge lines on even-column cells and bottom-edge lines on last-row cells.

## Verification
- Commands run:
  - `cd app/ui/ops-console && npm run build`
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:4173/?tab=ide' /Users/jvke/Documents/UpRight.os/output/playwright/ide-hud-additive-lines-no-wrap-1366x768.png`
- Results:
  - Build passed (`tsc -b && vite build`; Vite production build completed successfully).
  - 1366x768 screenshot captured successfully:
    - `output/playwright/ide-hud-additive-lines-no-wrap-1366x768.png`

## Risks / Open Issues
- Current no-wrap edge logic assumes 2-column layout in the IDE HUD section (`nth-child(2n)` / `nth-last-child(-n+2)`).
- Working tree remains broadly dirty; any commit must remain path-scoped.

## Next Task
- If needed, make no-wrap logic responsive for 1/2/3-column breakpoints with media-query-aware nth-child rules.

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 32dcc71
- Working Tree: dirty (broad in-progress repo state; this pass scoped to IDE HUD logic + divider rendering updates)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/App.tsx
  - app/ui/ops-console/src/styles/themes.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Removed the `Kalman Innovation` tile from IDE Live Input HUD rendering (`hudMetrics.cards.filter((card) => card.id !== 'innovation')`).
  - Replaced subtractive HUD line rendering with additive internal divider lines (no container fill/background trick, no outer wrap rails).
  - Divider line color/glow now uses structural depth-separator token language (core strength + near glow).

## Verification
- Commands run:
  - `cd app/ui/ops-console && npm run build`
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:4173/?tab=ide' /Users/jvke/Documents/UpRight.os/output/playwright/ide-hud-no-kalman-divider-glow-lines-1366x768.png`
- Results:
  - Build passed (`tsc -b && vite build`; Vite production build completed successfully).
  - 1366x768 screenshot captured successfully:
    - `output/playwright/ide-hud-no-kalman-divider-glow-lines-1366x768.png`

## Risks / Open Issues
- Current no-wrap logic for divider edges assumes 2-column HUD card layout (`nth-child(2n)`, `nth-last-child(-n + 2)`).
- Working tree remains broadly dirty; any commit must remain path-scoped.

## Next Task
- If needed, make divider edge trimming responsive to card column count per breakpoint.

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 32dcc71
- Working Tree: dirty (broad; this pass scoped to App.tsx, styles.css, styles/themes.css)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/App.tsx
  - app/ui/ops-console/src/styles.css
  - app/ui/ops-console/src/styles/themes.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Removed Kalman Innovation tile from **both** IDE HUD render paths (main panel at line 2270, compact sidebar at line 2391) via `filter((card) => card.id !== 'innovation')`.
  - Replaced `::after` pseudo-element monkey patch and inline `style={{ top }}` props with proper named CSS classes in `styles.css`: `.input-hud-grid-wrap`, `.hud-grid-sep-v`, `.hud-grid-sep-h`, `.hud-grid-sep-h--r1` through `--r4`.
  - HUD divider lines now use real `.depth-sep-v` / `.depth-sep-h` DOM elements (the same tokenized utility as the Codex vertical separator) — additive, not subtractive.
  - HUD cards: transparent background, no border, no box-shadow — pure negative space.
  - themes.css override block cleaned: no `::after` hack, no positional overrides (those live in base styles.css now).

## Verification
- Commands run:
  - `npm run build` — passed (`tsc -b && vite build`, ✓ built in 7.68s)
  - `npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:5173/?tab=ide'` — captured `output/playwright/ide-hud-depth-sep-clean-v2-1366x768.png`
- Results:
  - Kalman Innovation tile absent from HUD.
  - Vertical depth-sep divider line visible between HUD columns.
  - No box glow on HUD cards — negative space confirmed.

## Risks / Open Issues
- Horizontal sep `top` positions (20%/40%/60%/80%) assume equal-height rows with 9 cards in 2 columns (5 rows). If card count changes, row boundary percentages must be updated.
- Working tree broadly dirty; any commit must be path-scoped to UI files only.
- Two agents active — do not touch bridge, backend, or files outside `app/ui/ops-console/src/` and `docs/SESSION_HANDOFF.md`.

## Next Task
- Confirm divider line visibility and glow strength with user review of the screenshot.
- If horizontal seps need tuning, adjust `--r1` through `--r4` top values in `styles.css`.

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 32dcc71
- Working Tree: dirty (broad; this pass scoped to rig surface/rail changes in styles)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/styles.css
  - app/ui/ops-console/src/styles/themes.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Disabled `burst-rig::before` left rail in base styles (and disabled tone variants) so Burst Capture Rig has no rail by default.
  - Removed `burst-rig::before` from Blueprint rail override selector groups so special rails remain explicit opt-ins.
  - Introduced shared rig surface tokens (`--rig-surface-border`, `--rig-surface-bg`, `--rig-surface-radius`).
  - Applied shared surface styling via `.rig-surface, .setup-rig, .action-rig, .tune-param-rig, .burst-rig` so rigs share a consistent border/background/radius.
  - Kept `setup-rig::before` as the explicit rail opt-in.

## Verification
- Commands run:
  - `cd app/ui/ops-console && npm run build` — passed (✓ built in 5.64s)
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:5173/?tab=tune' /Users/jvke/Documents/UpRight.os/output/playwright/tune-rigs-no-burst-rail-1366x768.png`
- Results:
  - Burst Capture Rig renders without a left rail.
  - Shared rig surface styling is consistent across rig containers.

## Risks / Open Issues
- `setup-rig` still defines additional layout/transition styling beyond shared surface tokens; this is intentional (rail remains opt-in).

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 32dcc71
- Working Tree: dirty (broad; this pass scoped to badge/pill outline styling)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/styles.css
  - app/ui/ops-console/src/styles/themes.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Converted success/connected badges and other status pills from filled backgrounds to **outline-only** styling:
    - Transparent background
    - Colored text (`--status-good|warn|bad|unknown`)
    - Colored border (color-mix with `--line-0`)
  - Updated base selectors:
    - `.badge.connected`, `.badge.disconnected`, `.badge.unknown`
    - `.hud-pill.good|warn|bad|unknown`
    - `.status-pass|warn|fail` (now includes border)
  - Updated Blueprint theme overrides for the same selectors to match outline treatment.

## Verification
- Commands run:
  - `cd app/ui/ops-console && npm run build` — passed (✓ built in 4.72s)
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:5173/?tab=ide' /Users/jvke/Documents/UpRight.os/output/playwright/ide-outline-badges-1366x768.png`
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:5173/?tab=tune' /Users/jvke/Documents/UpRight.os/output/playwright/tune-outline-badges-1366x768.png`

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 32dcc71
- Working Tree: dirty (broad; this pass scoped to single-red consolidation in ops-console styles)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/styles.css
  - app/ui/ops-console/src/styles/themes.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Consolidated red usage in ops-console UI to a single canonical red token: `--status-bad` (backed by `--accent-bad: #ea4c4c`).
  - Replaced remaining hardcoded red/pink literals with `--status-bad` + `color-mix(...)` tints for:
    - telemetry bad markers, indicator bad values
    - danger/safety/estop surfaces + pulse
    - tool-call error surfaces + flash accents
    - auth/global alert error styling
    - setup rig pulse “bad” state

## Verification
- Commands run:
  - `cd app/ui/ops-console && npm run build` — passed (✓ built in 6.20s)
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=1366,768 'http://127.0.0.1:5173/?tab=ide' /Users/jvke/Documents/UpRight.os/output/playwright/ide-single-red-1366x768.png`
- Artifact:
  - `output/playwright/ide-single-red-1366x768.png`

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 32dcc71
- Working Tree: dirty (broad; this pass scoped to tab/menu selection underline indicator)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/styles.css
  - app/ui/ops-console/src/styles/themes.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Reused the faded+glow underline selection indicator (previously on primary `.tab-btn`) for secondary menu tabs:
    - Added underline pseudo-element for `.tabs > button::after` (same token family: `--menu-underline-*`).
    - Active/selected buttons reveal the underline via `clip-path` + opacity.
  - Updated Firmware Workbench tabs active styling to be underline-only (no filled active background/border), matching the primary tab treatment.

## Verification
- Commands run:
  - `cd app/ui/ops-console && npm run build` — passed (✓ built in 6.30s)
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=900,560 'http://127.0.0.1:5173/?tab=ide' /Users/jvke/Documents/UpRight.os/output/playwright/ide-workbench-subtabs-underline-900x560.png`
- Artifact:
  - `output/playwright/ide-workbench-subtabs-underline-900x560.png`

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 32dcc71
- Working Tree: dirty (broad; this pass scoped to submenu underline glow/taper visibility)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/styles.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Increased submenu selection underline visibility by locally overriding `--menu-underline-*` strengths inside `.tabs`:
    - stronger glass strength
    - higher near/far glow
    - slightly higher blur/saturation

## Verification
- Commands run:
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=900,560 'http://127.0.0.1:5173/?tab=ide' /Users/jvke/Documents/UpRight.os/output/playwright/ide-workbench-subtabs-underline-glow-v2-900x560.png`
- Artifact:
  - `output/playwright/ide-workbench-subtabs-underline-glow-v2-900x560.png`

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 32dcc71
- Working Tree: dirty (broad; this pass scoped to submenu underline sharp taper)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/styles.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Made submenu underline ends fade out more sharply by:
    - tightening the glass gradient stops via `--menu-underline-edge` / `--menu-underline-inner`
    - adding a `mask-image`/`-webkit-mask-image` to enforce a crisp end taper

## Verification
- Commands run:
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=900,560 'http://127.0.0.1:5173/?tab=ide' /Users/jvke/Documents/UpRight.os/output/playwright/ide-workbench-subtabs-underline-sharp-taper-900x560.png`
- Artifact:
  - `output/playwright/ide-workbench-subtabs-underline-sharp-taper-900x560.png`

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 32dcc71
- Working Tree: dirty (broad; this pass scoped to Serial Dock action controls)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/features/workbench/WorkbenchPanel.tsx
  - app/ui/ops-console/src/styles.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Moved `Open in Window` so it only appears inside the floating Serial Dock header actions (not in the main Serial pane button row).
  - Added an up-right arrow icon to the `Open Serial Dock` toggle.
  - Introduced semantic `.dock-menu-action` styling so these controls render as text-forward menu actions with the same underline beam language (instead of boxed secondary buttons).

## Verification
- Commands run:
  - `cd app/ui/ops-console && npm run build` — passed (✓ built in 5.18s)
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=900,560 'http://127.0.0.1:5173/?tab=ide' /Users/jvke/Documents/UpRight.os/output/playwright/ide-serial-open-dock-arrow-menuaction-900x560.png`
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=900,560 'http://127.0.0.1:5173/?tab=ide&workbench=serial' /Users/jvke/Documents/UpRight.os/output/playwright/ide-serial-dock-menuactions-900x560.png`
- Artifacts:
  - `output/playwright/ide-serial-open-dock-arrow-menuaction-900x560.png`
  - `output/playwright/ide-serial-dock-menuactions-900x560.png`

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 32dcc71
- Working Tree: dirty (broad; this pass scoped to Serial Dock resize)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/features/workbench/WorkbenchPanel.tsx
  - app/ui/ops-console/src/styles.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Floating Serial Dock is now user-resizable via a bottom-right resize handle.
  - Size is stored in CSS vars (`--serial-dock-w`, `--serial-dock-h`) and clamped to pixel limits:
    - min: 560×420
    - max: 980×860
  - Resizing also re-clamps the dock position so it stays within the viewport.

## Verification
- Commands run:
  - `cd app/ui/ops-console && npm run build` — passed (✓ built in 9.62s)
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=900,560 'http://127.0.0.1:5173/?tab=ide&workbench=serial' /Users/jvke/Documents/UpRight.os/output/playwright/ide-serial-dock-resize-handle-900x560.png`
- Artifact:
  - `output/playwright/ide-serial-dock-resize-handle-900x560.png`

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 32dcc71
- Working Tree: dirty (broad; this pass scoped to Serial Dock header icon actions)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/features/workbench/WorkbenchPanel.tsx
  - app/ui/ops-console/src/styles.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Serial Dock header actions are now icon-only:
    - `Open in Window` uses the up-right arrow icon.
    - `Close Dock` uses an X icon.
  - Added `.dock-icon-action` / `.dock-action-icon` styles for consistent hit area and visual weight; preserved accessibility via `aria-label`.

## Verification
- Commands run:
  - `cd app/ui/ops-console && npm run build` — passed (✓ built in 5.96s)
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=900,560 'http://127.0.0.1:5173/?tab=ide&workbench=serial' /Users/jvke/Documents/UpRight.os/output/playwright/ide-serial-dock-icon-actions-900x560.png`
- Artifact:
  - `output/playwright/ide-serial-dock-icon-actions-900x560.png`

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 32dcc71
- Working Tree: dirty (broad; this pass scoped to Workbench header subtitle placement)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/features/workbench/WorkbenchPanel.tsx
  - app/ui/ops-console/src/App.tsx
  - app/ui/ops-console/src/styles.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Moved the Workbench subtitle (`arduino-cli pipeline`) to the left, stacked under `Firmware Workbench`.
  - Reduced the subtitle font via `workflow-label-sm`.
  - Removed the right-aligned `strings.ide.subtitle` from the compact Live Input HUD header so the pipeline label is not duplicated on the right.

## Verification
- Commands run:
  - `cd app/ui/ops-console && npm run build` — passed (✓ built in 5.50s)
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=900,560 'http://127.0.0.1:5173/?tab=ide' /Users/jvke/Documents/UpRight.os/output/playwright/ide-workbench-pipeline-left-v2-900x560.png`
- Artifact:
  - `output/playwright/ide-workbench-pipeline-left-v2-900x560.png`

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 32dcc71
- Working Tree: dirty (broad; this pass scoped to aligning Workbench sub-tab underline to Setup flow style)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/styles.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Reverted Workbench `.tabs` underline tuning (boosted glow + sharp end taper) so the Workbench sub-tabs match the Setup flow step underline style.
    - Removed local `.tabs` overrides of `--menu-underline-*` strengths.
    - Removed the extra `mask-image` taper enforcement.
    - Restored baseline gradient stops (18% / 84%).

## Verification
- Commands run:
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=900,560 'http://127.0.0.1:5173/?tab=ide' /Users/jvke/Documents/UpRight.os/output/playwright/ide-workbench-tabs-setup-style-900x560.png`
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=900,560 'http://127.0.0.1:5173/?tab=setup' /Users/jvke/Documents/UpRight.os/output/playwright/setup-flow-steps-style-900x560.png`
- Artifacts:
  - `output/playwright/ide-workbench-tabs-setup-style-900x560.png`
  - `output/playwright/setup-flow-steps-style-900x560.png`

## Handoff Snapshot
- Branch: recover/uiux-restore-2026-02-19
- Head SHA: 32dcc71
- Working Tree: dirty (broad; this pass scoped to square underline endcaps)

## Scope Completed
- Files changed:
  - app/ui/ops-console/src/styles.css
  - docs/SESSION_HANDOFF.md
- Behavior changes:
  - Made Setup flow underline endcaps square by removing clipping on `.setup-flow-step` (`overflow: visible`), preventing the tokenized button radius from rounding the underline ends.
  - Also applied `overflow: visible` to `.tabs > button` for consistency and to ensure IDE Workbench tabs match the same square-ended style.
  - Maintains token-first approach; no inline styles; theme-consistent across Setup and IDE.

## Verification
- Commands run:
  - `cd app/ui/ops-console && npm run build` — passed (✓ built in 4.49s)
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=900,560 'http://127.0.0.1:5173/?tab=setup' /Users/jvke/Documents/UpRight.os/output/playwright/setup-flow-steps-square-ends-900x560.png`
  - `cd app/ui/ops-console && npx playwright screenshot --viewport-size=900,560 'http://127.0.0.1:5173/?tab=ide' /Users/jvke/Documents/UpRight.os/output/playwright/ide-workbench-tabs-square-ends-900x560.png`
- Artifacts:
  - `output/playwright/setup-flow-steps-square-ends-900x560.png`
  - `output/playwright/ide-workbench-tabs-square-ends-900x560.png`

## Open Risks/Blockers
- None identified. The change is minimal and isolated to visual underline clipping behavior; no functional regressions expected.

## Next Recommended Task
- No immediate follow-up required. The square-ended underline styling is now consistent across Setup and IDE Workbench tabs. If further visual refinements are desired, they should be scoped to token adjustments rather than one-off overrides.

## Deferred Refactor Backlog (Agreed)
- Date: 2026-02-21
- Priority: planned after current functional workflow testing pass
- Items:
  - Split `Codex chat/orchestration` service from `bridge hardware/serial` service so Codex remains available when bridge/serial is down.
  - CSS architecture cleanup for `app/ui/ops-console/src/styles.css` and theme layering in `app/ui/ops-console/src/styles/themes.css`:
    - reduce duplication and override conflicts
    - consolidate token usage and remove legacy style branches
    - improve maintainability and change safety
  - Enforce backend guardrails for agent responses (beyond profile text):
    - capability-aware responses (never suggest unavailable UI actions)
    - tool-evidence gate for success claims
    - operator-first concise response contract in debug flows
  - Strengthen bridge runtime resilience paths:
    - supervisor/process lifecycle hardening
    - clearer stale PID/log detection and recovery behavior

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
  - `cd app/ui/ops-console && npm run dev -- --host 127.0.0.1 --port 5173`
- Build check:
  - `cd app/ui/ops-console && npm run build`

## Notes
- `.gitignore` now excludes local editor/runtime state:
  - `.vscode/`
  - `app/bridge/.auth_secret`
  - `app/bridge/upright_auth.db`

# Core UI Principles (UpRight.os)

## Purpose
Define non-negotiable UI engineering rules so the console can evolve quickly without regressions, style drift, or ad-hoc patches.

## Principles
1. Token-First Styling
- All color, spacing, typography, radius, and elevation values must come from CSS variables (design tokens).
- No hard-coded visual constants inside component files.

2. No Inline Styles
- `style={...}` is prohibited for production UI components.
- Styling belongs in versioned CSS or theme stylesheets only.

3. Theme-Ready by Default
- Every new component must use semantic tokens (`--text-0`, `--surface-0`, `--accent-*`) rather than literal colors.
- New themes must be achievable by swapping token sets, not rewriting components.
- Theme overrides must load after base styles (`styles.css` first, `themes.css` second) so cascade is deterministic.
- Visual literals in base component styles are treated as defects unless they are mapped to tokens immediately.

4. Semantic Classes, Not One-Off Hacks
- Use stable class names tied to component meaning (`panel`, `statusbar`, `checkpoint-card`).
- Avoid one-use selectors and monkey patches.

5. Motion with Intent
- Animations should communicate state transitions or safety significance.
- Keep transitions short and deterministic; avoid decorative jitter.

6. Safety-Critical Legibility
- Status states (`connected`, `estop`, `balancing`, `fault`) must remain readable under all themes.
- Contrast and hierarchy are mandatory in control/safety regions.

7. Mobile + Desktop Parity
- The console must remain fully operable on narrow screens.
- No hidden critical controls at mobile breakpoints.

8. Component Contract Stability
- UI controls must map 1:1 to bridge API contracts.
- If the backend contract changes, update typed API models first, then UI usage.

9. Checkpoint and Tuning Integrity
- Tuning fields remain user-editable and must never be overwritten mid-edit by polling loops.
- Sync actions (`Sync From Bot`) should be explicit.

10. Documentation Before Expansion
- Any significant UI pattern addition must include a short rule update in this document or linked oracle docs.

## Implementation Rules
- Preferred location for global visual system: `/Users/jvke/Documents/UpRight.os/app/ui/ops-console/src/styles.css`
- Preferred location for theme overrides and theme-specific selectors: `/Users/jvke/Documents/UpRight.os/app/ui/ops-console/src/styles/themes.css`
- Component logic: `/Users/jvke/Documents/UpRight.os/app/ui/ops-console/src/App.tsx`
- API contract layer: `/Users/jvke/Documents/UpRight.os/app/ui/ops-console/src/api.ts`
- No runtime DOM style injection for normal feature work.
- Theme import policy: `main.tsx` must import `styles.css` before `styles/themes.css`.
- Run `app/ui/ops-console/scripts/theme_audit.sh` before merge for any theme-related change.
- UI runtime policy: run UI in a dedicated foreground terminal (`tools/start_ops_console.sh` or `tools/restart_ops_console.sh`).
- Bridge and UI must run in separate dedicated terminals for reliable local development.

## Definition of Done (UI)
A UI change is complete only if:
1. No inline style was introduced.
2. New visuals use existing or newly-defined tokens.
3. Build passes.
4. Mobile layout remains usable.
5. Safety actions remain clear and unambiguous.
6. Theme audit passes (`scripts/theme_audit.sh`) with zero blue-literal leak violations.

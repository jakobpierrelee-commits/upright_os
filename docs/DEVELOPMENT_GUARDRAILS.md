# Development Guardrails and Instruction Template

## One-time bootstrap

```bash
tools/bootstrap_dev_guardrails.sh
```

## Daily commands

### 1) Fast Python test loop

```bash
tools/pytest_fast.sh app/bridge/tests/test_thread_api_integration.py -q
```

### 2) Fast UI changed-file test loop

```bash
cd app/ui/ops-console && npm run test:changed
```

### 3) Full UI build + visual regression for Setup

```bash
cd app/ui/ops-console && npm run build
cd app/ui/ops-console && npm run e2e:visual
```

### 4) Pre-commit checks before pushing

```bash
pre-commit run --all-files
```

### 5) Scoped commit (prevents scope bleed)

```bash
tools/scoped_commit.sh -m "ui(setup): spacing polish" \
  app/ui/ops-console/src/styles.css \
  app/ui/ops-console/src/styles/themes.css \
  docs/SESSION_HANDOFF.md
```

## Going-forward instruction structure (use this exact shape)

Copy/paste this template for each request to any coding agent:

```md
Goal
- <single concrete objective>

Scope
- In: <allowed paths>
- Out: <explicitly excluded paths>

Branch/commit rules
- Branch: <exact branch>
- Do not switch branches.
- Do not revert unrelated in-flight work.
- Commit policy: <no commit | scoped commit allowed>

Behavior constraints
- <e.g., UI-only, no API changes>
- <e.g., no inline styles, tokenized CSS only>
- <e.g., preserve behavior unless explicitly requested>

Verification (required)
- Run:
  - <exact command>
  - <exact command>
- Report exact pass/fail output.

Deliverables
- Summary of changes
- Exact files changed
- Risks / open issues
- Next recommended task
```

## Optional manual tools

- Aider:
  - `pipx install aider-chat` (or `pip install aider-chat`)
  - Use as implementation agent, then run `pre-commit` + visual checks.
- OpenHands:
  - Best for larger, long-running autonomous tasks in sandboxed envs.
- VS Code extensions:
  - Keep minimal; install only trusted, actively maintained publishers.

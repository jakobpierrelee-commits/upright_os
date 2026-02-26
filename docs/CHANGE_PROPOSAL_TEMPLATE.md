# Change Proposal Template (One Page)

Purpose: force high-scrutiny decisions before adding, changing, or deleting flow-critical behavior.

Use this before implementing any non-trivial architecture/process change.

## 1) Requirement Owner

- Request owner (person, not department): `...`
- Mission objective this supports: `...`
- Why this matters now (time-sensitive): `...`

## 2) Delete-First Challenge

- What existing part/process could be removed instead of adding new scope: `...`
- Why delete is not sufficient (if not chosen): `...`
- If deleting now, what is the rollback path: `...`

## 3) Simplest Viable Shape

- Proposed minimum change (smallest useful slice): `...`
- What we are explicitly NOT adding in this slice: `...`
- Module/file boundaries touched: `...`

## 4) Risk + Safety Gate

- Main failure modes introduced: `...`
- Fail-closed behavior: `...`
- Operator-visible error copy expected: `...`
- Legacy-path impact: `None | Gated | Removed`

## 5) Speed + Verification

- Expected cycle-time gain: `...`
- Static checks to run: `...`
- Runtime/manual checks to run: `...`
- Acceptance criteria (binary pass/fail): `...`

## 6) Automation Plan (After Proven)

- What should be automated after this works manually: `...`
- Why automation is deferred until now: `...`
- CI/contract tests to add: `...`

## 7) Scorecard Mapping

- Scorecard item(s): `#...`
- Stage plan entry: `S...`
- Evidence files/logs to attach: `...`


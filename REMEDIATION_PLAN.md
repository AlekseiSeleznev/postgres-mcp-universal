# postgres-mcp-universal Remediation Plan

Date: 2026-04-12

## P0
1. Keep CI green under the new coverage gate (`line+branch >= 89%`); add missing branch tests discovered by Actions.
2. Expand deterministic env-isolation fixture usage for all config-default tests touching process env.

## P1
1. Refactor dashboard module into smaller route/service/template units.
2. Split large handler functions (`health`, `schema`, `query`) into composable pure helpers.
3. Add explicit contract tests for error payload consistency across tool handlers.

## P2
1. Add load smoke tests for:
   - concurrent query execution,
   - pool connect/disconnect churn,
   - dashboard polling with auth enabled.
2. Add UX checks for form validation feedback and mobile interaction quality.

## Acceptance Criteria
- CI passes with current threshold and no regressions in covered branches.
- No coroutine warnings in test runs.
- Dashboard/API behavior remains backward-compatible after refactor.

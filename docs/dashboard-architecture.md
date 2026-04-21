# Dashboard Architecture

This document defines the current dashboard structure in `postgres-mcp-universal`.

## Goals

- Keep dashboard/API behavior backward-compatible.
- Reduce `web_ui.py` coupling and review risk.
- Lock contracts with dedicated tests.
- Avoid exposing secrets in dashboard payloads and rendered HTML.

## Module Split

- `gateway/gateway/web_ui.py`
  - request/auth checks
  - endpoint handlers (`/api/*`)
  - thin route wrappers delegating connect/edit operations
- `gateway/gateway/web_ui_helpers.py`
  - render glue (`render_dashboard`)
  - response helpers (`json_response`, `error_response`)
  - dashboard-safe URI mapper (`safe_uri` only in `/api/databases`)
  - edit-flow password merge when dashboard sends redacted URI
- `gateway/gateway/web_ui_services.py`
  - connect/edit orchestration logic (service layer)
- `gateway/gateway/web_ui_content.py`
  - translations dictionary (`_T`)
  - static dashboard HTML (`DASHBOARD_HTML`)
  - static docs pages (`DOCS_HTML`)
  - docs renderer (`render_docs`)
  - client-side Bearer prompt flow (no injected API key)

## API Error Contract

Dashboard mutation endpoints return JSON errors in a single shape:

```json
{"error": "<message>"}
```

## Test Guardrails

Architecture and contracts are enforced by:

- `gateway/tests/test_web_ui.py` (lifecycle + error contract)
- `gateway/tests/test_ci_assets.py` (module split + docs presence checks)
- `gateway/tests/test_load_smoke.py` (concurrent query/admin churn + dashboard auth polling)

## Cross-Platform Notes

- Linux runtime smoke: `setup.sh` + `/health` + `/dashboard` + `/mcp`
- Windows native path: `install.ps1` / `uninstall.ps1`
- Windows CI smoke: deterministic static checks for `install.ps1`, `uninstall.ps1`, `setup.sh`, and compose config

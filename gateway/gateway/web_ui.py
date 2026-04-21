"""Dashboard — web UI for PostgreSQL MCP database management."""

from __future__ import annotations

import hmac
import logging

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response

from gateway.config import settings
from gateway.db_registry import DatabaseInfo, registry
from gateway.pg_pool import pool_manager
from gateway.rate_limit import check_rate_limit
from gateway.web_ui_content import DASHBOARD_HTML, _T, render_docs
from gateway.web_ui_helpers import (
    DB_NAME_RE,
    error_response,
    json_response,
    merge_password_from_old_uri,
    render_dashboard,
    safe_uri_for_dashboard,
)
from gateway.web_ui_services import connect_from_request, edit_from_request

log = logging.getLogger(__name__)
_CSP_HEADER = (
    "default-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "font-src 'self' data:; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'; "
    "form-action 'self'"
)


def _check_api_auth(request: Request) -> JSONResponse | None:
    """Verify Bearer token on dashboard API endpoints."""
    if not settings.api_key:
        return None
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else ""
    if not hmac.compare_digest(token.encode(), settings.api_key.encode()):
        return JSONResponse(
            {"error": "unauthorized"},
            status_code=401,
            headers={"WWW-Authenticate": 'Bearer realm="pg-mcp"'},
        )
    return None


def _json(data, status_code: int = 200) -> Response:
    return json_response(data, status_code=status_code)


def _error(message: str, status_code: int = 400) -> Response:
    return error_response(message, status_code=status_code)


def _safe_uri_for_dashboard(db) -> str:
    return safe_uri_for_dashboard(db)


def _merge_password_from_old_uri(new_uri: str, old_uri: str) -> str:
    return merge_password_from_old_uri(new_uri, old_uri)


def _render(lang: str = "ru") -> str:
    return render_dashboard(lang)


async def dashboard_page(request: Request) -> HTMLResponse:
    lang = request.query_params.get("lang", "ru")
    return HTMLResponse(_render(lang), headers={"Content-Security-Policy": _CSP_HEADER})


async def api_status(request: Request) -> JSONResponse:
    limited = check_rate_limit(request, "api", settings)
    if limited:
        return limited
    denied = _check_api_auth(request)
    if denied:
        return denied
    return JSONResponse(pool_manager.get_status())


async def api_databases(request: Request) -> JSONResponse:
    limited = check_rate_limit(request, "api", settings)
    if limited:
        return limited
    denied = _check_api_auth(request)
    if denied:
        return denied
    dbs = registry.list_all()
    return JSONResponse([
        {
            "name": db.name,
            "safe_uri": _safe_uri_for_dashboard(db),
            "access_mode": db.access_mode,
            "connected": db.connected,
        }
        for db in dbs
    ])


async def api_connect(request: Request) -> JSONResponse:
    limited = check_rate_limit(request, "api", settings)
    if limited:
        return limited
    denied = _check_api_auth(request)
    if denied:
        return denied
    result = await connect_from_request(
        request,
        registry=registry,
        pool_manager=pool_manager,
        database_info_cls=DatabaseInfo,
    )
    if isinstance(result, Response):
        return result
    return JSONResponse(result)


async def api_disconnect(request: Request) -> JSONResponse:
    limited = check_rate_limit(request, "api", settings)
    if limited:
        return limited
    denied = _check_api_auth(request)
    if denied:
        return denied
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        return _error("name is required", 400)
    removed = registry.remove(name)
    if not removed:
        return _error(f"'{name}' not found", 404)
    await pool_manager.disconnect(name)
    return JSONResponse({"ok": True})


async def api_edit(request: Request) -> JSONResponse:
    limited = check_rate_limit(request, "api", settings)
    if limited:
        return limited
    denied = _check_api_auth(request)
    if denied:
        return denied
    result = await edit_from_request(
        request,
        registry=registry,
        pool_manager=pool_manager,
        database_info_cls=DatabaseInfo,
    )
    if isinstance(result, Response):
        return result
    return JSONResponse(result)


async def api_switch(request: Request) -> JSONResponse:
    limited = check_rate_limit(request, "api", settings)
    if limited:
        return limited
    denied = _check_api_auth(request)
    if denied:
        return denied
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        return _error("name is required", 400)
    try:
        pool_manager.switch_db(name)
    except ValueError as e:
        return _error(str(e), 400)
    registry.active = name
    registry.save()
    return JSONResponse({"ok": True})

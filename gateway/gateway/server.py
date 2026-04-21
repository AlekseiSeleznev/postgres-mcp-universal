"""Starlette ASGI app with MCP transport and dashboard."""

from __future__ import annotations

import asyncio
import hmac
import logging
import uuid
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.routing import Mount, Route
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from mcp.server.streamable_http import StreamableHTTPServerTransport

from gateway.config import settings
from gateway.db_registry import DatabaseInfo, registry
from gateway.pg_pool import pool_manager
from gateway.mcp_server import server as mcp_server, _current_session_id
from gateway.rate_limit import check_rate_limit

log = logging.getLogger(__name__)

# Persistent transport per session
_transports: dict[str, StreamableHTTPServerTransport] = {}
_session_tasks: dict[str, asyncio.Task] = {}


def _transport_terminated(transport: StreamableHTTPServerTransport) -> bool:
    """Return transport termination state across MCP SDK variants.

    Some SDK builds expose a public ``is_terminated`` property, while others
    only keep the private ``_terminated`` flag. We support both so session
    reuse logic stays compatible across environments.
    """
    if hasattr(transport, "is_terminated"):
        return bool(getattr(transport, "is_terminated"))
    return bool(getattr(transport, "_terminated", False))


async def _session_cleanup_loop():
    """Background task: periodically clean up idle MCP sessions and expired pool sessions."""
    while True:
        try:
            await asyncio.sleep(300)  # run every 5 minutes
            removed = pool_manager.cleanup_sessions()
            if removed:
                log.info("Session cleanup: removed %d expired sessions", removed)
            # Also clean up terminated MCP transports
            terminated = [sid for sid, t in list(_transports.items()) if _transport_terminated(t)]
            for sid in terminated:
                _transports.pop(sid, None)
                task = _session_tasks.pop(sid, None)
                if task and not task.done():
                    task.cancel()
            if terminated:
                log.debug("Cleaned up %d terminated MCP sessions", len(terminated))
        except asyncio.CancelledError:
            break
        except Exception:
            log.exception("Error in session cleanup loop")


@asynccontextmanager
async def lifespan(app: Starlette):
    log.info("Starting postgres-mcp-universal on port %d", settings.port)

    # Restore saved databases
    saved = registry.load()
    for db_cfg in saved:
        try:
            db = registry.get(db_cfg["name"])
            if db:
                await pool_manager.connect(db)
                log.info("Restored connection to '%s'", db.name)
        except Exception:
            log.exception("Failed to restore '%s'", db_cfg["name"])

    # Connect default DB if configured and no saved DBs
    if settings.database_uri and not registry.list_all():
        db = DatabaseInfo(
            name="default",
            uri=settings.database_uri,
            access_mode=settings.access_mode,
            pool_min=settings.pool_min_size,
            pool_max=settings.pool_max_size,
        )
        registry.add(db)
        try:
            await pool_manager.connect(db)
            log.info("Connected to default database")
        except Exception:
            log.exception("Failed to connect to default database")

    # Start background session cleanup task
    cleanup_task = asyncio.create_task(_session_cleanup_loop())

    yield

    # Shutdown: cancel cleanup first
    cleanup_task.cancel()
    try:
        await cleanup_task
    except (asyncio.CancelledError, Exception):
        pass

    for task in _session_tasks.values():
        task.cancel()
    for task in _session_tasks.values():
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    _session_tasks.clear()
    _transports.clear()
    await pool_manager.close_all()
    log.info("Shutdown complete")


async def health_check(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", **pool_manager.get_status()})


async def oauth_protected_resource(request: Request) -> JSONResponse:
    """RFC 9728 Protected Resource Metadata — tells clients where to get tokens."""
    base = str(request.base_url).rstrip("/")
    return JSONResponse({
        "resource": base,
        "authorization_servers": [base],
        "bearer_methods_supported": ["header"],
    })


async def oauth_authorization_server(request: Request) -> JSONResponse:
    """RFC 8414 Authorization Server Metadata.

    The token endpoint is exposed only in explicit compatibility mode.
    """
    base = str(request.base_url).rstrip("/")
    payload = {"issuer": base}
    if settings.enable_simple_token_endpoint and settings.api_key:
        payload.update({
            "token_endpoint": f"{base}/oauth/token",
            "grant_types_supported": ["client_credentials"],
            "token_endpoint_auth_methods_supported": ["client_secret_post"],
        })
    else:
        payload.update({
            "grant_types_supported": [],
            "token_endpoint_auth_methods_supported": [],
        })
    return JSONResponse(payload)


async def oauth_token(request: Request) -> JSONResponse:
    """Compatibility token endpoint.

    Disabled by default. When enabled, requires client_secret == configured API key.
    """
    limited = check_rate_limit(request, "oauth", settings)
    if limited:
        return limited

    if not settings.enable_simple_token_endpoint:
        return JSONResponse({
            "error": "access_denied",
            "error_description": "simple token endpoint is disabled",
        }, status_code=403)

    if not settings.api_key:
        return JSONResponse({"error": "invalid_request"}, status_code=400)

    # OAuth client_credentials form payload is expected.
    payload = {}
    ctype = request.headers.get("content-type", "").lower()
    if "application/x-www-form-urlencoded" in ctype or "multipart/form-data" in ctype:
        form = await request.form()
        payload = dict(form)
    elif "application/json" in ctype:
        payload = await request.json()

    grant_type = payload.get("grant_type", "client_credentials")
    if grant_type != "client_credentials":
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

    client_secret = payload.get("client_secret")
    if not hmac.compare_digest((client_secret or "").encode(), settings.api_key.encode()):
        return JSONResponse(
            {"error": "invalid_client"},
            status_code=401,
            headers={"WWW-Authenticate": 'Bearer realm="pg-mcp"'},
        )

    return JSONResponse({
        "access_token": settings.api_key,
        "token_type": "Bearer",
        "expires_in": 86400,
    })


async def _run_session(transport: StreamableHTTPServerTransport, ready: asyncio.Event):
    """Keep transport connected and MCP server running for the session lifetime.

    Pin the transport's mcp_session_id into the task's context so that tool
    handlers can read it via the _current_session_id ContextVar. Without this,
    the ContextVar set by handle_mcp() in the HTTP request task is not
    visible here (this task was created earlier with an empty context) and
    every tool handler would see session_id=None, breaking per-session
    isolation between two concurrent clients.
    """
    _current_session_id.set(transport.mcp_session_id)
    async with transport.connect() as (read_stream, write_stream):
        ready.set()
        await mcp_server.run(
            read_stream, write_stream, mcp_server.create_initialization_options()
        )


async def handle_mcp(scope, receive, send):
    """ASGI handler for MCP Streamable HTTP transport."""
    request = Request(scope, receive)

    limited = check_rate_limit(request, "mcp", settings)
    if limited:
        await limited(scope, receive, send)
        return

    # Check auth if API key is configured
    if settings.api_key:
        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.lower().startswith("bearer ") else ""
        if not hmac.compare_digest(token.encode(), settings.api_key.encode()):
            response = JSONResponse({"error": "unauthorized"}, status_code=401,
                                    headers={"WWW-Authenticate": 'Bearer realm="pg-mcp"'})
            await response(scope, receive, send)
            return

    session_id = request.headers.get("mcp-session-id")

    # Reuse existing transport for the session
    transport = _transports.get(session_id) if session_id else None

    if transport is None or _transport_terminated(transport):
        # New session — generate ID, start background runner
        new_id = session_id or uuid.uuid4().hex
        transport = StreamableHTTPServerTransport(mcp_session_id=new_id)
        ready = asyncio.Event()
        task = asyncio.create_task(_run_session(transport, ready))
        await ready.wait()
        _transports[new_id] = transport
        _session_tasks[new_id] = task
        session_id = new_id

    # Inject the resolved session ID into the ContextVar so that tool handlers
    # in mcp_server.py can read it via _get_session_id() without touching any
    # private MCP SDK symbols.
    token = _current_session_id.set(session_id)
    try:
        await transport.handle_request(scope, receive, send)
    finally:
        _current_session_id.reset(token)


# Import dashboard lazily to keep startup fast
async def dashboard_docs(request: Request) -> HTMLResponse:
    from gateway.web_ui import _CSP_HEADER, render_docs
    lang = request.query_params.get("lang", "ru")
    return HTMLResponse(render_docs(lang), headers={"Content-Security-Policy": _CSP_HEADER})


def _dashboard_routes():
    from gateway.web_ui import (
        dashboard_page, api_status, api_databases, api_connect, api_disconnect, api_edit, api_switch,
    )
    return [
        Route("/dashboard", dashboard_page),
        Route("/dashboard/docs", dashboard_docs),
        Route("/api/status", api_status),
        Route("/api/databases", api_databases),
        Route("/api/connect", api_connect, methods=["POST"]),
        Route("/api/disconnect", api_disconnect, methods=["POST"]),
        Route("/api/edit", api_edit, methods=["POST"]),
        Route("/api/switch", api_switch, methods=["POST"]),
    ]


_inner = Starlette(
    lifespan=lifespan,
    routes=[
        Route("/health", health_check),
        Route("/.well-known/oauth-protected-resource", oauth_protected_resource),
        Route("/.well-known/oauth-authorization-server", oauth_authorization_server),
        Route("/oauth/token", oauth_token, methods=["POST"]),
        Mount("/mcp", app=handle_mcp),
        *_dashboard_routes(),
    ],
)


async def app(scope, receive, send):
    """ASGI wrapper: route /mcp (no trailing slash) directly to MCP handler."""
    if scope["type"] == "http" and scope["path"] == "/mcp":
        await handle_mcp(scope, receive, send)
    else:
        await _inner(scope, receive, send)

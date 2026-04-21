"""Coverage-focused tests for gateway.server runtime branches and entrypoint."""

from __future__ import annotations

import asyncio
import importlib
import runpy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.applications import Starlette
from starlette.requests import Request


def _scope(path: str, *, headers: list[tuple[bytes, bytes]] | None = None, query_string: bytes = b""):
    return {
        "type": "http",
        "method": "POST" if path == "/mcp" else "GET",
        "path": path,
        "headers": headers or [],
        "query_string": query_string,
        "scheme": "http",
        "server": ("testserver", 8090),
        "client": ("127.0.0.1", 12345),
    }


async def _receive():
    return {"type": "http.request", "body": b"", "more_body": False}


class _AwaitableTask:
    def __init__(self, exc=None):
        self.exc = exc
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    def done(self):
        return False

    def __await__(self):
        async def _runner():
            if self.exc:
                raise self.exc
            raise asyncio.CancelledError()

        return _runner().__await__()


def test_main_entrypoint_runs_uvicorn_with_settings():
    import gateway.config as config_mod

    with patch.object(config_mod.settings, "port", 9123), \
         patch.object(config_mod.settings, "log_level", "DEBUG"), \
         patch("uvicorn.run") as mock_run:
        runpy.run_module("gateway.__main__", run_name="__main__")

    mock_run.assert_called_once_with(
        "gateway.server:app",
        host="0.0.0.0",
        port=9123,
        log_level="debug",
    )


def test_main_module_import_does_not_start_server():
    with patch("uvicorn.run") as mock_run:
        importlib.reload(importlib.import_module("gateway.__main__"))

    mock_run.assert_not_called()


@pytest.mark.asyncio
async def test_session_cleanup_loop_removes_terminated_transports_and_logs():
    import gateway.server as server_mod

    terminated_transport = MagicMock()
    terminated_transport.is_terminated = True
    active_transport = MagicMock()
    active_transport.is_terminated = False
    terminated_task = MagicMock()
    terminated_task.done.return_value = False

    server_mod._transports.clear()
    server_mod._session_tasks.clear()
    server_mod._transports.update({"dead": terminated_transport, "alive": active_transport})
    server_mod._session_tasks["dead"] = terminated_task

    calls = {"count": 0}

    async def fake_sleep(_seconds):
        calls["count"] += 1
        if calls["count"] > 1:
            raise asyncio.CancelledError()

    try:
        with patch("gateway.server.asyncio.sleep", fake_sleep), \
             patch.object(server_mod.pool_manager, "cleanup_sessions", return_value=2), \
             patch.object(server_mod.log, "info") as log_info, \
             patch.object(server_mod.log, "debug") as log_debug:
            await server_mod._session_cleanup_loop()

        assert "dead" not in server_mod._transports
        assert "alive" in server_mod._transports
        terminated_task.cancel.assert_called_once()
        log_info.assert_called_with("Session cleanup: removed %d expired sessions", 2)
        log_debug.assert_called_with("Cleaned up %d terminated MCP sessions", 1)
    finally:
        server_mod._transports.clear()
        server_mod._session_tasks.clear()


@pytest.mark.asyncio
async def test_session_cleanup_loop_handles_idle_iteration_without_removals():
    import gateway.server as server_mod

    calls = {"count": 0}

    async def fake_sleep(_seconds):
        calls["count"] += 1
        if calls["count"] > 1:
            raise asyncio.CancelledError()

    with patch("gateway.server.asyncio.sleep", fake_sleep), \
         patch.object(server_mod.pool_manager, "cleanup_sessions", return_value=0):
        await server_mod._session_cleanup_loop()


@pytest.mark.asyncio
async def test_session_cleanup_loop_skips_cancelling_finished_tasks():
    import gateway.server as server_mod

    terminated_transport = MagicMock()
    terminated_transport.is_terminated = True
    finished_task = MagicMock()
    finished_task.done.return_value = True

    server_mod._transports.clear()
    server_mod._session_tasks.clear()
    server_mod._transports["dead"] = terminated_transport
    server_mod._session_tasks["dead"] = finished_task

    calls = {"count": 0}

    async def fake_sleep(_seconds):
        calls["count"] += 1
        if calls["count"] > 1:
            raise asyncio.CancelledError()

    try:
        with patch("gateway.server.asyncio.sleep", fake_sleep), \
             patch.object(server_mod.pool_manager, "cleanup_sessions", return_value=0):
            await server_mod._session_cleanup_loop()

        finished_task.cancel.assert_not_called()
    finally:
        server_mod._transports.clear()
        server_mod._session_tasks.clear()


def test_transport_terminated_supports_public_and_private_sdk_flags():
    import gateway.server as server_mod

    public_transport = SimpleNamespace(is_terminated=True)
    private_transport = SimpleNamespace(_terminated=True)
    active_transport = SimpleNamespace(_terminated=False)

    assert server_mod._transport_terminated(public_transport) is True
    assert server_mod._transport_terminated(private_transport) is True
    assert server_mod._transport_terminated(active_transport) is False


@pytest.mark.asyncio
async def test_lifespan_restores_saved_databases_and_logs_restore_failures():
    import gateway.server as server_mod

    db_ok = MagicMock(name="okdb")
    db_ok.name = "okdb"
    db_fail = MagicMock(name="faildb")
    db_fail.name = "faildb"

    async def fake_cleanup():
        await asyncio.sleep(3600)

    with patch.object(server_mod, "_session_cleanup_loop", fake_cleanup), \
         patch.object(server_mod.registry, "load", return_value=[{"name": "okdb"}, {"name": "faildb"}, {"name": "missing"}]), \
         patch.object(server_mod.registry, "get", side_effect=[db_ok, db_fail, None]), \
         patch.object(server_mod.registry, "list_all", return_value=[db_ok]), \
         patch.object(server_mod.pool_manager, "connect", AsyncMock(side_effect=[None, RuntimeError("boom")])), \
         patch.object(server_mod.pool_manager, "close_all", AsyncMock()) as close_all, \
         patch.object(server_mod.log, "exception") as log_exception, \
         patch("gateway.server.settings") as mock_settings:
        mock_settings.database_uri = ""
        mock_settings.port = 8090

        app = Starlette(lifespan=server_mod.lifespan)
        async with server_mod.lifespan(app):
            pass

    close_all.assert_awaited_once()
    log_exception.assert_called_with("Failed to restore '%s'", "faildb")


@pytest.mark.asyncio
async def test_lifespan_handles_default_connect_failure_and_shutdown_task_errors():
    import gateway.server as server_mod

    async def fake_cleanup():
        await asyncio.sleep(3600)

    server_mod._session_tasks.clear()
    server_mod._transports.clear()

    with patch.object(server_mod, "_session_cleanup_loop", fake_cleanup), \
         patch.object(server_mod.registry, "load", return_value=[]), \
         patch.object(server_mod.registry, "list_all", return_value=[]), \
         patch.object(server_mod.registry, "add") as reg_add, \
         patch.object(server_mod.pool_manager, "connect", AsyncMock(side_effect=RuntimeError("connect failed"))), \
         patch.object(server_mod.pool_manager, "close_all", AsyncMock()) as close_all, \
         patch.object(server_mod.log, "exception") as log_exception, \
         patch("gateway.server.settings") as mock_settings:
        mock_settings.database_uri = "postgresql://localhost/default"
        mock_settings.port = 8090
        mock_settings.access_mode = "unrestricted"
        mock_settings.pool_min_size = 2
        mock_settings.pool_max_size = 10

        app = Starlette(lifespan=server_mod.lifespan)
        async with server_mod.lifespan(app):
            server_mod._session_tasks["cancelled"] = _AwaitableTask()
            server_mod._session_tasks["boom"] = _AwaitableTask(RuntimeError("boom"))
            server_mod._transports["sess"] = MagicMock()

    reg_add.assert_called_once()
    close_all.assert_awaited_once()
    log_exception.assert_called_with("Failed to connect to default database")
    assert server_mod._session_tasks == {}
    assert server_mod._transports == {}


@pytest.mark.asyncio
async def test_oauth_token_accepts_json_payload_and_rejects_unsupported_grant():
    from starlette.routing import Route
    from starlette.testclient import TestClient
    import gateway.server as server_mod

    app = Starlette(routes=[Route("/oauth/token", server_mod.oauth_token, methods=["POST"])])

    with patch("gateway.server.settings") as mock_settings:
        mock_settings.enable_simple_token_endpoint = True
        mock_settings.api_key = "secret"
        client = TestClient(app)

        bad = client.post("/oauth/token", json={"grant_type": "authorization_code", "client_secret": "secret"})
        ok = client.post("/oauth/token", json={"client_secret": "secret"})

    assert bad.status_code == 400
    assert bad.json()["error"] == "unsupported_grant_type"
    assert ok.status_code == 200
    assert ok.json()["access_token"] == "secret"


@pytest.mark.asyncio
async def test_oauth_token_handles_unknown_content_type_as_empty_payload():
    from starlette.routing import Route
    from starlette.testclient import TestClient
    import gateway.server as server_mod

    app = Starlette(routes=[Route("/oauth/token", server_mod.oauth_token, methods=["POST"])])

    with patch("gateway.server.settings") as mock_settings:
        mock_settings.enable_simple_token_endpoint = True
        mock_settings.api_key = "secret"
        client = TestClient(app)
        resp = client.post("/oauth/token", content=b"raw-body", headers={"content-type": "text/plain"})

    assert resp.status_code == 401
    assert resp.json()["error"] == "invalid_client"


@pytest.mark.asyncio
async def test_run_session_sets_ready_and_runs_mcp_server():
    import gateway.server as server_mod

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=("read-stream", "write-stream"))
    cm.__aexit__ = AsyncMock(return_value=None)
    transport = MagicMock()
    transport.connect.return_value = cm
    ready = asyncio.Event()

    with patch.object(server_mod.mcp_server, "run", AsyncMock()) as run_mock, \
         patch.object(server_mod.mcp_server, "create_initialization_options", return_value={"ok": True}):
        await server_mod._run_session(transport, ready)

    assert ready.is_set()
    run_mock.assert_awaited_once_with("read-stream", "write-stream", {"ok": True})


@pytest.mark.asyncio
async def test_handle_mcp_reuses_existing_transport_with_valid_auth():
    import gateway.server as server_mod

    transport = MagicMock()
    transport.is_terminated = False
    transport.handle_request = AsyncMock()

    server_mod._transports.clear()
    server_mod._session_tasks.clear()
    server_mod._transports["sess-1"] = transport

    try:
        with patch("gateway.server.settings") as mock_settings, \
             patch("gateway.server.asyncio.create_task") as create_task:
            mock_settings.api_key = "secret"
            await server_mod.handle_mcp(
                _scope("/mcp", headers=[(b"authorization", b"Bearer secret"), (b"mcp-session-id", b"sess-1")]),
                _receive,
                AsyncMock(),
            )

        create_task.assert_not_called()
        transport.handle_request.assert_awaited_once()
    finally:
        server_mod._transports.clear()
        server_mod._session_tasks.clear()


@pytest.mark.asyncio
async def test_handle_mcp_replaces_terminated_transport_for_existing_session():
    import gateway.server as server_mod

    old_transport = MagicMock()
    old_transport.is_terminated = True
    new_transport = MagicMock()
    new_transport.is_terminated = False
    new_transport.handle_request = AsyncMock()
    ready = asyncio.Event()
    ready.set()

    server_mod._transports.clear()
    server_mod._session_tasks.clear()
    server_mod._transports["sess-1"] = old_transport

    def fake_create_task(coro, **_kwargs):
        coro.close()
        return MagicMock()

    try:
        with patch("gateway.server.settings") as mock_settings, \
             patch("gateway.server.StreamableHTTPServerTransport", return_value=new_transport), \
             patch("gateway.server.asyncio.Event", return_value=ready), \
             patch("gateway.server.asyncio.create_task", side_effect=fake_create_task):
            mock_settings.api_key = ""
            await server_mod.handle_mcp(
                _scope("/mcp", headers=[(b"mcp-session-id", b"sess-1")]),
                _receive,
                AsyncMock(),
            )

        assert server_mod._transports["sess-1"] is new_transport
        new_transport.handle_request.assert_awaited_once()
    finally:
        server_mod._transports.clear()
        server_mod._session_tasks.clear()


@pytest.mark.asyncio
async def test_handle_mcp_reuses_existing_transport_with_private_terminated_flag():
    import gateway.server as server_mod

    transport = SimpleNamespace(_terminated=False, handle_request=AsyncMock())

    server_mod._transports.clear()
    server_mod._session_tasks.clear()
    server_mod._transports["sess-1"] = transport

    try:
        with patch("gateway.server.settings") as mock_settings, \
             patch("gateway.server.asyncio.create_task") as create_task:
            mock_settings.api_key = ""
            await server_mod.handle_mcp(
                _scope("/mcp", headers=[(b"mcp-session-id", b"sess-1")]),
                _receive,
                AsyncMock(),
            )

        create_task.assert_not_called()
        transport.handle_request.assert_awaited_once()
    finally:
        server_mod._transports.clear()
        server_mod._session_tasks.clear()


@pytest.mark.asyncio
async def test_dashboard_docs_and_app_wrapper_dispatch_correctly():
    import gateway.server as server_mod

    request = Request(_scope("/dashboard/docs", query_string=b"lang=en"))

    with patch("gateway.web_ui.render_docs", return_value="<p>docs</p>"), \
         patch("gateway.web_ui._CSP_HEADER", "default-src 'self'"):
        response = await server_mod.dashboard_docs(request)
    assert response.body == b"<p>docs</p>"
    assert response.headers["Content-Security-Policy"] == "default-src 'self'"

    handle_mcp = AsyncMock()
    inner = AsyncMock()
    with patch.object(server_mod, "handle_mcp", handle_mcp), \
         patch.object(server_mod, "_inner", inner):
        await server_mod.app(_scope("/mcp"), _receive, AsyncMock())
        await server_mod.app(_scope("/health"), _receive, AsyncMock())

    handle_mcp.assert_awaited_once()
    inner.assert_awaited_once()

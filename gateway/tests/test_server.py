"""Tests for gateway.server — health endpoint, OAuth endpoints, auth middleware."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient


def _make_test_app():
    """Build a minimal test Starlette app without lifespan side-effects."""
    from starlette.applications import Starlette
    from starlette.routing import Route
    from gateway.server import (
        health_check,
        oauth_protected_resource,
        oauth_authorization_server,
        oauth_token,
    )

    return Starlette(routes=[
        Route("/health", health_check),
        Route("/.well-known/oauth-protected-resource", oauth_protected_resource),
        Route("/.well-known/oauth-authorization-server", oauth_authorization_server),
        Route("/oauth/token", oauth_token, methods=["POST"]),
    ])


class TestHealthEndpoint:
    """Tests for GET /health."""

    def test_health_returns_ok(self):
        mock_status = {"pools": {}, "sessions": 0, "active_default": ""}
        with patch("gateway.server.pool_manager.get_status", return_value=mock_status):
            app = _make_test_app()
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get("/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_health_includes_pool_status(self):
        mock_status = {"pools": {"mydb": {"size": 5}}, "sessions": 2, "active_default": "mydb"}
        with patch("gateway.server.pool_manager.get_status", return_value=mock_status):
            app = _make_test_app()
            client = TestClient(app)
            resp = client.get("/health")

        data = resp.json()
        assert data["pools"]["mydb"]["size"] == 5
        assert data["sessions"] == 2


class TestOAuthEndpoints:
    """Tests for OAuth discovery endpoints."""

    def test_protected_resource_metadata(self):
        app = _make_test_app()
        client = TestClient(app)
        resp = client.get("/.well-known/oauth-protected-resource")

        assert resp.status_code == 200
        data = resp.json()
        assert "resource" in data
        assert "authorization_servers" in data
        assert "bearer_methods_supported" in data

    def test_authorization_server_metadata(self):
        with patch("gateway.server.settings") as mock_settings:
            mock_settings.enable_simple_token_endpoint = False
            mock_settings.api_key = "secret"
            app = _make_test_app()
            client = TestClient(app)
            resp = client.get("/.well-known/oauth-authorization-server")

        assert resp.status_code == 200
        data = resp.json()
        assert "issuer" in data
        assert "token_endpoint" not in data
        assert data["grant_types_supported"] == []
        assert data["token_endpoint_auth_methods_supported"] == []

    def test_authorization_server_metadata_with_simple_endpoint_enabled(self):
        with patch("gateway.server.settings") as mock_settings:
            mock_settings.enable_simple_token_endpoint = True
            mock_settings.api_key = "secret"
            app = _make_test_app()
            client = TestClient(app)
            resp = client.get("/.well-known/oauth-authorization-server")

        assert resp.status_code == 200
        data = resp.json()
        assert "issuer" in data
        assert "token_endpoint" in data
        assert data["grant_types_supported"] == ["client_credentials"]
        assert data["token_endpoint_auth_methods_supported"] == ["client_secret_post"]

    def test_oauth_token_disabled_returns_403(self):
        with patch("gateway.server.settings") as mock_settings:
            mock_settings.enable_simple_token_endpoint = False
            mock_settings.api_key = "my-secret-key"
            app = _make_test_app()
            client = TestClient(app)
            resp = client.post("/oauth/token")

        assert resp.status_code == 403
        assert resp.json()["error"] == "access_denied"

    def test_oauth_token_no_api_key_returns_400(self):
        with patch("gateway.server.settings") as mock_settings:
            mock_settings.enable_simple_token_endpoint = True
            mock_settings.api_key = ""
            app = _make_test_app()
            client = TestClient(app)
            resp = client.post("/oauth/token")

        assert resp.status_code == 400
        assert resp.json()["error"] == "invalid_request"

    def test_oauth_token_wrong_client_secret_returns_401(self):
        with patch("gateway.server.settings") as mock_settings:
            mock_settings.enable_simple_token_endpoint = True
            mock_settings.api_key = "my-secret-key"
            app = _make_test_app()
            client = TestClient(app)
            resp = client.post(
                "/oauth/token",
                data={"grant_type": "client_credentials", "client_secret": "wrong"},
            )

        assert resp.status_code == 401
        assert resp.json()["error"] == "invalid_client"

    def test_oauth_token_with_api_key_returns_token(self):
        with patch("gateway.server.settings") as mock_settings:
            mock_settings.enable_simple_token_endpoint = True
            mock_settings.api_key = "my-secret-key"
            mock_settings.rate_limit_enabled = True
            mock_settings.rate_limit_window_seconds = 60
            mock_settings.rate_limit_oauth_requests = 10
            app = _make_test_app()
            client = TestClient(app)
            resp = client.post(
                "/oauth/token",
                data={"grant_type": "client_credentials", "client_secret": "my-secret-key"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["access_token"] == "my-secret-key"
        assert data["token_type"] == "Bearer"

    def test_oauth_token_rate_limited_returns_429_and_retry_after(self):
        with patch("gateway.server.settings") as mock_settings:
            mock_settings.enable_simple_token_endpoint = True
            mock_settings.api_key = "my-secret-key"
            mock_settings.rate_limit_enabled = True
            mock_settings.rate_limit_window_seconds = 60
            mock_settings.rate_limit_oauth_requests = 1
            app = _make_test_app()
            client = TestClient(app)

            first = client.post(
                "/oauth/token",
                data={"grant_type": "client_credentials", "client_secret": "my-secret-key"},
            )
            second = client.post(
                "/oauth/token",
                data={"grant_type": "client_credentials", "client_secret": "my-secret-key"},
            )

        assert first.status_code == 200
        assert second.status_code == 429
        assert second.json()["error"] == "rate_limited"
        assert second.headers["Retry-After"].isdigit()


class TestMCPAuthMiddleware:
    """Tests for Bearer token authentication on /mcp endpoint."""

    @pytest.mark.asyncio
    async def test_auth_rejects_missing_token(self):
        """When api_key is set, missing Authorization header returns 401."""
        from starlette.requests import Request
        from starlette.datastructures import Headers

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/mcp",
            "headers": [],
            "query_string": b"",
        }

        responses = []

        async def receive():
            return {"type": "http.request", "body": b""}

        async def send(event):
            responses.append(event)

        with patch("gateway.server.settings") as mock_settings:
            mock_settings.api_key = "secret"
            from gateway.server import handle_mcp
            await handle_mcp(scope, receive, send)

        # First response event should be "http.response.start" with 401
        start = next((r for r in responses if r.get("type") == "http.response.start"), None)
        assert start is not None
        assert start["status"] == 401

    @pytest.mark.asyncio
    async def test_auth_rejects_wrong_token(self):
        """Wrong Bearer token returns 401."""
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/mcp",
            "headers": [(b"authorization", b"Bearer wrong-token")],
            "query_string": b"",
        }

        responses = []

        async def receive():
            return {"type": "http.request", "body": b""}

        async def send(event):
            responses.append(event)

        with patch("gateway.server.settings") as mock_settings:
            mock_settings.api_key = "correct-token"
            from gateway.server import handle_mcp
            await handle_mcp(scope, receive, send)

        start = next((r for r in responses if r.get("type") == "http.response.start"), None)
        assert start is not None
        assert start["status"] == 401

    @pytest.mark.asyncio
    async def test_mcp_rate_limited_before_auth(self):
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/mcp",
            "headers": [(b"mcp-session-id", b"sess-1")],
            "query_string": b"",
            "client": ("127.0.0.1", 4321),
        }

        responses = []

        async def receive():
            return {"type": "http.request", "body": b""}

        async def send(event):
            responses.append(event)

        transport = MagicMock()
        transport.is_terminated = False
        transport.handle_request = AsyncMock()

        import gateway.server as server_mod
        server_mod._transports.clear()
        server_mod._session_tasks.clear()
        server_mod._transports["sess-1"] = transport

        try:
            with patch("gateway.server.settings") as mock_settings:
                mock_settings.api_key = "secret"
                mock_settings.rate_limit_enabled = True
                mock_settings.rate_limit_window_seconds = 60
                mock_settings.rate_limit_mcp_requests = 1

                await server_mod.handle_mcp(scope, receive, send)
                await server_mod.handle_mcp(scope, receive, send)

            starts = [r for r in responses if r.get("type") == "http.response.start"]
            assert starts
            assert starts[0]["status"] == 401
            assert any(event["status"] == 429 for event in starts)
            transport.handle_request.assert_not_awaited()
        finally:
            server_mod._transports.clear()
            server_mod._session_tasks.clear()


class TestLifespan:
    """Tests for lifespan startup/shutdown logic."""

    @pytest.mark.asyncio
    async def test_lifespan_loads_saved_databases(self, tmp_path):
        """Lifespan restores databases from registry state file."""
        import gateway.server as server_mod
        import gateway.db_registry as db_reg_mod
        from gateway.db_registry import DatabaseRegistry

        empty_reg = DatabaseRegistry()
        mock_pool_manager = MagicMock()
        mock_pool_manager.connect = AsyncMock()
        mock_pool_manager.close_all = AsyncMock()
        mock_pool_manager.get_status = MagicMock(return_value={})

        with patch.object(db_reg_mod, "registry", empty_reg), \
             patch.object(server_mod, "pool_manager", mock_pool_manager), \
             patch("gateway.server.settings") as mock_settings:
            mock_settings.database_uri = ""
            mock_settings.port = 8080

            # Run through the lifespan context manager
            from starlette.applications import Starlette
            app = Starlette(lifespan=server_mod.lifespan)
            async with server_mod.lifespan(app):
                pass  # yield point

        # No saved DBs, so connect should not be called
        mock_pool_manager.connect.assert_not_awaited()
        mock_pool_manager.close_all.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_lifespan_connects_default_db_when_uri_set(self, tmp_path):
        """When DATABASE_URI is configured and no saved DBs, lifespan connects default."""
        import gateway.server as server_mod
        import gateway.db_registry as db_reg_mod
        from gateway.db_registry import DatabaseRegistry

        empty_reg = DatabaseRegistry()
        mock_pool_manager = MagicMock()
        mock_pool_manager.connect = AsyncMock()
        mock_pool_manager.close_all = AsyncMock()

        with patch.object(db_reg_mod, "registry", empty_reg), \
             patch.object(server_mod, "pool_manager", mock_pool_manager), \
             patch("gateway.server.settings") as mock_settings, \
             patch("gateway.db_registry.STATE_FILE", str(tmp_path / "s.json")):
            mock_settings.database_uri = "postgresql://localhost/default"
            mock_settings.port = 8080
            mock_settings.access_mode = "unrestricted"
            mock_settings.pool_min_size = 2
            mock_settings.pool_max_size = 10

            from starlette.applications import Starlette
            app = Starlette(lifespan=server_mod.lifespan)
            async with server_mod.lifespan(app):
                pass

        mock_pool_manager.connect.assert_awaited_once()

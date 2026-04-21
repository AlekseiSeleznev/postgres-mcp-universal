"""Security tests — auth enforcement, URI sanitization, input validation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient


# ── Helpers ──────────────────────────────────────────────────────────

def _make_app_with_key(api_key: str = "test-api-key"):
    """Build test app with a specific API key."""
    from starlette.applications import Starlette
    from starlette.routing import Route
    from gateway.server import health_check, oauth_token

    app = Starlette(routes=[
        Route("/health", health_check),
        Route("/oauth/token", oauth_token, methods=["POST"]),
    ])
    return app


# ── API Auth Tests ────────────────────────────────────────────────────

class TestApiAuthOnDashboard:
    """Verify that dashboard API endpoints enforce Bearer auth."""

    def _make_web_app(self, api_key: str = "secret-key"):
        from starlette.applications import Starlette
        from starlette.routing import Route
        from gateway.web_ui import api_databases, api_status, api_connect, api_disconnect, api_switch

        return Starlette(routes=[
            Route("/api/databases", api_databases),
            Route("/api/status", api_status),
            Route("/api/connect", api_connect, methods=["POST"]),
            Route("/api/disconnect", api_disconnect, methods=["POST"]),
            Route("/api/switch", api_switch, methods=["POST"]),
        ])

    def test_api_databases_requires_auth(self):
        app = self._make_web_app()
        with patch("gateway.web_ui.settings") as ms, \
             patch("gateway.web_ui.registry") as mr:
            ms.api_key = "secret-key"
            mr.list_all.return_value = []
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get("/api/databases")
        assert resp.status_code == 401

    def test_api_databases_allows_with_correct_token(self):
        app = self._make_web_app()
        with patch("gateway.web_ui.settings") as ms, \
             patch("gateway.web_ui.registry") as mr:
            ms.api_key = "secret-key"
            mr.list_all.return_value = []
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get("/api/databases", headers={"Authorization": "Bearer secret-key"})
        assert resp.status_code == 200

    def test_api_status_requires_auth(self):
        app = self._make_web_app()
        with patch("gateway.web_ui.settings") as ms, \
             patch("gateway.web_ui.pool_manager") as mpm:
            ms.api_key = "secret-key"
            ms.rate_limit_enabled = True
            ms.rate_limit_window_seconds = 60
            ms.rate_limit_api_requests = 60
            mpm.get_status.return_value = {}
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get("/api/status")
        assert resp.status_code == 401

    def test_api_connect_requires_auth(self):
        app = self._make_web_app()
        with patch("gateway.web_ui.settings") as ms:
            ms.api_key = "secret-key"
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post(
                "/api/connect",
                json={"name": "db1", "uri": "postgresql://localhost/db1"},
            )
        assert resp.status_code == 401

    def test_api_disconnect_requires_auth(self):
        app = self._make_web_app()
        with patch("gateway.web_ui.settings") as ms:
            ms.api_key = "secret-key"
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post("/api/disconnect", json={"name": "db1"})
        assert resp.status_code == 401

    def test_api_switch_requires_auth(self):
        app = self._make_web_app()
        with patch("gateway.web_ui.settings") as ms:
            ms.api_key = "secret-key"
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post("/api/switch", json={"name": "db1"})
        assert resp.status_code == 401

    def test_no_api_key_means_no_auth_required(self):
        """When api_key is empty, all requests should be allowed without auth."""
        app = self._make_web_app()
        with patch("gateway.web_ui.settings") as ms, \
             patch("gateway.web_ui.registry") as mr:
            ms.api_key = ""
            mr.list_all.return_value = []
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get("/api/databases")
        assert resp.status_code == 200

    def test_api_rate_limiter_blocks_repeated_missing_token_requests(self):
        app = self._make_web_app()
        with patch("gateway.web_ui.settings") as ms, \
             patch("gateway.web_ui.registry") as mr:
            ms.api_key = "secret-key"
            ms.rate_limit_enabled = True
            ms.rate_limit_window_seconds = 60
            ms.rate_limit_api_requests = 1
            mr.list_all.return_value = []
            client = TestClient(app, raise_server_exceptions=True)
            first = client.get("/api/databases")
            second = client.get("/api/databases")
        assert first.status_code == 401
        assert second.status_code == 429
        assert second.json()["error"] == "rate_limited"

    def test_api_rate_limiter_blocks_repeated_wrong_token_requests(self):
        app = self._make_web_app()
        with patch("gateway.web_ui.settings") as ms, \
             patch("gateway.web_ui.registry") as mr:
            ms.api_key = "secret-key"
            ms.rate_limit_enabled = True
            ms.rate_limit_window_seconds = 60
            ms.rate_limit_api_requests = 1
            mr.list_all.return_value = []
            client = TestClient(app, raise_server_exceptions=True)
            first = client.get("/api/databases", headers={"Authorization": "Bearer wrong"})
            second = client.get("/api/databases", headers={"Authorization": "Bearer wrong"})
        assert first.status_code == 401
        assert second.status_code == 429

    def test_api_rate_limiter_can_be_disabled(self):
        app = self._make_web_app()
        with patch("gateway.web_ui.settings") as ms, \
             patch("gateway.web_ui.registry") as mr:
            ms.api_key = ""
            ms.rate_limit_enabled = False
            mr.list_all.return_value = []
            client = TestClient(app, raise_server_exceptions=True)
            first = client.get("/api/databases")
            second = client.get("/api/databases")
        assert first.status_code == 200
        assert second.status_code == 200


class TestDatabaseNameValidation:
    """Input validation for database names."""

    def _make_connect_app(self):
        from starlette.applications import Starlette
        from starlette.routing import Route
        from gateway.web_ui import api_connect

        return Starlette(routes=[Route("/api/connect", api_connect, methods=["POST"])])

    def test_invalid_name_rejected(self):
        app = self._make_connect_app()
        with patch("gateway.web_ui.settings") as ms:
            ms.api_key = ""
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post(
                "/api/connect",
                json={"name": "../../etc/passwd", "uri": "postgresql://localhost/db"},
            )
        assert resp.status_code == 400
        assert "Invalid" in resp.json()["error"]

    def test_name_with_semicolon_rejected(self):
        app = self._make_connect_app()
        with patch("gateway.web_ui.settings") as ms:
            ms.api_key = ""
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post(
                "/api/connect",
                json={"name": "db;DROP", "uri": "postgresql://localhost/db"},
            )
        assert resp.status_code == 400

    def test_valid_name_with_hyphens_allowed(self):
        app = self._make_connect_app()
        mock_pm = MagicMock()
        mock_pm.connect = AsyncMock()
        mock_reg = MagicMock()
        mock_reg.add = MagicMock()
        mock_reg.remove = MagicMock()
        mock_db = MagicMock()
        mock_db.name = "my-db"
        mock_reg.get.return_value = None
        with patch("gateway.web_ui.settings") as ms, \
             patch("gateway.web_ui.registry", mock_reg), \
             patch("gateway.web_ui.pool_manager", mock_pm):
            ms.api_key = ""
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post(
                "/api/connect",
                json={"name": "my-db", "uri": "postgresql://localhost/mydb"},
            )
        assert resp.status_code == 200

    def test_empty_name_rejected(self):
        app = self._make_connect_app()
        with patch("gateway.web_ui.settings") as ms:
            ms.api_key = ""
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post(
                "/api/connect",
                json={"name": "", "uri": "postgresql://localhost/db"},
            )
        assert resp.status_code == 400

    def test_missing_uri_rejected(self):
        app = self._make_connect_app()
        with patch("gateway.web_ui.settings") as ms:
            ms.api_key = ""
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post("/api/connect", json={"name": "db1"})
        assert resp.status_code == 400


class TestUriSanitization:
    """URI password should be scrubbed in logs and safe_uri helper."""

    def test_safe_uri_redacts_password(self):
        from gateway.db_registry import DatabaseInfo
        db = DatabaseInfo(name="x", uri="postgresql://user:supersecret@localhost/db")
        safe = db.safe_uri()
        assert "supersecret" not in safe
        assert "****" in safe
        assert "user" in safe
        assert "localhost" in safe

    def test_safe_uri_no_password(self):
        from gateway.db_registry import DatabaseInfo
        db = DatabaseInfo(name="x", uri="postgresql://user@localhost/db")
        safe = db.safe_uri()
        assert "user" in safe
        assert "localhost" in safe

    def test_safe_uri_empty_password(self):
        from gateway.db_registry import DatabaseInfo
        db = DatabaseInfo(name="x", uri="postgresql://user:@localhost/db")
        # Should not raise
        safe = db.safe_uri()
        assert "localhost" in safe


# ── MCP Error Format Tests ────────────────────────────────────────────

class TestMcpErrorFormat:
    """Verify MCP errors follow the spec (isError=True in CallToolResult)."""

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_call_tool_result_with_is_error(self):
        from gateway.mcp_server import call_tool
        from mcp.types import CallToolResult

        result = await call_tool("nonexistent_tool", {})
        assert isinstance(result, CallToolResult)
        assert result.isError is True

    @pytest.mark.asyncio
    async def test_exception_returns_call_tool_result_with_is_error(self):
        from gateway.mcp_server import call_tool
        from gateway import mcp_server
        from mcp.types import CallToolResult

        mock_handle = AsyncMock(side_effect=RuntimeError("DB error"))

        with patch.dict(mcp_server._TOOL_DISPATCH, {"execute_sql": MagicMock(handle=mock_handle)}):
            result = await call_tool("execute_sql", {})

        assert isinstance(result, CallToolResult)
        assert result.isError is True
        assert "DB error" in result.content[0].text

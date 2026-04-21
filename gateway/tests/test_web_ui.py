"""Tests for gateway.web_ui — dashboard rendering, API endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient
from starlette.applications import Starlette
from starlette.routing import Route
from gateway import __version__

_LEGACY_CONFIG_PATH = "." + "cl" + "aude"


def _build_app():
    from starlette.responses import HTMLResponse
    from gateway.web_ui import (
        dashboard_page, render_docs, api_status, api_databases, api_connect,
        api_disconnect, api_edit, api_switch,
    )

    async def dashboard_docs(request):
        return HTMLResponse(render_docs(request.query_params.get("lang", "ru")))

    return Starlette(routes=[
        Route("/dashboard", dashboard_page),
        Route("/dashboard/docs", dashboard_docs),
        Route("/api/status", api_status),
        Route("/api/databases", api_databases),
        Route("/api/connect", api_connect, methods=["POST"]),
        Route("/api/disconnect", api_disconnect, methods=["POST"]),
        Route("/api/edit", api_edit, methods=["POST"]),
        Route("/api/switch", api_switch, methods=["POST"]),
    ])


class TestDashboardPage:
    """Tests for /dashboard HTML page rendering."""

    def test_dashboard_returns_html(self):
        app = _build_app()
        with patch("gateway.web_ui.settings") as ms:
            ms.api_key = ""
            client = TestClient(app)
            resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_dashboard_lang_ru_default(self):
        app = _build_app()
        with patch("gateway.web_ui.settings") as ms:
            ms.api_key = ""
            client = TestClient(app)
            resp = client.get("/dashboard")
        # Should contain Russian language content
        assert "postgres-mcp-universal" in resp.text

    def test_dashboard_lang_en(self):
        app = _build_app()
        with patch("gateway.web_ui.settings") as ms:
            ms.api_key = ""
            client = TestClient(app)
            resp = client.get("/dashboard?lang=en")
        assert resp.status_code == 200
        assert "MCP gateway" in resp.text

    def test_dashboard_api_key_not_exposed_in_wrong_context(self):
        """Dashboard HTML must not embed server-side API key secrets."""
        app = _build_app()
        with patch("gateway.web_ui.settings") as ms:
            ms.api_key = "my-super-secret-key"
            client = TestClient(app)
            resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert "my-super-secret-key" not in resp.text

    def test_dashboard_sets_csp_header(self):
        app = _build_app()
        with patch("gateway.web_ui.settings") as ms:
            ms.api_key = ""
            client = TestClient(app)
            resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert "Content-Security-Policy" in resp.headers
        assert "default-src 'self'" in resp.headers["Content-Security-Policy"]

    def test_dashboard_visual_accessibility_markers_present(self):
        app = _build_app()
        with patch("gateway.web_ui.settings") as ms:
            ms.api_key = ""
            client = TestClient(app)
            resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert "focus-visible" in resp.text
        assert 'aria-live="polite"' in resp.text
        assert '<button type="button" class="rd"' in resp.text
        assert 'role="dialog"' in resp.text
        assert 'aria-modal="true"' in resp.text

    def test_dashboard_docs_ru_contains_actual_tool_count(self):
        app = _build_app()
        with patch("gateway.web_ui.settings") as ms:
            ms.api_key = ""
            client = TestClient(app)
            resp = client.get("/dashboard/docs?lang=ru")
        assert resp.status_code == 200
        assert "23 MCP tools" in resp.text
        assert "pg_overview" in resp.text
        assert "pg_schemas" in resp.text
        assert "docs/mcp-tool-catalog.md" in resp.text
        assert f"v{__version__}" in resp.text
        assert "любого MCP-клиента" in resp.text
        assert ".\\install.cmd" in resp.text
        assert "Codex" in resp.text
        assert _LEGACY_CONFIG_PATH not in resp.text

    def test_dashboard_docs_en_contains_actual_tool_count(self):
        app = _build_app()
        with patch("gateway.web_ui.settings") as ms:
            ms.api_key = ""
            client = TestClient(app)
            resp = client.get("/dashboard/docs?lang=en")
        assert resp.status_code == 200
        assert "23 MCP tools" in resp.text
        assert "pg_overview" in resp.text
        assert "/dashboard/docs" in resp.text
        assert "docs/mcp-tool-catalog.md" in resp.text
        assert f"v{__version__}" in resp.text
        assert "Connect Any MCP Client" in resp.text
        assert ".\\install.cmd" in resp.text
        assert "Codex" in resp.text
        assert _LEGACY_CONFIG_PATH not in resp.text

    def test_dashboard_contains_mobile_layout_basics(self):
        app = _build_app()
        with patch("gateway.web_ui.settings") as ms:
            ms.api_key = ""
            client = TestClient(app)
            resp = client.get("/dashboard?lang=en")
        assert resp.status_code == 200
        assert '<meta name="viewport" content="width=device-width,initial-scale=1">' in resp.text
        assert "@media(max-width:900px)" in resp.text
        assert "@media(max-width:600px)" in resp.text

    def test_dashboard_docs_mentions_manual_mcp_reachability_check(self):
        app = _build_app()
        with patch("gateway.web_ui.settings") as ms:
            ms.api_key = ""
            client = TestClient(app)
            resp = client.get("/dashboard/docs?lang=ru")
        assert "POST" in resp.text
        assert "/mcp" in resp.text
        assert "PG_MCP_STATE_FILE" in resp.text

    def test_dashboard_pages_are_not_rate_limited(self):
        app = _build_app()
        with patch("gateway.web_ui.settings") as ms:
            ms.api_key = ""
            ms.rate_limit_enabled = True
            ms.rate_limit_window_seconds = 60
            ms.rate_limit_api_requests = 1
            client = TestClient(app)
            dashboard = client.get("/dashboard")
            docs = client.get("/dashboard/docs?lang=en")
        assert dashboard.status_code == 200
        assert docs.status_code == 200


class TestApiConnectValidation:
    """Tests for /api/connect input validation."""

    def test_missing_name_returns_400(self):
        app = _build_app()
        with patch("gateway.web_ui.settings") as ms:
            ms.api_key = ""
            client = TestClient(app)
            resp = client.post("/api/connect", json={"uri": "postgresql://localhost/db"})
        assert resp.status_code == 400

    def test_missing_uri_returns_400(self):
        app = _build_app()
        with patch("gateway.web_ui.settings") as ms:
            ms.api_key = ""
            client = TestClient(app)
            resp = client.post("/api/connect", json={"name": "db1"})
        assert resp.status_code == 400

    def test_invalid_name_returns_400(self):
        app = _build_app()
        with patch("gateway.web_ui.settings") as ms:
            ms.api_key = ""
            client = TestClient(app)
            resp = client.post(
                "/api/connect",
                json={"name": "my db!", "uri": "postgresql://localhost/db"},
            )
        assert resp.status_code == 400
        assert "Invalid" in resp.json()["error"]

    def test_connection_failure_returns_500(self):
        app = _build_app()
        mock_pm = MagicMock()
        mock_pm.connect = AsyncMock(side_effect=Exception("Connection refused"))
        mock_reg = MagicMock()
        mock_reg.add = MagicMock()
        mock_reg.remove = MagicMock()
        mock_reg.get.return_value = None
        with patch("gateway.web_ui.settings") as ms, \
             patch("gateway.web_ui.registry", mock_reg), \
             patch("gateway.web_ui.pool_manager", mock_pm):
            ms.api_key = ""
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post(
                "/api/connect",
                json={"name": "baddb", "uri": "postgresql://invalid/db"},
            )
        assert resp.status_code == 500
        assert "error" in resp.json()


class TestApiDisconnect:
    """Tests for /api/disconnect."""

    def test_disconnect_not_found_returns_404(self):
        app = _build_app()
        mock_reg = MagicMock()
        mock_reg.remove.return_value = None
        with patch("gateway.web_ui.settings") as ms, \
             patch("gateway.web_ui.registry", mock_reg):
            ms.api_key = ""
            client = TestClient(app)
            resp = client.post("/api/disconnect", json={"name": "nonexistent"})
        assert resp.status_code == 404

    def test_disconnect_missing_name_returns_400(self):
        app = _build_app()
        with patch("gateway.web_ui.settings") as ms:
            ms.api_key = ""
            client = TestClient(app)
            resp = client.post("/api/disconnect", json={})
        assert resp.status_code == 400

    def test_disconnect_success(self):
        app = _build_app()
        mock_pm = MagicMock()
        mock_pm.disconnect = AsyncMock()
        mock_reg = MagicMock()
        fake_db = MagicMock()
        mock_reg.remove.return_value = fake_db
        with patch("gateway.web_ui.settings") as ms, \
             patch("gateway.web_ui.registry", mock_reg), \
             patch("gateway.web_ui.pool_manager", mock_pm):
            ms.api_key = ""
            client = TestClient(app)
            resp = client.post("/api/disconnect", json={"name": "mydb"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


class TestApiSwitch:
    """Tests for /api/switch."""

    def test_switch_missing_name_returns_400(self):
        app = _build_app()
        with patch("gateway.web_ui.settings") as ms:
            ms.api_key = ""
            client = TestClient(app)
            resp = client.post("/api/switch", json={})
        assert resp.status_code == 400

    def test_switch_success(self):
        app = _build_app()
        mock_pm = MagicMock()
        mock_pm.switch_db = MagicMock()
        mock_reg = MagicMock()
        mock_reg.active = ""
        mock_reg.save = MagicMock()
        with patch("gateway.web_ui.settings") as ms, \
             patch("gateway.web_ui.registry", mock_reg), \
             patch("gateway.web_ui.pool_manager", mock_pm):
            ms.api_key = ""
            client = TestClient(app)
            resp = client.post("/api/switch", json={"name": "mydb"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_switch_unknown_db_returns_400(self):
        app = _build_app()
        mock_pm = MagicMock()
        mock_pm.switch_db = MagicMock(side_effect=ValueError("not connected"))
        mock_reg = MagicMock()
        with patch("gateway.web_ui.settings") as ms, \
             patch("gateway.web_ui.registry", mock_reg), \
             patch("gateway.web_ui.pool_manager", mock_pm):
            ms.api_key = ""
            client = TestClient(app)
            resp = client.post("/api/switch", json={"name": "nonexistent"})
        assert resp.status_code == 400


class TestApiEdit:
    """Tests for /api/edit endpoint."""

    def test_edit_missing_old_name_returns_400(self):
        app = _build_app()
        with patch("gateway.web_ui.settings") as ms:
            ms.api_key = ""
            client = TestClient(app)
            resp = client.post(
                "/api/edit",
                json={"name": "newname", "uri": "postgresql://localhost/db"},
            )
        assert resp.status_code == 400

    def test_edit_missing_name_returns_400(self):
        app = _build_app()
        with patch("gateway.web_ui.settings") as ms:
            ms.api_key = ""
            client = TestClient(app)
            resp = client.post(
                "/api/edit",
                json={"old_name": "oldname", "uri": "postgresql://localhost/db"},
            )
        assert resp.status_code == 400

    def test_edit_invalid_new_name_returns_400(self):
        app = _build_app()
        with patch("gateway.web_ui.settings") as ms:
            ms.api_key = ""
            client = TestClient(app)
            resp = client.post(
                "/api/edit",
                json={
                    "old_name": "oldname",
                    "name": "new name!",
                    "uri": "postgresql://localhost/db",
                },
            )
        assert resp.status_code == 400

    def test_edit_restores_default_when_renamed(self):
        """If the edited DB was the default, new name should become default."""
        app = _build_app()
        mock_pm = MagicMock()
        mock_pm.connect = AsyncMock()
        mock_pm.disconnect = AsyncMock()
        mock_reg = MagicMock()
        mock_reg.active = "oldname"
        mock_reg.remove.return_value = MagicMock()
        mock_reg.add = MagicMock()
        mock_reg.save = MagicMock()
        with patch("gateway.web_ui.settings") as ms, \
             patch("gateway.web_ui.registry", mock_reg), \
             patch("gateway.web_ui.pool_manager", mock_pm):
            ms.api_key = ""
            client = TestClient(app)
            resp = client.post(
                "/api/edit",
                json={
                    "old_name": "oldname",
                    "name": "newname",
                    "uri": "postgresql://localhost/db",
                },
            )
        assert resp.status_code == 200
        # active should have been set to new name
        assert mock_reg.active == "newname"


class TestDashboardApiLifecycle:
    def test_connection_lifecycle_connect_switch_list_disconnect(self):
        app = _build_app()
        mock_pm = MagicMock()
        mock_pm.connect = AsyncMock()
        mock_pm.disconnect = AsyncMock()
        mock_pm.switch_db = MagicMock()

        db = MagicMock()
        db.name = "prod"
        db.uri = "postgresql://localhost/prod"
        db.access_mode = "restricted"
        db.connected = True

        mock_reg = MagicMock()
        mock_reg.list_all.return_value = [db]
        mock_reg.remove.return_value = db
        mock_reg.active = ""
        mock_reg.save = MagicMock()

        with patch("gateway.web_ui.settings") as ms, \
             patch("gateway.web_ui.registry", mock_reg), \
             patch("gateway.web_ui.pool_manager", mock_pm):
            ms.api_key = ""
            client = TestClient(app)

            connect_resp = client.post(
                "/api/connect",
                json={"name": "prod", "uri": "postgresql://localhost/prod", "access_mode": "restricted"},
            )
            assert connect_resp.status_code == 200
            assert connect_resp.json()["ok"] is True
            assert connect_resp.json()["name"] == "prod"
            mock_pm.connect.assert_awaited_once()

            switch_resp = client.post("/api/switch", json={"name": "prod"})
            assert switch_resp.status_code == 200
            assert switch_resp.json()["ok"] is True
            mock_pm.switch_db.assert_called_once_with("prod")
            assert mock_reg.active == "prod"
            assert mock_reg.save.called

            list_resp = client.get("/api/databases")
            assert list_resp.status_code == 200
            listed = list_resp.json()
            assert listed[0]["name"] == "prod"
            assert listed[0]["connected"] is True

            disconnect_resp = client.post("/api/disconnect", json={"name": "prod"})
            assert disconnect_resp.status_code == 200
            assert disconnect_resp.json()["ok"] is True
            mock_pm.disconnect.assert_awaited_once_with("prod")

    def test_databases_endpoint_returns_redacted_safe_uri(self):
        app = _build_app()
        from gateway.db_registry import DatabaseInfo

        db = DatabaseInfo(
            name="prod",
            uri="postgresql://user:supersecret@localhost/prod",
            access_mode="restricted",
            connected=True,
        )

        mock_reg = MagicMock()
        mock_reg.list_all.return_value = [db]

        with patch("gateway.web_ui.settings") as ms, patch("gateway.web_ui.registry", mock_reg):
            ms.api_key = ""
            client = TestClient(app)
            resp = client.get("/api/databases")

        assert resp.status_code == 200
        row = resp.json()[0]
        assert row["name"] == "prod"
        assert "safe_uri" in row
        assert "supersecret" not in row["safe_uri"]
        assert "****" in row["safe_uri"]
        assert "uri" not in row

    def test_edit_preserves_old_password_when_safe_uri_omits_it(self):
        app = _build_app()
        from gateway.db_registry import DatabaseInfo

        old_db = DatabaseInfo(
            name="prod",
            uri="postgresql://user:supersecret@localhost:5432/prod",
            access_mode="restricted",
            connected=True,
        )

        mock_reg = MagicMock()
        mock_reg.active = "prod"
        mock_reg.get.return_value = old_db
        mock_reg.remove.return_value = old_db
        mock_reg.save = MagicMock()

        mock_pm = MagicMock()
        mock_pm.disconnect = AsyncMock()
        mock_pm.connect = AsyncMock()

        with patch("gateway.web_ui.settings") as ms, \
             patch("gateway.web_ui.registry", mock_reg), \
             patch("gateway.web_ui.pool_manager", mock_pm):
            ms.api_key = ""
            client = TestClient(app)
            resp = client.post(
                "/api/edit",
                json={
                    "old_name": "prod",
                    "name": "prod",
                    "uri": "postgresql://user@localhost:5432/prod",
                    "access_mode": "restricted",
                },
            )

        assert resp.status_code == 200
        added_db = mock_reg.add.call_args.args[0]
        assert "supersecret" in added_db.uri


class TestDashboardErrorContract:
    def test_mutation_endpoints_return_json_error_payload(self):
        app = _build_app()
        cases = [
            ("/api/connect", {"uri": "postgresql://localhost/db"}, 400),
            ("/api/disconnect", {}, 400),
            ("/api/edit", {"name": "prod", "uri": "postgresql://localhost/db"}, 400),
            ("/api/switch", {}, 400),
        ]

        with patch("gateway.web_ui.settings") as ms:
            ms.api_key = ""
            client = TestClient(app)
            for endpoint, payload, status_code in cases:
                resp = client.post(endpoint, json=payload)
                assert resp.status_code == status_code
                assert "application/json" in resp.headers["content-type"]
                assert isinstance(resp.json().get("error"), str)

    def test_mutation_endpoints_return_429_when_rate_limited(self):
        from gateway.rate_limit import limiter

        app = _build_app()
        cases = [
            ("/api/status", None),
            ("/api/connect", {"name": "prod", "uri": "postgresql://localhost/prod"}),
            ("/api/disconnect", {"name": "prod"}),
            ("/api/edit", {"old_name": "prod", "name": "prod2", "uri": "postgresql://localhost/prod2"}),
            ("/api/switch", {"name": "prod"}),
        ]

        for endpoint, payload in cases:
            limiter.reset()
            with patch("gateway.web_ui.settings") as ms:
                ms.api_key = ""
                ms.rate_limit_enabled = True
                ms.rate_limit_window_seconds = 60
                ms.rate_limit_api_requests = 1
                with patch("gateway.web_ui.pool_manager") as pm:
                    pm.get_status.return_value = {"ok": True}
                    client = TestClient(app)
                    if payload is None:
                        first = client.get(endpoint)
                        second = client.get(endpoint)
                    else:
                        first = client.post(endpoint, json=payload)
                        second = client.post(endpoint, json=payload)

            assert first.status_code != 429
            assert second.status_code == 429
            assert second.json()["error"] == "rate_limited"
            assert second.headers["Retry-After"].isdigit()


class TestInternalHelpersAndAuth:
    def test_wrapper_helpers_delegate_to_shared_implementations(self):
        from gateway import web_ui

        ok = web_ui._json({"ok": True}, status_code=202)
        assert ok.status_code == 202

        merged = web_ui._merge_password_from_old_uri(
            "postgresql://user@localhost/db",
            "postgresql://user:secret@localhost/db",
        )
        assert "secret" in merged

    def test_api_edit_returns_401_when_bearer_token_missing(self):
        app = _build_app()
        with patch("gateway.web_ui.settings") as ms:
            ms.api_key = "secret"
            client = TestClient(app)
            resp = client.post(
                "/api/edit",
                json={"old_name": "old", "name": "new", "uri": "postgresql://localhost/db"},
            )
        assert resp.status_code == 401

"""Tests for gateway.tools.admin — connect/disconnect/switch/list databases."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp.types import TextContent


class TestConnectDatabase:
    """Tests for connect_database tool."""

    @pytest.mark.asyncio
    async def test_connect_database_success(self, tmp_path):
        from gateway.tools import admin as admin_mod
        import gateway.db_registry as db_reg_mod
        from gateway.db_registry import DatabaseRegistry

        reg = DatabaseRegistry()
        mock_pm = MagicMock()
        mock_pm.connect = AsyncMock()

        with patch.object(db_reg_mod, "registry", reg), \
             patch.object(admin_mod, "registry", reg), \
             patch.object(admin_mod, "pool_manager", mock_pm), \
             patch("gateway.db_registry.STATE_FILE", str(tmp_path / "s.json")):
            result = await admin_mod.handle("connect_database", {
                "name": "mydb",
                "uri": "postgresql://localhost/mydb",
            })

        assert "Connected" in result[0].text
        assert "mydb" in result[0].text
        mock_pm.connect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connect_database_with_restricted_mode(self, tmp_path):
        from gateway.tools import admin as admin_mod
        import gateway.db_registry as db_reg_mod
        from gateway.db_registry import DatabaseRegistry

        reg = DatabaseRegistry()
        mock_pm = MagicMock()
        mock_pm.connect = AsyncMock()

        with patch.object(db_reg_mod, "registry", reg), \
             patch.object(admin_mod, "registry", reg), \
             patch.object(admin_mod, "pool_manager", mock_pm), \
             patch("gateway.db_registry.STATE_FILE", str(tmp_path / "s.json")):
            result = await admin_mod.handle("connect_database", {
                "name": "ro_db",
                "uri": "postgresql://localhost/ro_db",
                "access_mode": "restricted",
            })

        assert "restricted" in result[0].text


class TestDisconnectDatabase:
    """Tests for disconnect_database tool."""

    @pytest.mark.asyncio
    async def test_disconnect_existing_db(self, tmp_path):
        from gateway.tools import admin as admin_mod
        import gateway.db_registry as db_reg_mod
        from gateway.db_registry import DatabaseRegistry, DatabaseInfo

        reg = DatabaseRegistry()
        mock_pm = MagicMock()
        mock_pm.disconnect = AsyncMock()

        with patch.object(db_reg_mod, "registry", reg), \
             patch.object(admin_mod, "registry", reg), \
             patch.object(admin_mod, "pool_manager", mock_pm), \
             patch("gateway.db_registry.STATE_FILE", str(tmp_path / "s.json")):
            reg.add(DatabaseInfo(name="mydb", uri="postgresql://localhost/mydb"))
            result = await admin_mod.handle("disconnect_database", {"name": "mydb"})

        assert "Disconnected" in result[0].text
        mock_pm.disconnect.assert_awaited_once_with("mydb")

    @pytest.mark.asyncio
    async def test_disconnect_nonexistent_db(self, tmp_path):
        from gateway.tools import admin as admin_mod
        import gateway.db_registry as db_reg_mod
        from gateway.db_registry import DatabaseRegistry

        reg = DatabaseRegistry()
        mock_pm = MagicMock()
        mock_pm.disconnect = AsyncMock()

        with patch.object(db_reg_mod, "registry", reg), \
             patch.object(admin_mod, "registry", reg), \
             patch.object(admin_mod, "pool_manager", mock_pm), \
             patch("gateway.db_registry.STATE_FILE", str(tmp_path / "s.json")):
            result = await admin_mod.handle("disconnect_database", {"name": "nonexistent"})

        assert "not found" in result[0].text
        mock_pm.disconnect.assert_not_awaited()


class TestSwitchDatabase:
    """Tests for switch_database tool."""

    @pytest.mark.asyncio
    async def test_switch_database_success(self):
        from gateway.tools import admin as admin_mod

        mock_pm = MagicMock()
        mock_pm.switch_db = MagicMock()

        with patch.object(admin_mod, "pool_manager", mock_pm):
            result = await admin_mod.handle("switch_database", {"name": "analytics"}, session_id="sess-1")

        mock_pm.switch_db.assert_called_once_with("analytics", session_id="sess-1")
        assert "Switched" in result[0].text
        assert "analytics" in result[0].text

    @pytest.mark.asyncio
    async def test_switch_database_raises_propagates(self):
        from gateway.tools import admin as admin_mod

        mock_pm = MagicMock()
        mock_pm.switch_db = MagicMock(side_effect=ValueError("Database 'x' is not connected"))

        with patch.object(admin_mod, "pool_manager", mock_pm):
            with pytest.raises(ValueError):
                await admin_mod.handle("switch_database", {"name": "x"})


class TestListDatabases:
    """Tests for list_databases tool."""

    @pytest.mark.asyncio
    async def test_list_databases_empty(self):
        from gateway.tools import admin as admin_mod
        import gateway.db_registry as db_reg_mod
        from gateway.db_registry import DatabaseRegistry

        reg = DatabaseRegistry()
        mock_pm = MagicMock()
        mock_pm.get_active_db = MagicMock(return_value="")

        with patch.object(db_reg_mod, "registry", reg), \
             patch.object(admin_mod, "registry", reg), \
             patch.object(admin_mod, "pool_manager", mock_pm):
            result = await admin_mod.handle("list_databases", {})

        assert "No databases" in result[0].text

    @pytest.mark.asyncio
    async def test_list_databases_shows_all(self, tmp_path):
        from gateway.tools import admin as admin_mod
        import gateway.db_registry as db_reg_mod
        from gateway.db_registry import DatabaseRegistry, DatabaseInfo

        reg = DatabaseRegistry()
        mock_pm = MagicMock()
        mock_pm.get_active_db = MagicMock(return_value="primary")

        with patch.object(db_reg_mod, "registry", reg), \
             patch.object(admin_mod, "registry", reg), \
             patch.object(admin_mod, "pool_manager", mock_pm), \
             patch("gateway.db_registry.STATE_FILE", str(tmp_path / "s.json")):
            reg.add(DatabaseInfo(name="primary", uri="postgresql://localhost/primary"))
            reg.add(DatabaseInfo(name="secondary", uri="postgresql://localhost/secondary"))
            result = await admin_mod.handle("list_databases", {})

        text = result[0].text
        assert "primary" in text
        assert "secondary" in text

    @pytest.mark.asyncio
    async def test_list_databases_marks_active(self, tmp_path):
        from gateway.tools import admin as admin_mod
        import gateway.db_registry as db_reg_mod
        from gateway.db_registry import DatabaseRegistry, DatabaseInfo

        reg = DatabaseRegistry()
        mock_pm = MagicMock()
        mock_pm.get_active_db = MagicMock(return_value="primary")

        with patch.object(db_reg_mod, "registry", reg), \
             patch.object(admin_mod, "registry", reg), \
             patch.object(admin_mod, "pool_manager", mock_pm), \
             patch("gateway.db_registry.STATE_FILE", str(tmp_path / "s.json")):
            reg.add(DatabaseInfo(name="primary", uri="postgresql://localhost/primary"))
            result = await admin_mod.handle("list_databases", {})

        # Active DB should be marked with *
        text = result[0].text
        assert "*" in text

    @pytest.mark.asyncio
    async def test_list_databases_ignores_compat_placeholder(self, tmp_path):
        from gateway.tools import admin as admin_mod
        import gateway.db_registry as db_reg_mod
        from gateway.db_registry import DatabaseRegistry, DatabaseInfo

        reg = DatabaseRegistry()
        mock_pm = MagicMock()
        mock_pm.get_active_db = MagicMock(return_value="primary")

        with patch.object(db_reg_mod, "registry", reg), \
             patch.object(admin_mod, "registry", reg), \
             patch.object(admin_mod, "pool_manager", mock_pm), \
             patch("gateway.db_registry.STATE_FILE", str(tmp_path / "s.json")):
            reg.add(DatabaseInfo(name="primary", uri="postgresql://localhost/primary"))
            result = await admin_mod.handle("list_databases", {"_compat": True})

        assert "primary" in result[0].text


class TestGetServerStatus:
    """Tests for get_server_status tool."""

    @pytest.mark.asyncio
    async def test_get_server_status_returns_json(self):
        from gateway.tools import admin as admin_mod

        mock_status = {
            "pools": {"mydb": {"size": 5, "free": 3, "used": 2}},
            "sessions": 1,
            "active_default": "mydb",
        }
        mock_pm = MagicMock()
        mock_pm.get_status = MagicMock(return_value=mock_status)

        with patch.object(admin_mod, "pool_manager", mock_pm):
            result = await admin_mod.handle("get_server_status", {})

        data = json.loads(result[0].text)
        assert "pools" in data
        assert "sessions" in data

    @pytest.mark.asyncio
    async def test_get_server_status_ignores_compat_placeholder(self):
        from gateway.tools import admin as admin_mod

        mock_status = {"pools": {}, "sessions": 0, "active_default": ""}
        mock_pm = MagicMock()
        mock_pm.get_status = MagicMock(return_value=mock_status)

        with patch.object(admin_mod, "pool_manager", mock_pm):
            result = await admin_mod.handle("get_server_status", {"_compat": True})

        data = json.loads(result[0].text)
        assert data["sessions"] == 0

    @pytest.mark.asyncio
    async def test_unknown_admin_tool_returns_error(self):
        from gateway.tools import admin as admin_mod

        result = await admin_mod.handle("unknown_admin_tool", {})
        assert "Unknown" in result[0].text

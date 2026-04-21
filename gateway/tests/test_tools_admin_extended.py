"""Extended tests for admin tools — connection_string alias, re-connect, error handling."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp.types import TextContent


class TestConnectDatabaseAlias:
    """Test connection_string alias and error paths in connect_database."""

    @pytest.mark.asyncio
    async def test_connection_string_alias_works(self, tmp_path):
        from gateway.tools import admin as admin_mod
        import gateway.db_registry as db_reg_mod
        from gateway.db_registry import DatabaseRegistry

        reg = DatabaseRegistry()
        mock_pm = MagicMock()
        mock_pm.connect = AsyncMock()
        mock_pm.disconnect = AsyncMock()

        with patch.object(db_reg_mod, "registry", reg), \
             patch.object(admin_mod, "registry", reg), \
             patch.object(admin_mod, "pool_manager", mock_pm), \
             patch("gateway.db_registry.STATE_FILE", str(tmp_path / "s.json")):
            result = await admin_mod.handle("connect_database", {
                "name": "mydb",
                "connection_string": "postgresql://localhost/mydb",
            })

        assert "Connected" in result[0].text
        assert "mydb" in result[0].text
        mock_pm.connect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_missing_uri_and_connection_string_returns_error(self, tmp_path):
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
            result = await admin_mod.handle("connect_database", {"name": "mydb"})

        assert "required" in result[0].text.lower()
        mock_pm.connect.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_connect_failure_removes_db_from_registry(self, tmp_path):
        from gateway.tools import admin as admin_mod
        import gateway.db_registry as db_reg_mod
        from gateway.db_registry import DatabaseRegistry

        reg = DatabaseRegistry()
        mock_pm = MagicMock()
        mock_pm.connect = AsyncMock(side_effect=Exception("Connection refused"))
        mock_pm.disconnect = AsyncMock()

        with patch.object(db_reg_mod, "registry", reg), \
             patch.object(admin_mod, "registry", reg), \
             patch.object(admin_mod, "pool_manager", mock_pm), \
             patch("gateway.db_registry.STATE_FILE", str(tmp_path / "s.json")):
            result = await admin_mod.handle("connect_database", {
                "name": "baddb",
                "uri": "postgresql://localhost/baddb",
            })

        assert "Failed" in result[0].text
        # Database should have been removed from registry after failure
        assert reg.get("baddb") is None

    @pytest.mark.asyncio
    async def test_reconnect_replaces_existing_connection(self, tmp_path):
        from gateway.tools import admin as admin_mod
        import gateway.db_registry as db_reg_mod
        from gateway.db_registry import DatabaseRegistry, DatabaseInfo

        reg = DatabaseRegistry()
        mock_pm = MagicMock()
        mock_pm.connect = AsyncMock()
        mock_pm.disconnect = AsyncMock()

        with patch.object(db_reg_mod, "registry", reg), \
             patch.object(admin_mod, "registry", reg), \
             patch.object(admin_mod, "pool_manager", mock_pm), \
             patch("gateway.db_registry.STATE_FILE", str(tmp_path / "s.json")):
            # First connect
            await admin_mod.handle("connect_database", {
                "name": "mydb",
                "uri": "postgresql://localhost/mydb",
            })
            # Reconnect with different URI
            await admin_mod.handle("connect_database", {
                "name": "mydb",
                "uri": "postgresql://newhost/mydb",
            })

        # disconnect should have been called once (for the re-connect)
        mock_pm.disconnect.assert_awaited_once_with("mydb")
        # connect should have been called twice
        assert mock_pm.connect.await_count == 2

    @pytest.mark.asyncio
    async def test_uri_takes_precedence_over_connection_string(self, tmp_path):
        from gateway.tools import admin as admin_mod
        import gateway.db_registry as db_reg_mod
        from gateway.db_registry import DatabaseRegistry

        reg = DatabaseRegistry()
        mock_pm = MagicMock()
        mock_pm.connect = AsyncMock()
        mock_pm.disconnect = AsyncMock()

        with patch.object(db_reg_mod, "registry", reg), \
             patch.object(admin_mod, "registry", reg), \
             patch.object(admin_mod, "pool_manager", mock_pm), \
             patch("gateway.db_registry.STATE_FILE", str(tmp_path / "s.json")):
            result = await admin_mod.handle("connect_database", {
                "name": "mydb",
                "uri": "postgresql://primary/mydb",
                "connection_string": "postgresql://secondary/mydb",
            })

        # uri should take precedence
        assert reg.get("mydb").uri == "postgresql://primary/mydb"


class TestDisconnectEdgeCases:
    """Edge case tests for disconnect_database."""

    @pytest.mark.asyncio
    async def test_disconnect_calls_save_on_registry(self, tmp_path):
        """disconnect_database should persist registry state."""
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
        # State file should have been written
        assert (tmp_path / "s.json").exists()


class TestThreadSafeRegistry:
    """Verify DatabaseRegistry thread-safety properties."""

    def test_concurrent_adds_dont_corrupt_active(self, tmp_path):
        """Multiple sequential adds should maintain consistent active pointer."""
        import threading
        from gateway.db_registry import DatabaseRegistry, DatabaseInfo

        reg = DatabaseRegistry()
        errors = []

        def add_db(name):
            try:
                with patch("gateway.db_registry.STATE_FILE", str(tmp_path / "s.json")):
                    reg.add(DatabaseInfo(name=name, uri=f"postgresql://localhost/{name}"))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add_db, args=(f"db{i}",)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        # active should be one of the added DBs
        assert reg.active in {f"db{i}" for i in range(10)}
        assert len(reg.list_all()) == 10

    def test_safe_uri_is_not_exposed_in_to_dict(self):
        """to_dict excludes connected flag but retains URI (for state save)."""
        from gateway.db_registry import DatabaseInfo
        db = DatabaseInfo(name="x", uri="postgresql://user:pass@host/db")
        d = db.to_dict()
        # URI is retained for persistence (password is NOT stripped from stored state)
        assert d["uri"] == "postgresql://user:pass@host/db"
        # connected is excluded (transient)
        assert "connected" not in d

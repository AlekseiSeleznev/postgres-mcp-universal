"""Tests for gateway.pg_pool — PoolManager with mocked asyncpg."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_mock_pool(size=5, idle=3, min_s=2, max_s=10):
    """Create a mock asyncpg pool."""
    pool = MagicMock()
    pool.get_size.return_value = size
    pool.get_idle_size.return_value = idle
    pool.get_min_size.return_value = min_s
    pool.get_max_size.return_value = max_s
    pool.close = AsyncMock()
    return pool


def _make_db_info(name="testdb", uri="postgresql://localhost/testdb"):
    from gateway.db_registry import DatabaseInfo
    return DatabaseInfo(name=name, uri=uri)


class TestPoolManagerConnect:
    """Tests for connect / disconnect lifecycle."""

    @pytest.mark.asyncio
    async def test_connect_creates_pool(self):
        from gateway.pg_pool import PoolManager

        mock_pool = _make_mock_pool()
        pm = PoolManager()
        db = _make_db_info()

        with patch("gateway.pg_pool.asyncpg.create_pool", AsyncMock(return_value=mock_pool)):
            await pm.connect(db)

        assert "testdb" in pm._pools
        assert db.connected is True

    @pytest.mark.asyncio
    async def test_connect_idempotent(self):
        """Connecting to an already-connected DB is a no-op."""
        from gateway.pg_pool import PoolManager

        mock_pool = _make_mock_pool()
        pm = PoolManager()
        db = _make_db_info()

        create_pool = AsyncMock(return_value=mock_pool)
        with patch("gateway.pg_pool.asyncpg.create_pool", create_pool):
            await pm.connect(db)
            await pm.connect(db)  # second call should be skipped

        assert create_pool.call_count == 1

    @pytest.mark.asyncio
    async def test_disconnect_closes_pool(self):
        from gateway.pg_pool import PoolManager

        mock_pool = _make_mock_pool()
        pm = PoolManager()
        db = _make_db_info()

        with patch("gateway.pg_pool.asyncpg.create_pool", AsyncMock(return_value=mock_pool)):
            await pm.connect(db)

        with patch("gateway.db_registry.registry.get", return_value=db):
            await pm.disconnect("testdb")

        mock_pool.close.assert_awaited_once()
        assert "testdb" not in pm._pools
        assert db.connected is False

    @pytest.mark.asyncio
    async def test_disconnect_nonexistent_is_safe(self):
        from gateway.pg_pool import PoolManager

        pm = PoolManager()
        # Should not raise
        await pm.disconnect("nonexistent")

    @pytest.mark.asyncio
    async def test_close_all_disconnects_all(self):
        from gateway.pg_pool import PoolManager

        pm = PoolManager()
        pool_a = _make_mock_pool()
        pool_b = _make_mock_pool()

        db_a = _make_db_info("a", "postgresql://localhost/a")
        db_b = _make_db_info("b", "postgresql://localhost/b")

        with patch("gateway.pg_pool.asyncpg.create_pool", AsyncMock(side_effect=[pool_a, pool_b])):
            await pm.connect(db_a)
            await pm.connect(db_b)

        with patch("gateway.db_registry.registry.get", return_value=None):
            await pm.close_all()

        assert pm._pools == {}


class TestPoolManagerSessionRouting:
    """Tests for get_active_db, switch_db, get_pool routing."""

    @pytest.mark.asyncio
    async def test_get_pool_returns_pool_for_active_db(self, tmp_path):
        from gateway.pg_pool import PoolManager
        from gateway.db_registry import DatabaseRegistry, DatabaseInfo
        import gateway.pg_pool as pg_pool_module

        reg = DatabaseRegistry()
        mock_pool = _make_mock_pool()
        pm = PoolManager()
        db = _make_db_info()

        with patch("gateway.db_registry.STATE_FILE", str(tmp_path / "s.json")):
            reg.add(DatabaseInfo(name="testdb", uri="postgresql://localhost/testdb"))

        with patch.object(pg_pool_module, "registry", reg), \
             patch("gateway.pg_pool.asyncpg.create_pool", AsyncMock(return_value=mock_pool)):
            await pm.connect(db)
            pool = pm.get_pool(session_id=None)

        assert pool is mock_pool

    @pytest.mark.asyncio
    async def test_get_pool_raises_when_no_active_db(self):
        from gateway.pg_pool import PoolManager
        import gateway.pg_pool as pg_pool_module
        from gateway.db_registry import DatabaseRegistry

        pm = PoolManager()
        empty_reg = DatabaseRegistry()

        with patch.object(pg_pool_module, "registry", empty_reg):
            with pytest.raises(RuntimeError, match="No active database"):
                pm.get_pool(session_id=None)

    @pytest.mark.asyncio
    async def test_get_pool_raises_when_db_not_connected(self, tmp_path):
        from gateway.pg_pool import PoolManager
        import gateway.pg_pool as pg_pool_module
        from gateway.db_registry import DatabaseRegistry, DatabaseInfo

        pm = PoolManager()
        reg = DatabaseRegistry()

        with patch("gateway.db_registry.STATE_FILE", str(tmp_path / "s.json")):
            reg.add(DatabaseInfo(name="testdb", uri="postgresql://localhost/testdb"))

        with patch.object(pg_pool_module, "registry", reg):
            with pytest.raises(RuntimeError, match="not connected"):
                pm.get_pool(session_id=None)

    @pytest.mark.asyncio
    async def test_switch_db_sets_session_routing(self, tmp_path):
        from gateway.pg_pool import PoolManager
        import gateway.db_registry as db_reg_module
        from gateway.db_registry import DatabaseRegistry, DatabaseInfo

        pm = PoolManager()
        reg = DatabaseRegistry()

        pool_a = _make_mock_pool()
        pool_b = _make_mock_pool()
        db_a = DatabaseInfo(name="a", uri="postgresql://localhost/a")
        db_b = DatabaseInfo(name="b", uri="postgresql://localhost/b")

        with patch("gateway.db_registry.STATE_FILE", str(tmp_path / "s.json")):
            reg.add(db_a)
            reg.add(db_b)

        with patch.object(db_reg_module, "registry", reg), \
             patch("gateway.pg_pool.asyncpg.create_pool", AsyncMock(side_effect=[pool_a, pool_b])):
            await pm.connect(db_a)
            await pm.connect(db_b)

        pm.switch_db("b", session_id="sess-1")
        assert pm.get_active_db("sess-1") == "b"

    @pytest.mark.asyncio
    async def test_switch_db_raises_for_unconnected(self):
        from gateway.pg_pool import PoolManager

        pm = PoolManager()
        with pytest.raises(ValueError, match="not connected"):
            pm.switch_db("nonexistent", session_id="sess-1")

    @pytest.mark.asyncio
    async def test_switch_db_without_session_sets_global(self, tmp_path):
        from gateway.pg_pool import PoolManager
        import gateway.pg_pool as pg_pool_module
        from gateway.db_registry import DatabaseRegistry, DatabaseInfo

        pm = PoolManager()
        reg = DatabaseRegistry()
        mock_pool = _make_mock_pool()
        db_b = DatabaseInfo(name="b", uri="postgresql://localhost/b")

        with patch("gateway.db_registry.STATE_FILE", str(tmp_path / "s.json")):
            reg.add(DatabaseInfo(name="a", uri="postgresql://localhost/a"))
            reg.add(db_b)

        with patch.object(pg_pool_module, "registry", reg), \
             patch("gateway.pg_pool.asyncpg.create_pool", AsyncMock(return_value=mock_pool)):
            await pm.connect(db_b)
            pm.switch_db("b", session_id=None)
            assert reg.active == "b"

    @pytest.mark.asyncio
    async def test_disconnect_cleans_related_sessions(self, tmp_path):
        from gateway.pg_pool import PoolManager
        import gateway.db_registry as db_reg_module
        from gateway.db_registry import DatabaseRegistry, DatabaseInfo

        pm = PoolManager()
        reg = DatabaseRegistry()
        mock_pool = _make_mock_pool()
        db = DatabaseInfo(name="testdb", uri="postgresql://localhost/testdb")

        with patch("gateway.db_registry.STATE_FILE", str(tmp_path / "s.json")):
            reg.add(db)

        with patch.object(db_reg_module, "registry", reg), \
             patch("gateway.pg_pool.asyncpg.create_pool", AsyncMock(return_value=mock_pool)):
            await pm.connect(db)

        # Attach session
        pm._sessions["sess-abc"] = __import__(
            "gateway.pg_pool", fromlist=["SessionState"]
        ).SessionState(db_name="testdb")

        with patch.object(db_reg_module, "registry", reg):
            await pm.disconnect("testdb")

        assert "sess-abc" not in pm._sessions

    def test_get_active_db_without_session_returns_registry_default(self):
        from gateway.pg_pool import PoolManager
        import gateway.pg_pool as pg_pool_module

        pm = PoolManager()
        fake_registry = MagicMock()
        fake_registry.active = "analytics"

        with patch.object(pg_pool_module, "registry", fake_registry):
            assert pm.get_active_db() == "analytics"

    @pytest.mark.asyncio
    async def test_get_pool_uses_session_mapping_and_updates_last_access(self, tmp_path):
        from gateway.pg_pool import PoolManager, SessionState
        import gateway.pg_pool as pg_pool_module
        from gateway.db_registry import DatabaseRegistry, DatabaseInfo

        pm = PoolManager()
        reg = DatabaseRegistry()
        mock_pool = _make_mock_pool()
        db = DatabaseInfo(name="testdb", uri="postgresql://localhost/testdb")

        with patch("gateway.db_registry.STATE_FILE", str(tmp_path / "s.json")):
            reg.add(db)

        with patch.object(pg_pool_module, "registry", reg), \
             patch("gateway.pg_pool.asyncpg.create_pool", AsyncMock(return_value=mock_pool)), \
             patch("gateway.pg_pool.time.time", return_value=100.0):
            await pm.connect(db)
            pm._sessions["sess-1"] = SessionState(db_name="testdb", last_access=50.0)
            assert pm.get_pool(session_id="sess-1") is mock_pool
            assert pm._sessions["sess-1"].last_access == 100.0


class TestPoolManagerStatus:
    """Tests for get_status and cleanup_sessions."""

    def test_get_status_empty(self):
        from gateway.pg_pool import PoolManager
        import gateway.db_registry as db_reg_module
        from gateway.db_registry import DatabaseRegistry

        pm = PoolManager()
        empty_reg = DatabaseRegistry()
        with patch.object(db_reg_module, "registry", empty_reg):
            status = pm.get_status()

        assert status["pools"] == {}
        assert status["sessions"] == 0

    @pytest.mark.asyncio
    async def test_get_status_with_pool(self, tmp_path):
        from gateway.pg_pool import PoolManager
        import gateway.db_registry as db_reg_module
        from gateway.db_registry import DatabaseRegistry, DatabaseInfo

        pm = PoolManager()
        reg = DatabaseRegistry()
        mock_pool = _make_mock_pool(size=5, idle=3, min_s=2, max_s=10)
        db = DatabaseInfo(name="testdb", uri="postgresql://localhost/testdb")

        with patch("gateway.db_registry.STATE_FILE", str(tmp_path / "s.json")):
            reg.add(db)

        with patch.object(db_reg_module, "registry", reg), \
             patch("gateway.pg_pool.asyncpg.create_pool", AsyncMock(return_value=mock_pool)):
            await pm.connect(db)
            status = pm.get_status()

        assert "testdb" in status["pools"]
        pool_info = status["pools"]["testdb"]
        assert pool_info["size"] == 5
        assert pool_info["free"] == 3
        assert pool_info["used"] == 2

    def test_cleanup_sessions_removes_expired(self):
        from gateway.pg_pool import PoolManager, SessionState
        import gateway.config as cfg_mod

        pm = PoolManager()
        # Add an expired session (last_access very far in the past)
        pm._sessions["old"] = SessionState(db_name="x", last_access=time.time() - 99999)
        pm._sessions["fresh"] = SessionState(db_name="x", last_access=time.time())

        with patch.object(cfg_mod.settings, "session_timeout", 1000):
            removed = pm.cleanup_sessions()

        assert removed == 1
        assert "old" not in pm._sessions
        assert "fresh" in pm._sessions

    def test_cleanup_sessions_returns_zero_when_nothing_expired(self):
        from gateway.pg_pool import PoolManager, SessionState
        import gateway.config as cfg_mod

        pm = PoolManager()
        pm._sessions["fresh"] = SessionState(db_name="x", last_access=time.time())

        with patch.object(cfg_mod.settings, "session_timeout", 99999):
            removed = pm.cleanup_sessions()

        assert removed == 0

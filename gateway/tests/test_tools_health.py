"""Tests for gateway.tools.health — db_health, active_queries, table_bloat, etc."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp.types import TextContent


def _dict_record(d: dict):
    """Make an asyncpg-like Record from a dict."""
    rec = MagicMock()
    rec.__getitem__ = lambda self, k: d[k]
    rec.keys = MagicMock(return_value=list(d.keys()))

    def _get(key, default=None):
        return d.get(key, default)

    rec.get = _get
    # Support dict(rec)
    rec.items = lambda: d.items()
    rec.__iter__ = lambda self: iter(d)
    return rec


def _make_pool(conn):
    """Wrap conn in a mock pool with acquire() context manager."""
    pool = MagicMock()
    pool.fetch = conn.fetch

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    pool.acquire.return_value = cm

    return pool


class TestDbHealth:
    """Tests for db_health tool."""

    @pytest.mark.asyncio
    async def test_db_health_returns_json(self):
        from gateway.tools import health as health_mod

        conn = MagicMock()
        conn.fetchval = AsyncMock(side_effect=[
            "PostgreSQL 16.1",  # version
            MagicMock(__str__=lambda self: "1 day, 2:30:00"),  # uptime
            "100 MB",  # database size
        ])
        conn.fetchrow = AsyncMock(side_effect=[
            _dict_record({
                "total": 10, "active": 2, "idle": 7,
                "idle_in_tx": 1, "max_conn": 100
            }),  # connections
            _dict_record({
                "hits": 9000, "reads": 1000, "hit_ratio_pct": 90.0
            }),  # cache
        ])
        conn.fetch = AsyncMock(side_effect=[
            [],  # dead tuples
            [],  # long queries
            [],  # replication
        ])

        pool = _make_pool(conn)

        with patch.object(health_mod.pool_manager, "get_pool", return_value=pool):
            result = await health_mod.handle("db_health", {})

        data = json.loads(result[0].text)
        assert "version" in data
        assert "connections" in data
        assert "cache" in data
        assert "database_size" in data

    @pytest.mark.asyncio
    async def test_db_health_includes_top_dead_tuples(self):
        from gateway.tools import health as health_mod

        dead_rec = _dict_record({
            "table": "public.orders",
            "n_dead_tup": 5000,
            "n_live_tup": 50000,
            "dead_pct": 10.0,
        })

        conn = MagicMock()
        conn.fetchval = AsyncMock(side_effect=[
            "PostgreSQL 16.1",
            MagicMock(__str__=lambda self: "0:01:00"),
            "50 MB",
        ])
        conn.fetchrow = AsyncMock(side_effect=[
            _dict_record({"total": 5, "active": 1, "idle": 4, "idle_in_tx": 0, "max_conn": 100}),
            _dict_record({"hits": 1000, "reads": 100, "hit_ratio_pct": 90.9}),
        ])
        conn.fetch = AsyncMock(side_effect=[
            [dead_rec],  # dead tuples
            [],  # long queries
            [],  # replication
        ])

        pool = _make_pool(conn)

        with patch.object(health_mod.pool_manager, "get_pool", return_value=pool):
            result = await health_mod.handle("db_health", {})

        data = json.loads(result[0].text)
        assert len(data["top_dead_tuples"]) == 1

    @pytest.mark.asyncio
    async def test_db_health_ignores_compat_placeholder(self):
        from gateway.tools import health as health_mod

        conn = MagicMock()
        conn.fetchval = AsyncMock(side_effect=[
            "PostgreSQL 16.1",
            MagicMock(__str__=lambda self: "0:10:00"),
            "10 MB",
        ])
        conn.fetchrow = AsyncMock(side_effect=[
            _dict_record({"total": 1, "active": 1, "idle": 0, "idle_in_tx": 0, "max_conn": 100}),
            _dict_record({"hits": 10, "reads": 1, "hit_ratio_pct": 90.9}),
        ])
        conn.fetch = AsyncMock(side_effect=[[], [], []])

        pool = _make_pool(conn)

        with patch.object(health_mod.pool_manager, "get_pool", return_value=pool):
            result = await health_mod.handle("db_health", {"_compat": True})

        data = json.loads(result[0].text)
        assert data["version"] == "PostgreSQL 16.1"


class TestActiveQueries:
    """Tests for active_queries tool."""

    @pytest.mark.asyncio
    async def test_active_queries_no_results(self):
        from gateway.tools import health as health_mod

        pool = MagicMock()
        pool.fetch = AsyncMock(return_value=[])

        with patch.object(health_mod.pool_manager, "get_pool", return_value=pool):
            result = await health_mod.handle("active_queries", {})

        assert "No active queries" in result[0].text

    @pytest.mark.asyncio
    async def test_active_queries_with_min_duration(self):
        from gateway.tools import health as health_mod

        pool = MagicMock()
        pool.fetch = AsyncMock(return_value=[])

        with patch.object(health_mod.pool_manager, "get_pool", return_value=pool):
            result = await health_mod.handle("active_queries", {"min_duration_ms": 500})

        text = result[0].text
        assert "No active queries" in text
        assert "500ms" in text

    @pytest.mark.asyncio
    async def test_active_queries_with_results(self):
        from gateway.tools import health as health_mod

        q_rec = _dict_record({
            "pid": 12345,
            "usename": "dbuser",
            "client_addr": "127.0.0.1",
            "duration": MagicMock(__str__=lambda self: "0:00:02.500000"),
            "state": "active",
            "wait_event_type": None,
            "wait_event": None,
            "query": "SELECT * FROM big_table",
        })

        pool = MagicMock()
        pool.fetch = AsyncMock(return_value=[q_rec])

        with patch.object(health_mod.pool_manager, "get_pool", return_value=pool):
            result = await health_mod.handle("active_queries", {})

        text = result[0].text
        assert "12345" in text
        assert "SELECT * FROM big_table" in text


class TestTableBloat:
    """Tests for table_bloat tool."""

    @pytest.mark.asyncio
    async def test_table_bloat_empty(self):
        from gateway.tools import health as health_mod

        pool = MagicMock()
        pool.fetch = AsyncMock(return_value=[])

        with patch.object(health_mod.pool_manager, "get_pool", return_value=pool):
            result = await health_mod.handle("table_bloat", {"schema": "public"})

        assert "No tables" in result[0].text

    @pytest.mark.asyncio
    async def test_table_bloat_with_data(self):
        from gateway.tools import health as health_mod

        bloat_rec = _dict_record({
            "table": "public.orders",
            "size": "10 MB",
            "n_dead_tup": 1000,
            "bloat_pct": 5.0,
            "last_autovacuum": None,
        })

        pool = MagicMock()
        pool.fetch = AsyncMock(return_value=[bloat_rec])

        with patch.object(health_mod.pool_manager, "get_pool", return_value=pool):
            result = await health_mod.handle("table_bloat", {"schema": "public"})

        text = result[0].text
        assert "orders" in text
        assert "never" in text  # last_autovacuum is None


class TestVacuumStats:
    """Tests for vacuum_stats tool."""

    @pytest.mark.asyncio
    async def test_vacuum_stats_empty_schema(self):
        from gateway.tools import health as health_mod

        pool = MagicMock()
        pool.fetch = AsyncMock(return_value=[])

        with patch.object(health_mod.pool_manager, "get_pool", return_value=pool):
            result = await health_mod.handle("vacuum_stats", {"schema": "public"})

        assert "No tables" in result[0].text

    @pytest.mark.asyncio
    async def test_vacuum_stats_returns_json(self):
        from gateway.tools import health as health_mod

        vac_rec = _dict_record({
            "table": "users",
            "n_live_tup": 1000,
            "n_dead_tup": 10,
            "last_vacuum": None,
            "last_autovacuum": "2024-01-01 00:00:00",
            "vacuum_count": 0,
            "autovacuum_count": 5,
            "last_analyze": None,
            "last_autoanalyze": None,
        })

        pool = MagicMock()
        pool.fetch = AsyncMock(return_value=[vac_rec])

        with patch.object(health_mod.pool_manager, "get_pool", return_value=pool):
            result = await health_mod.handle("vacuum_stats", {"schema": "public"})

        data = json.loads(result[0].text)
        assert isinstance(data, list)
        assert len(data) == 1


class TestLockInfo:
    """Tests for lock_info tool."""

    @pytest.mark.asyncio
    async def test_lock_info_no_blocks(self):
        from gateway.tools import health as health_mod

        pool = MagicMock()
        pool.fetch = AsyncMock(return_value=[])

        with patch.object(health_mod.pool_manager, "get_pool", return_value=pool):
            result = await health_mod.handle("lock_info", {})

        assert "No blocked queries" in result[0].text

    @pytest.mark.asyncio
    async def test_lock_info_with_blocked_query(self):
        from gateway.tools import health as health_mod

        lock_rec = _dict_record({
            "blocked_pid": 1001,
            "blocked_user": "user_a",
            "blocked_query": "UPDATE orders SET status='done' WHERE id=1",
            "blocking_pid": 1002,
            "blocking_user": "user_b",
            "blocking_query": "SELECT * FROM orders WHERE id=1 FOR UPDATE",
        })

        pool = MagicMock()
        pool.fetch = AsyncMock(return_value=[lock_rec])

        with patch.object(health_mod.pool_manager, "get_pool", return_value=pool):
            result = await health_mod.handle("lock_info", {})

        text = result[0].text
        assert "1001" in text
        assert "1002" in text
        assert "BLOCKED" in text

    @pytest.mark.asyncio
    async def test_lock_info_ignores_compat_placeholder(self):
        from gateway.tools import health as health_mod

        pool = MagicMock()
        pool.fetch = AsyncMock(return_value=[])

        with patch.object(health_mod.pool_manager, "get_pool", return_value=pool):
            result = await health_mod.handle("lock_info", {"_compat": True})

        assert "No blocked queries" in result[0].text

    @pytest.mark.asyncio
    async def test_unknown_health_tool_returns_error(self):
        from gateway.tools import health as health_mod

        pool = MagicMock()
        pool.fetch = AsyncMock(return_value=[])

        with patch.object(health_mod.pool_manager, "get_pool", return_value=pool):
            result = await health_mod.handle("unknown_tool", {})

        assert "Unknown" in result[0].text

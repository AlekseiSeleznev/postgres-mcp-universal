"""Tests for gateway.tools.monitoring — pg_overview, pg_activity, pg_table_stats,
pg_index_stats, pg_replication, pg_schemas."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp.types import TextContent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rec(d: dict):
    """Return an asyncpg-like Record mock from a plain dict."""
    rec = MagicMock()
    rec.__getitem__ = lambda self, k: d[k]
    rec.keys = MagicMock(return_value=list(d.keys()))
    rec.get = lambda k, default=None: d.get(k, default)
    rec.items = lambda: d.items()
    rec.__iter__ = lambda self: iter(d)
    return rec


def _pool_with_conn(conn):
    """Wrap a mock connection in a pool that exposes .fetch and .acquire()."""
    pool = MagicMock()
    pool.fetch = conn.fetch

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    pool.acquire.return_value = cm
    return pool


# ---------------------------------------------------------------------------
# TOOLS list
# ---------------------------------------------------------------------------

class TestMonitoringTools:
    """Verify TOOLS list contains all six monitoring tools."""

    def test_tools_count(self):
        from gateway.tools import monitoring as m
        assert len(m.TOOLS) == 6

    def test_tool_names(self):
        from gateway.tools import monitoring as m
        names = {t.name for t in m.TOOLS}
        assert names == {
            "pg_overview",
            "pg_activity",
            "pg_table_stats",
            "pg_index_stats",
            "pg_replication",
            "pg_schemas",
        }

    def test_tools_have_descriptions(self):
        from gateway.tools import monitoring as m
        for tool in m.TOOLS:
            assert tool.description, f"{tool.name} has no description"

    def test_tools_registered_in_mcp_server(self):
        """Ensure all monitoring tools appear in the server tool list."""
        from gateway.mcp_server import _all_tools
        names = {t.name for t in _all_tools()}
        assert "pg_overview" in names
        assert "pg_replication" in names
        assert "pg_schemas" in names

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("tool_name", "target", "payload"),
        [
            ("pg_overview", "get_overview", {"status": "ok"}),
            ("pg_activity", "get_activity", {"queries": [], "locks": []}),
            ("pg_replication", "get_replication", {"replicas": [], "slots": []}),
            ("pg_schemas", "get_schemas", []),
        ],
    )
    async def test_zero_arg_tools_ignore_compat_placeholder(self, tool_name, target, payload):
        from gateway.tools import monitoring as m

        with patch(f"gateway.monitoring.{target}", AsyncMock(return_value=payload)) as mock_call:
            result = await m.handle(tool_name, {"_compat": True})

        mock_call.assert_awaited_once_with(session_id=None)
        assert json.loads(result[0].text) == payload


# ---------------------------------------------------------------------------
# pg_overview
# ---------------------------------------------------------------------------

class TestPgOverview:
    @pytest.mark.asyncio
    async def test_returns_json_with_expected_keys(self):
        from gateway.tools import monitoring as m

        conn = MagicMock()
        conn.fetchval = AsyncMock(side_effect=[
            "PostgreSQL 16.2",  # version
            MagicMock(__str__=lambda self: "1 day, 0:00:00"),  # uptime
        ])
        conn.fetchrow = AsyncMock(side_effect=[
            _rec({"total": 5, "active": 1, "idle": 4, "idle_in_tx": 0,
                  "idle_in_tx_abort": 0, "max_conn": 100}),  # connections
            _rec({"hits": 9000, "reads": 1000, "hit_ratio": 90.0}),  # cache
            _rec({"commits": 100, "rollbacks": 2, "tup_returned": 5000,
                  "tup_fetched": 4000, "tup_inserted": 500, "tup_updated": 100,
                  "tup_deleted": 50, "conflicts": 0, "deadlocks": 0,
                  "size_bytes": 10485760, "size_pretty": "10 MB",
                  "numbackends": 5}),  # db_stats
            _rec({"checkpoints_timed": 10, "checkpoints_req": 1,
                  "buffers_checkpoint": 1000}),  # bgwriter
        ])
        # fetch is not called at the top level; WAL raises → None
        conn.fetch = AsyncMock(return_value=[])

        pool = _pool_with_conn(conn)

        with patch("gateway.monitoring.pool_manager.get_pool", return_value=pool):
            result = await m.handle("pg_overview", {})

        assert isinstance(result[0], TextContent)
        data = json.loads(result[0].text)
        assert "version" in data
        assert "uptime" in data
        assert "connections" in data
        assert "cache" in data
        assert "db_stats" in data

    @pytest.mark.asyncio
    async def test_returns_iserror_on_exception(self):
        from gateway.tools import monitoring as m

        with patch("gateway.monitoring.pool_manager.get_pool",
                   side_effect=RuntimeError("pool not found")):
            result = await m.handle("pg_overview", {})

        # isError path: CallToolResult has .isError attribute
        assert result.isError is True
        assert "pool not found" in result.content[0].text


# ---------------------------------------------------------------------------
# pg_activity
# ---------------------------------------------------------------------------

class TestPgActivity:
    @pytest.mark.asyncio
    async def test_empty_activity(self):
        from gateway.tools import monitoring as m

        conn = MagicMock()
        conn.fetch = AsyncMock(return_value=[])
        pool = _pool_with_conn(conn)

        with patch("gateway.monitoring.pool_manager.get_pool", return_value=pool):
            result = await m.handle("pg_activity", {})

        data = json.loads(result[0].text)
        assert data["queries"] == []
        assert data["locks"] == []

    @pytest.mark.asyncio
    async def test_with_active_query(self):
        from gateway.tools import monitoring as m

        q_rec = _rec({
            "pid": 42,
            "usename": "alice",
            "client_addr": "10.0.0.1",
            "datname": "mydb",
            "duration": MagicMock(__str__=lambda self: "0:00:05"),
            "state": "active",
            "wait_event_type": None,
            "wait_event": None,
            "query": "SELECT 1",
        })

        conn = MagicMock()
        # fetch called twice: queries, then locks
        conn.fetch = AsyncMock(side_effect=[[q_rec], []])
        pool = _pool_with_conn(conn)

        with patch("gateway.monitoring.pool_manager.get_pool", return_value=pool):
            result = await m.handle("pg_activity", {})

        data = json.loads(result[0].text)
        assert len(data["queries"]) == 1
        assert data["queries"][0]["pid"] == 42
        assert data["locks"] == []

    @pytest.mark.asyncio
    async def test_with_lock_block(self):
        from gateway.tools import monitoring as m

        lock_rec = _rec({
            "blocked_pid": 100,
            "blocked_user": "bob",
            "blocked_query": "UPDATE t SET x=1",
            "blocked_duration": MagicMock(__str__=lambda self: "0:00:30"),
            "blocking_pid": 99,
            "blocking_user": "alice",
            "blocking_query": "SELECT * FROM t FOR UPDATE",
        })

        conn = MagicMock()
        conn.fetch = AsyncMock(side_effect=[[], [lock_rec]])
        pool = _pool_with_conn(conn)

        with patch("gateway.monitoring.pool_manager.get_pool", return_value=pool):
            result = await m.handle("pg_activity", {})

        data = json.loads(result[0].text)
        assert len(data["locks"]) == 1
        assert data["locks"][0]["blocked_pid"] == 100
        assert data["locks"][0]["blocking_pid"] == 99


# ---------------------------------------------------------------------------
# pg_table_stats
# ---------------------------------------------------------------------------

class TestPgTableStats:
    @pytest.mark.asyncio
    async def test_empty_schema(self):
        from gateway.tools import monitoring as m

        pool = MagicMock()
        pool.fetch = AsyncMock(return_value=[])

        with patch("gateway.monitoring.pool_manager.get_pool", return_value=pool):
            result = await m.handle("pg_table_stats", {"schema": "public"})

        data = json.loads(result[0].text)
        assert data == []

    @pytest.mark.asyncio
    async def test_default_schema(self):
        from gateway.tools import monitoring as m

        pool = MagicMock()
        pool.fetch = AsyncMock(return_value=[])

        with patch("gateway.monitoring.pool_manager.get_pool", return_value=pool):
            await m.handle("pg_table_stats", {})

        # Verify pool.fetch was called (schema defaults to 'public')
        pool.fetch.assert_called_once()
        call_args = pool.fetch.call_args
        assert call_args[0][1] == "public"

    @pytest.mark.asyncio
    async def test_returns_table_data(self):
        from gateway.tools import monitoring as m

        tbl = _rec({
            "name": "orders",
            "type": "table",
            "total_bytes": 10485760,
            "total_size": "10 MB",
            "table_bytes": 8388608,
            "index_bytes": 2097152,
            "live_tuples": 10000,
            "dead_tuples": 100,
            "dead_pct": 1.0,
            "seq_scan": 50,
            "idx_scan": 9950,
            "inserts": 10000,
            "updates": 500,
            "deletes": 200,
            "last_vacuum": None,
            "last_autovacuum": "2024-01-01 00:00:00",
            "last_analyze": None,
            "last_autoanalyze": "2024-01-01 00:00:00",
            "vacuum_count": 0,
            "autovacuum_count": 3,
        })

        pool = MagicMock()
        pool.fetch = AsyncMock(return_value=[tbl])

        with patch("gateway.monitoring.pool_manager.get_pool", return_value=pool):
            result = await m.handle("pg_table_stats", {"schema": "myschema"})

        data = json.loads(result[0].text)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["name"] == "orders"
        assert data[0]["live_tuples"] == 10000


# ---------------------------------------------------------------------------
# pg_index_stats
# ---------------------------------------------------------------------------

class TestPgIndexStats:
    @pytest.mark.asyncio
    async def test_empty_schema(self):
        from gateway.tools import monitoring as m

        pool = MagicMock()
        pool.fetch = AsyncMock(return_value=[])

        with patch("gateway.monitoring.pool_manager.get_pool", return_value=pool):
            result = await m.handle("pg_index_stats", {})

        data = json.loads(result[0].text)
        assert data == []

    @pytest.mark.asyncio
    async def test_returns_index_data(self):
        from gateway.tools import monitoring as m

        idx = _rec({
            "table_name": "orders",
            "index_name": "orders_pkey",
            "scans": 9999,
            "tuples_read": 50000,
            "tuples_fetched": 49000,
            "size_bytes": 1048576,
            "size": "1 MB",
            "indexdef": "CREATE UNIQUE INDEX orders_pkey ON public.orders USING btree (id)",
        })

        pool = MagicMock()
        pool.fetch = AsyncMock(return_value=[idx])

        with patch("gateway.monitoring.pool_manager.get_pool", return_value=pool):
            result = await m.handle("pg_index_stats", {"schema": "public"})

        data = json.loads(result[0].text)
        assert len(data) == 1
        assert data[0]["index_name"] == "orders_pkey"
        assert data[0]["scans"] == 9999

    @pytest.mark.asyncio
    async def test_unused_index_has_zero_scans(self):
        from gateway.tools import monitoring as m

        unused = _rec({
            "table_name": "products",
            "index_name": "idx_products_old",
            "scans": 0,
            "tuples_read": 0,
            "tuples_fetched": 0,
            "size_bytes": 524288,
            "size": "512 kB",
            "indexdef": "CREATE INDEX idx_products_old ON public.products USING btree (sku)",
        })

        pool = MagicMock()
        pool.fetch = AsyncMock(return_value=[unused])

        with patch("gateway.monitoring.pool_manager.get_pool", return_value=pool):
            result = await m.handle("pg_index_stats", {"schema": "public"})

        data = json.loads(result[0].text)
        assert data[0]["scans"] == 0


# ---------------------------------------------------------------------------
# pg_replication
# ---------------------------------------------------------------------------

class TestPgReplication:
    @pytest.mark.asyncio
    async def test_no_replication(self):
        from gateway.tools import monitoring as m

        conn = MagicMock()
        conn.fetch = AsyncMock(return_value=[])
        pool = _pool_with_conn(conn)

        with patch("gateway.monitoring.pool_manager.get_pool", return_value=pool):
            result = await m.handle("pg_replication", {})

        data = json.loads(result[0].text)
        assert data["replicas"] == []
        assert data["slots"] == []

    @pytest.mark.asyncio
    async def test_with_replica(self):
        from gateway.tools import monitoring as m

        replica = _rec({
            "client_addr": "10.0.0.2",
            "application_name": "standby1",
            "state": "streaming",
            "sent_lsn": "0/5000000",
            "write_lsn": "0/5000000",
            "flush_lsn": "0/4FF0000",
            "replay_lsn": "0/4FE0000",
            "write_lag": "0:00:00.001",
            "flush_lag": "0:00:00.002",
            "replay_lag": "0:00:00.003",
            "replay_lag_bytes": 131072,
        })

        conn = MagicMock()
        conn.fetch = AsyncMock(side_effect=[[replica], []])
        pool = _pool_with_conn(conn)

        with patch("gateway.monitoring.pool_manager.get_pool", return_value=pool):
            result = await m.handle("pg_replication", {})

        data = json.loads(result[0].text)
        assert len(data["replicas"]) == 1
        assert data["replicas"][0]["application_name"] == "standby1"
        assert data["replicas"][0]["replay_lag_bytes"] == 131072

    @pytest.mark.asyncio
    async def test_with_replication_slot(self):
        from gateway.tools import monitoring as m

        slot = _rec({
            "slot_name": "logical_slot_1",
            "slot_type": "logical",
            "active": False,
            "retained_bytes": 5368709120,
            "retained_size": "5 GB",
        })

        conn = MagicMock()
        conn.fetch = AsyncMock(side_effect=[[], [slot]])
        pool = _pool_with_conn(conn)

        with patch("gateway.monitoring.pool_manager.get_pool", return_value=pool):
            result = await m.handle("pg_replication", {})

        data = json.loads(result[0].text)
        assert len(data["slots"]) == 1
        assert data["slots"][0]["slot_name"] == "logical_slot_1"
        assert data["slots"][0]["retained_size"] == "5 GB"


# ---------------------------------------------------------------------------
# pg_schemas
# ---------------------------------------------------------------------------

class TestPgSchemas:
    @pytest.mark.asyncio
    async def test_empty_db(self):
        from gateway.tools import monitoring as m

        pool = MagicMock()
        pool.fetch = AsyncMock(return_value=[])

        with patch("gateway.monitoring.pool_manager.get_pool", return_value=pool):
            result = await m.handle("pg_schemas", {})

        data = json.loads(result[0].text)
        assert data == []

    @pytest.mark.asyncio
    async def test_returns_schemas(self):
        from gateway.tools import monitoring as m

        schemas = [
            _rec({"name": "public", "tables": 10}),
            _rec({"name": "audit", "tables": 3}),
        ]

        pool = MagicMock()
        pool.fetch = AsyncMock(return_value=schemas)

        with patch("gateway.monitoring.pool_manager.get_pool", return_value=pool):
            result = await m.handle("pg_schemas", {})

        data = json.loads(result[0].text)
        assert len(data) == 2
        assert data[0]["name"] == "public"
        assert data[0]["tables"] == 10
        assert data[1]["name"] == "audit"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestMonitoringErrorHandling:
    @pytest.mark.asyncio
    async def test_unknown_tool_returns_message(self):
        from gateway.tools import monitoring as m

        pool = MagicMock()
        pool.fetch = AsyncMock(return_value=[])

        with patch("gateway.monitoring.pool_manager.get_pool", return_value=pool):
            result = await m.handle("nonexistent_monitoring_tool", {})

        assert "Unknown monitoring tool" in result[0].text

    @pytest.mark.asyncio
    async def test_db_error_returns_iserror(self):
        from gateway.tools import monitoring as m

        with patch("gateway.monitoring.pool_manager.get_pool",
                   side_effect=ConnectionError("DB unreachable")):
            result = await m.handle("pg_table_stats", {"schema": "public"})

        assert result.isError is True
        assert "DB unreachable" in result.content[0].text

    @pytest.mark.asyncio
    async def test_pg_activity_error(self):
        from gateway.tools import monitoring as m

        with patch("gateway.monitoring.pool_manager.get_pool",
                   side_effect=Exception("timeout")):
            result = await m.handle("pg_activity", {})

        assert result.isError is True

    @pytest.mark.asyncio
    async def test_pg_replication_error(self):
        from gateway.tools import monitoring as m

        with patch("gateway.monitoring.pool_manager.get_pool",
                   side_effect=Exception("connection refused")):
            result = await m.handle("pg_replication", {})

        assert result.isError is True
        assert "connection refused" in result.content[0].text

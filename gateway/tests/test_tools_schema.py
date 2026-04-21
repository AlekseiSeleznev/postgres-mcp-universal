"""Tests for gateway.tools.schema — list_schemas, list_tables, get_table_info, etc."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp.types import TextContent


def _make_record(**kwargs):
    """Make a mock asyncpg Record with dict-like access."""
    rec = MagicMock()
    rec.keys = MagicMock(return_value=list(kwargs.keys()))
    rec.__getitem__ = lambda self, k: kwargs[k]
    rec.__contains__ = lambda self, k: k in kwargs

    # Support r.get(key) pattern
    def _get(key, default=None):
        return kwargs.get(key, default)
    rec.get = _get

    # dict(r) support
    rec.items = lambda: kwargs.items()
    return rec


def _dict_record(d: dict):
    """Make a simple asyncpg-Record-like object from a dict."""
    class _Rec:
        def __getitem__(self, k):
            return d[k]
        def keys(self):
            return list(d.keys())
        def get(self, k, default=None):
            return d.get(k, default)
        def __contains__(self, k):
            return k in d
        def items(self):
            return d.items()
        def values(self):
            return d.values()
    return _Rec()


def _make_pool_with_fetch(records):
    """Create mock pool returning records from pool.fetch() and conn.fetch()."""
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=records)
    conn.fetchrow = AsyncMock(return_value=None)

    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=records)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    pool.acquire.return_value = cm

    return pool, conn


class TestListSchemas:
    """Tests for list_schemas tool."""

    @pytest.mark.asyncio
    async def test_list_schemas_returns_schema_names(self):
        from gateway.tools import schema as schema_mod

        records = [
            _dict_record({"schema_name": "public", "tables": 5}),
            _dict_record({"schema_name": "analytics", "tables": 2}),
        ]
        pool, conn = _make_pool_with_fetch(records)

        with patch.object(schema_mod.pool_manager, "get_pool", return_value=pool):
            result = await schema_mod.handle("list_schemas", {})

        text = result[0].text
        assert "public" in text
        assert "analytics" in text

    @pytest.mark.asyncio
    async def test_list_schemas_no_schemas_message(self):
        from gateway.tools import schema as schema_mod

        pool, conn = _make_pool_with_fetch([])

        with patch.object(schema_mod.pool_manager, "get_pool", return_value=pool):
            result = await schema_mod.handle("list_schemas", {})

        assert "No user schemas" in result[0].text

    @pytest.mark.asyncio
    async def test_list_schemas_ignores_compat_placeholder(self):
        from gateway.tools import schema as schema_mod

        records = [_dict_record({"schema_name": "public", "tables": 5})]
        pool, conn = _make_pool_with_fetch(records)

        with patch.object(schema_mod.pool_manager, "get_pool", return_value=pool):
            result = await schema_mod.handle("list_schemas", {"_compat": True})

        assert "public" in result[0].text


class TestListTables:
    """Tests for list_tables tool."""

    @pytest.mark.asyncio
    async def test_list_tables_returns_table_names(self):
        from gateway.tools import schema as schema_mod

        records = [
            _dict_record({"name": "users", "type": "table", "approx_rows": 1000, "total_size": "8 kB"}),
            _dict_record({"name": "orders", "type": "table", "approx_rows": 5000, "total_size": "40 kB"}),
        ]
        pool, conn = _make_pool_with_fetch(records)

        with patch.object(schema_mod.pool_manager, "get_pool", return_value=pool):
            result = await schema_mod.handle("list_tables", {"schema": "public"})

        text = result[0].text
        assert "users" in text
        assert "orders" in text

    @pytest.mark.asyncio
    async def test_list_tables_empty_schema(self):
        from gateway.tools import schema as schema_mod

        pool, conn = _make_pool_with_fetch([])

        with patch.object(schema_mod.pool_manager, "get_pool", return_value=pool):
            result = await schema_mod.handle("list_tables", {"schema": "empty_schema"})

        assert "No tables" in result[0].text

    @pytest.mark.asyncio
    async def test_list_tables_default_schema_is_public(self):
        from gateway.tools import schema as schema_mod

        pool, conn = _make_pool_with_fetch([])

        with patch.object(schema_mod.pool_manager, "get_pool", return_value=pool):
            await schema_mod.handle("list_tables", {})

        # Should query with 'public' as default
        call_args = pool.fetch.call_args
        assert "public" in call_args[0]


class TestGetTableInfo:
    """Tests for get_table_info tool."""

    @pytest.mark.asyncio
    async def test_get_table_info_returns_json(self):
        from gateway.tools import schema as schema_mod

        col_record = _dict_record({
            "column_name": "id",
            "data_type": "integer",
            "is_nullable": "NO",
            "column_default": None,
            "character_maximum_length": None,
            "numeric_precision": 32,
            "numeric_scale": 0,
        })
        pk_record = _dict_record({"attname": "id"})
        stat_record = _dict_record({
            "approx_rows": 100,
            "total_size": "8 kB",
            "table_size": "4 kB",
            "indexes_size": "4 kB",
        })

        conn = MagicMock()
        conn.fetch = AsyncMock(side_effect=[
            [col_record],    # columns
            [pk_record],     # primary key
            [],              # foreign keys
            [],              # indexes
        ])
        conn.fetchrow = AsyncMock(return_value=stat_record)

        pool = MagicMock()
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__ = AsyncMock(return_value=False)
        pool.acquire.return_value = cm

        with patch.object(schema_mod.pool_manager, "get_pool", return_value=pool):
            result = await schema_mod.handle("get_table_info", {"table": "users", "schema": "public"})

        data = json.loads(result[0].text)
        assert "columns" in data
        assert "primary_key" in data
        assert "foreign_keys" in data
        assert "indexes" in data
        assert data["primary_key"] == ["id"]


class TestListIndexes:
    """Tests for list_indexes tool."""

    @pytest.mark.asyncio
    async def test_list_indexes_for_table(self):
        from gateway.tools import schema as schema_mod

        idx_rec = _dict_record({
            "indexname": "users_pkey",
            "indexdef": "CREATE UNIQUE INDEX users_pkey ON public.users USING btree (id)",
            "size": "8 kB",
            "idx_scan": 100,
            "idx_tup_read": 500,
            "idx_tup_fetch": 400,
        })

        pool, conn = _make_pool_with_fetch([idx_rec])

        with patch.object(schema_mod.pool_manager, "get_pool", return_value=pool):
            result = await schema_mod.handle("list_indexes", {"table": "users", "schema": "public"})

        text = result[0].text
        assert "users_pkey" in text

    @pytest.mark.asyncio
    async def test_list_indexes_no_table_lists_all_schema(self):
        from gateway.tools import schema as schema_mod

        pool, conn = _make_pool_with_fetch([])

        with patch.object(schema_mod.pool_manager, "get_pool", return_value=pool):
            result = await schema_mod.handle("list_indexes", {"schema": "public"})

        assert "No indexes" in result[0].text

    @pytest.mark.asyncio
    async def test_list_indexes_empty_returns_message(self):
        from gateway.tools import schema as schema_mod

        pool, conn = _make_pool_with_fetch([])

        with patch.object(schema_mod.pool_manager, "get_pool", return_value=pool):
            result = await schema_mod.handle("list_indexes", {})

        assert "No indexes" in result[0].text


class TestListFunctions:
    """Tests for list_functions tool."""

    @pytest.mark.asyncio
    async def test_list_functions_returns_function_info(self):
        from gateway.tools import schema as schema_mod

        func_rec = _dict_record({
            "name": "calculate_discount",
            "arguments": "price numeric, pct numeric",
            "kind": "function",
            "return_type": "numeric",
        })
        pool, conn = _make_pool_with_fetch([func_rec])

        with patch.object(schema_mod.pool_manager, "get_pool", return_value=pool):
            result = await schema_mod.handle("list_functions", {"schema": "public"})

        text = result[0].text
        assert "calculate_discount" in text

    @pytest.mark.asyncio
    async def test_list_functions_empty_schema(self):
        from gateway.tools import schema as schema_mod

        pool, conn = _make_pool_with_fetch([])

        with patch.object(schema_mod.pool_manager, "get_pool", return_value=pool):
            result = await schema_mod.handle("list_functions", {"schema": "empty"})

        assert "No functions" in result[0].text

    @pytest.mark.asyncio
    async def test_unknown_schema_tool_returns_error(self):
        from gateway.tools import schema as schema_mod

        pool, conn = _make_pool_with_fetch([])

        with patch.object(schema_mod.pool_manager, "get_pool", return_value=pool):
            result = await schema_mod.handle("unknown_schema_tool", {})

        assert "Unknown" in result[0].text

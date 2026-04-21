"""Tests for gateway.tools.query — execute_sql, explain_query."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp.types import TextContent


def _make_mock_record(keys, values):
    """Create a mock asyncpg Record-like object."""
    rec = MagicMock()
    rec.keys.return_value = keys
    rec.values.return_value = values
    # Support indexing by position
    rec.__getitem__ = lambda self, i: dict(zip(keys, values))[i] if isinstance(i, str) else values[i]
    return rec


def _make_pool_with_fetch(records):
    """Create a mock pool that returns given records from fetch()."""
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=records)
    conn.prepare = AsyncMock()

    pool = MagicMock()

    # Use async context manager for pool.acquire()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    pool.acquire.return_value = cm

    pool.fetch = AsyncMock(return_value=records)
    return pool, conn


class TestIsReadOnly:
    """Tests for the _is_read_only helper."""

    def test_select_is_readonly(self):
        from gateway.tools.query import _is_read_only
        assert _is_read_only("SELECT * FROM users") is True

    def test_select_case_insensitive(self):
        from gateway.tools.query import _is_read_only
        assert _is_read_only("select id from foo") is True

    def test_explain_is_readonly(self):
        from gateway.tools.query import _is_read_only
        assert _is_read_only("EXPLAIN SELECT 1") is True

    def test_show_is_readonly(self):
        from gateway.tools.query import _is_read_only
        assert _is_read_only("SHOW search_path") is True

    def test_with_cte_is_readonly(self):
        from gateway.tools.query import _is_read_only
        assert _is_read_only("WITH cte AS (SELECT 1) SELECT * FROM cte") is True

    def test_values_is_readonly(self):
        from gateway.tools.query import _is_read_only
        assert _is_read_only("VALUES (1, 2, 3)") is True

    def test_insert_is_not_readonly(self):
        from gateway.tools.query import _is_read_only
        assert _is_read_only("INSERT INTO foo VALUES (1)") is False

    def test_update_is_not_readonly(self):
        from gateway.tools.query import _is_read_only
        assert _is_read_only("UPDATE foo SET bar=1") is False

    def test_delete_is_not_readonly(self):
        from gateway.tools.query import _is_read_only
        assert _is_read_only("DELETE FROM foo") is False

    def test_drop_is_not_readonly(self):
        from gateway.tools.query import _is_read_only
        assert _is_read_only("DROP TABLE foo") is False

    def test_single_line_comment_stripped(self):
        from gateway.tools.query import _is_read_only
        sql = "-- this is a comment\nSELECT 1"
        assert _is_read_only(sql) is True

    def test_block_comment_stripped(self):
        from gateway.tools.query import _is_read_only
        sql = "/* comment */ SELECT 1"
        assert _is_read_only(sql) is True

    def test_insert_after_block_comment_not_readonly(self):
        from gateway.tools.query import _is_read_only
        sql = "/* comment */ INSERT INTO foo VALUES (1)"
        assert _is_read_only(sql) is False

    def test_cte_with_delete_not_readonly(self):
        from gateway.tools.query import _is_read_only
        sql = "WITH deleted AS (DELETE FROM users RETURNING *) SELECT * FROM deleted"
        assert _is_read_only(sql) is False

    def test_cte_with_update_not_readonly(self):
        from gateway.tools.query import _is_read_only
        sql = "WITH upd AS (UPDATE users SET active=false RETURNING *) SELECT * FROM upd"
        assert _is_read_only(sql) is False

    def test_cte_with_insert_not_readonly(self):
        from gateway.tools.query import _is_read_only
        sql = "WITH ins AS (INSERT INTO logs VALUES (1) RETURNING *) SELECT * FROM ins"
        assert _is_read_only(sql) is False

    def test_cte_select_only_is_readonly(self):
        from gateway.tools.query import _is_read_only
        sql = "WITH cte AS (SELECT id FROM users) SELECT * FROM cte"
        assert _is_read_only(sql) is True

    def test_cte_with_quoted_keyword_is_readonly(self):
        """Write keyword inside a string literal should not trigger false positive."""
        from gateway.tools.query import _is_read_only
        sql = "WITH cte AS (SELECT 'delete this' AS note FROM t) SELECT * FROM cte"
        assert _is_read_only(sql) is True


class TestFormatTable:
    """Tests for _format_table helper."""

    def test_empty_rows(self):
        from gateway.tools.query import _format_table
        result = _format_table(["id", "name"], [])
        assert "0 rows" in result
        assert "id" in result
        assert "name" in result

    def test_single_row(self):
        from gateway.tools.query import _format_table
        result = _format_table(["id", "name"], [(1, "Alice")])
        assert "1 row" in result
        assert "Alice" in result
        assert "id" in result

    def test_multiple_rows(self):
        from gateway.tools.query import _format_table
        result = _format_table(["id"], [(1,), (2,), (3,)])
        assert "3 rows" in result

    def test_columns_aligned(self):
        from gateway.tools.query import _format_table
        result = _format_table(["short", "longer_column"], [(1, "x"), (2, "yyyy")])
        lines = result.split("\n")
        # Header and separator should be present
        assert len(lines) >= 3

    def test_separator_present(self):
        from gateway.tools.query import _format_table
        result = _format_table(["a", "b"], [(1, 2)])
        assert "-" in result


class TestExecuteSql:
    """Tests for execute_sql via handle()."""

    @pytest.mark.asyncio
    async def test_execute_sql_returns_formatted_table(self):
        from gateway.tools import query as query_mod

        rec = _make_mock_record(["id", "name"], [1, "Alice"])
        pool, conn = _make_pool_with_fetch([rec])

        with patch.object(query_mod.pool_manager, "get_pool", return_value=pool), \
             patch.object(query_mod.pool_manager, "get_active_db", return_value="testdb"), \
             patch.object(query_mod.registry, "get", return_value=None):
            result = await query_mod.handle("execute_sql", {"query": "SELECT id, name FROM users"})

        assert len(result) == 1
        text = result[0].text
        assert "Alice" in text
        assert "Time:" in text

    @pytest.mark.asyncio
    async def test_execute_sql_empty_result(self):
        from gateway.tools import query as query_mod

        pool, conn = _make_pool_with_fetch([])

        with patch.object(query_mod.pool_manager, "get_pool", return_value=pool), \
             patch.object(query_mod.pool_manager, "get_active_db", return_value="testdb"), \
             patch.object(query_mod.registry, "get", return_value=None):
            result = await query_mod.handle("execute_sql", {"query": "SELECT 1 WHERE false"})

        assert "0 rows" in result[0].text

    @pytest.mark.asyncio
    async def test_execute_sql_restricted_mode_blocks_write(self):
        from gateway.tools import query as query_mod
        from gateway.db_registry import DatabaseInfo

        db = DatabaseInfo(name="testdb", uri="x", access_mode="restricted")
        pool, conn = _make_pool_with_fetch([])

        with patch.object(query_mod.pool_manager, "get_pool", return_value=pool), \
             patch.object(query_mod.pool_manager, "get_active_db", return_value="testdb"), \
             patch.object(query_mod.registry, "get", return_value=db):
            result = await query_mod.handle("execute_sql", {"query": "INSERT INTO foo VALUES (1)"})

        assert "DENIED" in result[0].text
        assert "restricted" in result[0].text

    @pytest.mark.asyncio
    async def test_execute_sql_restricted_mode_allows_select(self):
        from gateway.tools import query as query_mod
        from gateway.db_registry import DatabaseInfo

        db = DatabaseInfo(name="testdb", uri="x", access_mode="restricted")
        rec = _make_mock_record(["id"], [1])
        pool, conn = _make_pool_with_fetch([rec])

        with patch.object(query_mod.pool_manager, "get_pool", return_value=pool), \
             patch.object(query_mod.pool_manager, "get_active_db", return_value="testdb"), \
             patch.object(query_mod.registry, "get", return_value=db):
            result = await query_mod.handle("execute_sql", {"query": "SELECT 1"})

        assert "DENIED" not in result[0].text

    @pytest.mark.asyncio
    async def test_execute_sql_with_params(self):
        from gateway.tools import query as query_mod

        rec = _make_mock_record(["id"], [42])

        conn = MagicMock()
        stmt = MagicMock()
        stmt.fetch = AsyncMock(return_value=[rec])
        conn.prepare = AsyncMock(return_value=stmt)

        pool = MagicMock()
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__ = AsyncMock(return_value=False)
        pool.acquire.return_value = cm

        with patch.object(query_mod.pool_manager, "get_pool", return_value=pool), \
             patch.object(query_mod.pool_manager, "get_active_db", return_value="testdb"), \
             patch.object(query_mod.registry, "get", return_value=None):
            result = await query_mod.handle(
                "execute_sql",
                {"query": "SELECT * FROM foo WHERE id = $1", "params": [42]}
            )

        conn.prepare.assert_awaited_once()
        stmt.fetch.assert_awaited_once_with(42)

    @pytest.mark.asyncio
    async def test_execute_sql_truncates_large_result(self):
        from gateway.tools import query as query_mod

        # Generate 501 records (more than MAX_ROWS=500)
        records = [_make_mock_record(["n"], [i]) for i in range(501)]
        pool, conn = _make_pool_with_fetch(records)

        with patch.object(query_mod.pool_manager, "get_pool", return_value=pool), \
             patch.object(query_mod.pool_manager, "get_active_db", return_value="testdb"), \
             patch.object(query_mod.registry, "get", return_value=None):
            result = await query_mod.handle("execute_sql", {"query": "SELECT n FROM nums"})

        assert "truncated" in result[0].text
        assert "501" in result[0].text


class TestExplainQuery:
    """Tests for explain_query via handle()."""

    @pytest.mark.asyncio
    async def test_explain_query_returns_json_plan(self):
        from gateway.tools import query as query_mod

        plan_data = [{"Plan": {"Node Type": "Seq Scan"}}]
        rec = MagicMock()
        rec.__getitem__ = MagicMock(return_value=json.dumps(plan_data))

        pool, conn = _make_pool_with_fetch([rec])

        with patch.object(query_mod.pool_manager, "get_pool", return_value=pool), \
             patch.object(query_mod.pool_manager, "get_active_db", return_value="testdb"), \
             patch.object(query_mod.registry, "get", return_value=None):
            result = await query_mod.handle("explain_query", {"query": "SELECT * FROM users"})

        assert len(result) == 1
        # Should be valid JSON output
        parsed = json.loads(result[0].text)
        assert isinstance(parsed, list)

    @pytest.mark.asyncio
    async def test_explain_query_analyze_true_includes_analyze(self):
        from gateway.tools import query as query_mod

        rec = MagicMock()
        rec.__getitem__ = MagicMock(return_value="{}")

        pool, conn = _make_pool_with_fetch([rec])

        with patch.object(query_mod.pool_manager, "get_pool", return_value=pool), \
             patch.object(query_mod.pool_manager, "get_active_db", return_value="testdb"), \
             patch.object(query_mod.registry, "get", return_value=None):
            await query_mod.handle("explain_query", {"query": "SELECT 1", "analyze": True})

        # Verify ANALYZE was in the query sent
        call_args = conn.fetch.call_args[0][0]
        assert "ANALYZE" in call_args

    @pytest.mark.asyncio
    async def test_explain_query_analyze_false_omits_analyze(self):
        from gateway.tools import query as query_mod

        rec = MagicMock()
        rec.__getitem__ = MagicMock(return_value="{}")

        pool, conn = _make_pool_with_fetch([rec])

        with patch.object(query_mod.pool_manager, "get_pool", return_value=pool), \
             patch.object(query_mod.pool_manager, "get_active_db", return_value="testdb"), \
             patch.object(query_mod.registry, "get", return_value=None):
            await query_mod.handle("explain_query", {"query": "SELECT 1", "analyze": False})

        call_args = conn.fetch.call_args[0][0]
        assert "ANALYZE" not in call_args

    @pytest.mark.asyncio
    async def test_explain_query_restricted_mode_blocks_analyze(self):
        from gateway.tools import query as query_mod
        from gateway.db_registry import DatabaseInfo

        db = DatabaseInfo(name="testdb", uri="x", access_mode="restricted")
        rec = MagicMock()
        rec.__getitem__ = MagicMock(return_value="{}")
        pool, conn = _make_pool_with_fetch([rec])

        with patch.object(query_mod.pool_manager, "get_pool", return_value=pool), \
             patch.object(query_mod.pool_manager, "get_active_db", return_value="testdb"), \
             patch.object(query_mod.registry, "get", return_value=db):
            result = await query_mod.handle("explain_query", {"query": "SELECT 1", "analyze": True})

        assert "DENIED" in result[0].text
        assert "ANALYZE is not allowed" in result[0].text
        conn.fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_explain_query_restricted_mode_blocks_write_target(self):
        from gateway.tools import query as query_mod
        from gateway.db_registry import DatabaseInfo

        db = DatabaseInfo(name="testdb", uri="x", access_mode="restricted")
        rec = MagicMock()
        rec.__getitem__ = MagicMock(return_value="{}")
        pool, conn = _make_pool_with_fetch([rec])

        with patch.object(query_mod.pool_manager, "get_pool", return_value=pool), \
             patch.object(query_mod.pool_manager, "get_active_db", return_value="testdb"), \
             patch.object(query_mod.registry, "get", return_value=db):
            result = await query_mod.handle("explain_query", {"query": "DELETE FROM users", "analyze": False})

        assert "DENIED" in result[0].text
        assert "target query must be read-only" in result[0].text

    @pytest.mark.asyncio
    async def test_explain_query_restricted_mode_allows_read_only_target_without_analyze(self):
        import gateway.tools.query as query_mod

        pool = MagicMock()
        conn = MagicMock()
        conn.fetch = AsyncMock(return_value=[[{"Plan": {"Node Type": "Seq Scan"}}]])
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        db = MagicMock()
        db.access_mode = "restricted"

        with patch.object(query_mod.pool_manager, "get_pool", return_value=pool), \
             patch.object(query_mod.pool_manager, "get_active_db", return_value="demo"), \
             patch.object(query_mod.registry, "get", return_value=db):
            result = await query_mod.handle("explain_query", {"query": "SELECT 1", "analyze": False})

        assert "Seq Scan" in result[0].text

    @pytest.mark.asyncio
    async def test_unknown_query_tool_returns_error(self):
        from gateway.tools import query as query_mod

        pool, conn = _make_pool_with_fetch([])

        with patch.object(query_mod.pool_manager, "get_pool", return_value=pool), \
             patch.object(query_mod.pool_manager, "get_active_db", return_value="testdb"), \
             patch.object(query_mod.registry, "get", return_value=None):
            result = await query_mod.handle("unknown_tool", {})

        assert "Unknown" in result[0].text

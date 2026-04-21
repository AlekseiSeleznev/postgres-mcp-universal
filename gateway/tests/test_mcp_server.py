"""Tests for gateway.mcp_server — tool dispatch, list_tools, call_tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp.types import TextContent, Tool


class TestAllTools:
    """Verify all expected tools are registered."""

    def test_all_tools_returns_list(self):
        from gateway.mcp_server import _all_tools
        tools = _all_tools()
        assert isinstance(tools, list)
        assert len(tools) > 0

    def test_all_tools_are_tool_instances(self):
        from gateway.mcp_server import _all_tools
        for t in _all_tools():
            assert isinstance(t, Tool)

    def test_expected_tools_present(self):
        from gateway.mcp_server import _all_tools
        names = {t.name for t in _all_tools()}
        expected = {
            "execute_sql",
            "explain_query",
            "list_schemas",
            "list_tables",
            "get_table_info",
            "list_indexes",
            "list_functions",
            "db_health",
            "active_queries",
            "table_bloat",
            "vacuum_stats",
            "lock_info",
            "connect_database",
            "disconnect_database",
            "switch_database",
            "list_databases",
            "get_server_status",
        }
        assert expected.issubset(names)

    def test_no_duplicate_tool_names(self):
        from gateway.mcp_server import _all_tools
        names = [t.name for t in _all_tools()]
        assert len(names) == len(set(names)), "Duplicate tool names found"

    def test_zero_arg_tools_publish_compat_placeholder_schema(self):
        from gateway.mcp_server import _all_tools

        zero_arg_names = {
            "list_databases",
            "get_server_status",
            "list_schemas",
            "db_health",
            "lock_info",
            "pg_overview",
            "pg_activity",
            "pg_replication",
            "pg_schemas",
        }
        tools = {t.name: t for t in _all_tools()}

        for name in zero_arg_names:
            schema = tools[name].inputSchema
            assert schema["type"] == "object"
            assert "_compat" in schema["properties"]
            assert schema["properties"]["_compat"]["type"] == "boolean"

    def test_initialization_options_publish_project_version(self):
        from gateway import __version__
        from gateway.mcp_server import server

        opts = server.create_initialization_options()

        assert opts.server_version == __version__


class TestToolDispatch:
    """Verify _TOOL_DISPATCH maps correctly."""

    def test_dispatch_keys_match_tool_names(self):
        from gateway.mcp_server import _TOOL_DISPATCH, _all_tools
        tool_names = {t.name for t in _all_tools()}
        assert set(_TOOL_DISPATCH.keys()) == tool_names

    def test_dispatch_values_are_modules(self):
        from gateway.mcp_server import _TOOL_DISPATCH
        import types
        for name, mod in _TOOL_DISPATCH.items():
            assert hasattr(mod, "handle"), f"Module for {name} has no handle()"


class TestCallTool:
    """Tests for the call_tool handler."""

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error_text(self):
        from gateway.mcp_server import call_tool
        from mcp.types import CallToolResult

        result = await call_tool("nonexistent_tool", {})
        # Per MCP spec, unknown tool returns CallToolResult with isError=True
        assert isinstance(result, CallToolResult)
        assert result.isError is True
        assert "Unknown tool" in result.content[0].text

    @pytest.mark.asyncio
    async def test_call_tool_dispatches_to_correct_module(self):
        from gateway.mcp_server import call_tool
        from gateway import mcp_server

        mock_result = [TextContent(type="text", text="mock result")]
        mock_handle = AsyncMock(return_value=mock_result)

        with patch.dict(mcp_server._TOOL_DISPATCH, {"execute_sql": MagicMock(handle=mock_handle)}):
            result = await call_tool("execute_sql", {"query": "SELECT 1"})

        mock_handle.assert_awaited_once_with("execute_sql", {"query": "SELECT 1"}, session_id=None)
        assert result == mock_result

    @pytest.mark.asyncio
    async def test_call_tool_catches_exceptions(self):
        from gateway.mcp_server import call_tool
        from gateway import mcp_server
        from mcp.types import CallToolResult

        mock_handle = AsyncMock(side_effect=RuntimeError("DB connection failed"))

        with patch.dict(mcp_server._TOOL_DISPATCH, {"execute_sql": MagicMock(handle=mock_handle)}):
            result = await call_tool("execute_sql", {"query": "SELECT 1"})

        # Per MCP spec: exceptions should return CallToolResult with isError=True
        assert isinstance(result, CallToolResult)
        assert result.isError is True
        assert "Error in execute_sql" in result.content[0].text
        assert "DB connection failed" in result.content[0].text

    @pytest.mark.asyncio
    async def test_call_tool_passes_session_id(self):
        from gateway.mcp_server import call_tool
        from gateway import mcp_server

        mock_result = [TextContent(type="text", text="ok")]
        mock_handle = AsyncMock(return_value=mock_result)

        with patch.dict(mcp_server._TOOL_DISPATCH, {"execute_sql": MagicMock(handle=mock_handle)}), \
             patch("gateway.mcp_server._get_session_id", return_value="session-xyz"):
            await call_tool("execute_sql", {"query": "SELECT 1"})

        mock_handle.assert_awaited_once_with("execute_sql", {"query": "SELECT 1"}, session_id="session-xyz")


class TestGetSessionId:
    """Tests for _get_session_id helper."""

    def test_returns_none_when_no_context(self):
        from gateway.mcp_server import _get_session_id
        # No request context active — should return None gracefully
        result = _get_session_id()
        assert result is None

    def test_returns_none_on_import_error(self):
        from gateway.mcp_server import _get_session_id
        with patch("gateway.mcp_server._get_session_id", return_value=None):
            result = _get_session_id()
        assert result is None


class TestListTools:
    """Tests for list_tools handler (registered via decorator)."""

    @pytest.mark.asyncio
    async def test_list_tools_returns_all(self):
        from gateway.mcp_server import list_tools, _all_tools
        tools = await list_tools()
        expected_count = len(_all_tools())
        assert len(tools) == expected_count

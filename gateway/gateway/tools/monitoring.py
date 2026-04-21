"""Monitoring tools — rich PostgreSQL metrics exposed as MCP tools."""

from __future__ import annotations

import json

from mcp.types import CallToolResult, TextContent, Tool

from gateway import monitoring as mon
from gateway.tools._compat_schema import compat_empty_schema

TOOLS = [
    Tool(
        name="pg_overview",
        description=(
            "Top-level PostgreSQL server metrics: version, uptime, connection counts, "
            "buffer cache hit ratio, database statistics (commits, rollbacks, tuple ops, "
            "deadlocks, conflicts), checkpoint stats, and WAL stats (PG14+). "
            "Use as a quick health snapshot before diving deeper."
        ),
        inputSchema=compat_empty_schema(),
    ),
    Tool(
        name="pg_activity",
        description=(
            "Current backend activity: all client queries with PID, user, client address, "
            "duration, state (active/idle/idle-in-transaction), wait events. "
            "Also returns blocked/blocking lock pairs with queries. "
            "Use when investigating slow or stuck sessions."
        ),
        inputSchema=compat_empty_schema(),
    ),
    Tool(
        name="pg_table_stats",
        description=(
            "Per-table statistics for a schema: size (table + indexes), live/dead tuple counts, "
            "dead tuple percentage, sequential vs index scan counts, insert/update/delete counts, "
            "vacuum and analyze timestamps. "
            "Use to find tables needing vacuuming or lacking indexes."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "schema": {
                    "type": "string",
                    "description": "Schema name. Default: 'public'",
                },
            },
        },
    ),
    Tool(
        name="pg_index_stats",
        description=(
            "Index usage statistics for a schema: scan count, tuples read/fetched, index size, "
            "and the index definition. Ordered by scan count ascending so unused indexes appear "
            "first. Use to identify unused or redundant indexes that waste write overhead."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "schema": {
                    "type": "string",
                    "description": "Schema name. Default: 'public'",
                },
            },
        },
    ),
    Tool(
        name="pg_replication",
        description=(
            "Replication status: connected standbys with LSN positions, write/flush/replay lag "
            "(time and bytes), and all replication slots with retained WAL size. "
            "Returns empty lists on a standalone server. "
            "Use to monitor replication lag and detect stuck slots."
        ),
        inputSchema=compat_empty_schema(),
    ),
    Tool(
        name="pg_schemas",
        description=(
            "List all user-defined schemas in the active database with their table counts. "
            "Excludes system schemas (pg_catalog, information_schema). "
            "Use to discover available schemas before exploring tables."
        ),
        inputSchema=compat_empty_schema(),
    ),
]


async def handle(name: str, arguments: dict, session_id: str | None = None) -> list[TextContent]:
    try:
        if name == "pg_overview":
            result = await mon.get_overview(session_id=session_id)
            return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

        if name == "pg_activity":
            result = await mon.get_activity(session_id=session_id)
            return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

        if name == "pg_table_stats":
            schema = arguments.get("schema", "public")
            result = await mon.get_tables_stats(schema=schema, session_id=session_id)
            return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

        if name == "pg_index_stats":
            schema = arguments.get("schema", "public")
            result = await mon.get_indexes_stats(schema=schema, session_id=session_id)
            return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

        if name == "pg_replication":
            result = await mon.get_replication(session_id=session_id)
            return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

        if name == "pg_schemas":
            result = await mon.get_schemas(session_id=session_id)
            return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    except Exception as e:
        return CallToolResult(
            isError=True,
            content=[TextContent(type="text", text=f"Error in {name}: {e}")],
        )

    return [TextContent(type="text", text=f"Unknown monitoring tool: {name}")]

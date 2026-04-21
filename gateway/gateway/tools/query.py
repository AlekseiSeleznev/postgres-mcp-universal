"""Query tools — execute SQL, explain queries."""

from __future__ import annotations

import json
import time
import logging

from mcp.types import TextContent, Tool

from gateway.config import settings
from gateway.db_registry import registry
from gateway.pg_pool import pool_manager
from gateway.tools.query_service import (
    format_query_result_text,
    format_table_text,
    is_read_only_sql,
    parse_explain_plan,
)

log = logging.getLogger(__name__)

TOOLS = [
    Tool(
        name="execute_sql",
        description=(
            "Execute a SQL query against the active PostgreSQL database. "
            "In restricted mode only SELECT/EXPLAIN/SHOW/WITH are allowed. "
            "Returns results as a formatted table (up to 500 rows)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "SQL query to execute"},
                "params": {
                    "type": "array",
                    "items": {},
                    "description": "Optional positional parameters ($1, $2, ...) for the query",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="explain_query",
        description=(
            "Run EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) on a query. "
            "Returns the query plan with timing and buffer information. "
            "WARNING: EXPLAIN ANALYZE actually executes the query!"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "SQL query to explain"},
                "analyze": {
                    "type": "boolean",
                    "description": "Run EXPLAIN ANALYZE (actually executes the query). Default: true",
                },
            },
            "required": ["query"],
        },
    ),
]

READ_ONLY_PREFIXES = ("select", "explain", "show", "with", "values", "table")
WRITE_KEYWORDS = {"insert", "update", "delete", "merge", "truncate", "drop", "alter", "create", "grant", "revoke"}
MAX_ROWS = 500


def _is_read_only(sql: str) -> bool:
    return is_read_only_sql(sql, READ_ONLY_PREFIXES, WRITE_KEYWORDS)


def _format_table(columns: list[str], rows: list[tuple]) -> str:
    return format_table_text(columns, rows)


async def handle(name: str, arguments: dict, session_id: str | None = None) -> list[TextContent]:
    pool = pool_manager.get_pool(session_id)
    db_name = pool_manager.get_active_db(session_id)
    db = registry.get(db_name)

    if name == "execute_sql":
        query = arguments["query"]
        params = arguments.get("params")

        # Check access mode
        if db and db.access_mode == "restricted" and not _is_read_only(query):
            return [TextContent(
                type="text",
                text=f"DENIED: Database '{db_name}' is in restricted (read-only) mode. Only SELECT/EXPLAIN/SHOW/WITH queries are allowed.",
            )]

        t0 = time.perf_counter()
        async with pool.acquire() as conn:
            if params:
                stmt = await conn.prepare(query)
                records = await stmt.fetch(*params)
            else:
                records = await conn.fetch(query)

        elapsed = time.perf_counter() - t0

        return [TextContent(type="text", text=format_query_result_text(records, elapsed, MAX_ROWS))]

    if name == "explain_query":
        query = arguments["query"]
        analyze = arguments.get("analyze", True)

        if db and db.access_mode == "restricted":
            if analyze:
                return [TextContent(
                    type="text",
                    text=(
                        f"DENIED: Database '{db_name}' is in restricted (read-only) mode. "
                        "EXPLAIN ANALYZE is not allowed."
                    ),
                )]
            if not _is_read_only(query):
                return [TextContent(
                    type="text",
                    text=(
                        f"DENIED: Database '{db_name}' is in restricted (read-only) mode. "
                        "EXPLAIN target query must be read-only."
                    ),
                )]

        explain_prefix = "EXPLAIN (FORMAT JSON, BUFFERS"
        if analyze:
            explain_prefix += ", ANALYZE"
        explain_prefix += ") "

        async with pool.acquire() as conn:
            records = await conn.fetch(explain_prefix + query)

        plan = parse_explain_plan(records[0][0] if records else "{}")

        return [TextContent(type="text", text=json.dumps(plan, indent=2, ensure_ascii=False))]

    return [TextContent(type="text", text=f"Unknown query tool: {name}")]

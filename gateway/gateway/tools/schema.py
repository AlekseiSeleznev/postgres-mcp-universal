"""Schema tools — explore database structure."""

from __future__ import annotations

import json

from mcp.types import TextContent, Tool

from gateway.pg_pool import pool_manager
from gateway.tools._compat_schema import compat_empty_schema
from gateway.tools.schema_service import (
    build_table_info_payload,
    render_functions,
    render_indexes,
    render_schemas,
    render_tables,
)

TOOLS = [
    Tool(
        name="list_schemas",
        description="List all schemas in the active database.",
        inputSchema=compat_empty_schema(),
    ),
    Tool(
        name="list_tables",
        description="List tables and views in a schema with row counts and sizes.",
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
        name="get_table_info",
        description="Get detailed table information: columns, types, constraints, indexes, foreign keys.",
        inputSchema={
            "type": "object",
            "properties": {
                "table": {"type": "string", "description": "Table name"},
                "schema": {"type": "string", "description": "Schema name. Default: 'public'"},
            },
            "required": ["table"],
        },
    ),
    Tool(
        name="list_indexes",
        description="List indexes for a table or entire schema.",
        inputSchema={
            "type": "object",
            "properties": {
                "table": {"type": "string", "description": "Table name (optional, omit for all tables in schema)"},
                "schema": {"type": "string", "description": "Schema name. Default: 'public'"},
            },
        },
    ),
    Tool(
        name="list_functions",
        description="List user-defined functions and procedures in a schema.",
        inputSchema={
            "type": "object",
            "properties": {
                "schema": {"type": "string", "description": "Schema name. Default: 'public'"},
            },
        },
    ),
]


async def handle(name: str, arguments: dict, session_id: str | None = None) -> list[TextContent]:
    pool = pool_manager.get_pool(session_id)

    if name == "list_schemas":
        rows = await pool.fetch("""
            SELECT schema_name,
                   (SELECT count(*) FROM information_schema.tables t
                    WHERE t.table_schema = s.schema_name) AS tables
            FROM information_schema.schemata s
            WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
            ORDER BY schema_name
        """)
        return [TextContent(type="text", text=render_schemas(rows))]

    if name == "list_tables":
        schema = arguments.get("schema", "public")
        rows = await pool.fetch("""
            SELECT c.relname AS name,
                   CASE c.relkind
                       WHEN 'r' THEN 'table'
                       WHEN 'v' THEN 'view'
                       WHEN 'm' THEN 'materialized view'
                       WHEN 'f' THEN 'foreign table'
                       WHEN 'p' THEN 'partitioned table'
                   END AS type,
                   c.reltuples::bigint AS approx_rows,
                   pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = $1
              AND c.relkind IN ('r', 'v', 'm', 'f', 'p')
            ORDER BY c.relname
        """, schema)

        return [TextContent(type="text", text=render_tables(schema, rows))]

    if name == "get_table_info":
        table = arguments["table"]
        schema = arguments.get("schema", "public")
        async with pool.acquire() as conn:
            # Columns
            cols = await conn.fetch("""
                SELECT column_name, data_type, is_nullable, column_default,
                       character_maximum_length, numeric_precision, numeric_scale
                FROM information_schema.columns
                WHERE table_schema = $1 AND table_name = $2
                ORDER BY ordinal_position
            """, schema, table)

            # Primary key
            pk = await conn.fetch("""
                SELECT a.attname
                FROM pg_index i
                JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                JOIN pg_class c ON c.oid = i.indrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = $1 AND c.relname = $2 AND i.indisprimary
                ORDER BY array_position(i.indkey, a.attnum)
            """, schema, table)

            # Foreign keys
            fks = await conn.fetch("""
                SELECT
                    tc.constraint_name,
                    kcu.column_name,
                    ccu.table_schema AS ref_schema,
                    ccu.table_name AS ref_table,
                    ccu.column_name AS ref_column
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage ccu
                    ON tc.constraint_name = ccu.constraint_name AND tc.table_schema = ccu.table_schema
                WHERE tc.table_schema = $1 AND tc.table_name = $2
                  AND tc.constraint_type = 'FOREIGN KEY'
            """, schema, table)

            # Indexes
            idxs = await conn.fetch("""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = $1 AND tablename = $2
                ORDER BY indexname
            """, schema, table)

            # Row count and size
            stats = await conn.fetchrow("""
                SELECT c.reltuples::bigint AS approx_rows,
                       pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size,
                       pg_size_pretty(pg_relation_size(c.oid)) AS table_size,
                       pg_size_pretty(pg_indexes_size(c.oid)) AS indexes_size
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = $1 AND c.relname = $2
            """, schema, table)
            result = build_table_info_payload(cols, pk, fks, idxs, stats)

        return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False, default=str))]

    if name == "list_indexes":
        schema = arguments.get("schema", "public")
        table = arguments.get("table")

        if table:
            rows = await pool.fetch("""
                SELECT indexname, indexdef,
                       pg_size_pretty(pg_relation_size(i.indexrelid)) AS size,
                       idx_scan, idx_tup_read, idx_tup_fetch
                FROM pg_indexes pi
                JOIN pg_stat_user_indexes i
                    ON pi.indexname = i.indexrelname AND pi.schemaname = i.schemaname
                WHERE pi.schemaname = $1 AND pi.tablename = $2
                ORDER BY pi.indexname
            """, schema, table)
        else:
            rows = await pool.fetch("""
                SELECT tablename, indexname, indexdef,
                       pg_size_pretty(pg_relation_size(i.indexrelid)) AS size,
                       idx_scan
                FROM pg_indexes pi
                JOIN pg_stat_user_indexes i
                    ON pi.indexname = i.indexrelname AND pi.schemaname = i.schemaname
                WHERE pi.schemaname = $1
                ORDER BY pi.tablename, pi.indexname
            """, schema)

        return [TextContent(type="text", text=render_indexes(rows, table))]

    if name == "list_functions":
        schema = arguments.get("schema", "public")
        rows = await pool.fetch("""
            SELECT p.proname AS name,
                   pg_get_function_arguments(p.oid) AS arguments,
                   CASE p.prokind
                       WHEN 'f' THEN 'function'
                       WHEN 'p' THEN 'procedure'
                       WHEN 'a' THEN 'aggregate'
                       WHEN 'w' THEN 'window'
                   END AS kind,
                   t.typname AS return_type
            FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            JOIN pg_type t ON t.oid = p.prorettype
            WHERE n.nspname = $1
            ORDER BY p.proname
        """, schema)

        return [TextContent(type="text", text=render_functions(schema, rows))]

    return [TextContent(type="text", text=f"Unknown schema tool: {name}")]

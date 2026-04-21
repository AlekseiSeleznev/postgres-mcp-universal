"""Health tools — PostgreSQL monitoring and diagnostics."""

from __future__ import annotations

import json

from mcp.types import TextContent, Tool

from gateway.pg_pool import pool_manager
from gateway.tools._compat_schema import compat_empty_schema
from gateway.tools.health_service import (
    build_db_health_payload,
    render_active_queries,
    render_lock_info,
    render_table_bloat,
    serialize_vacuum_stats,
)

TOOLS = [
    Tool(
        name="db_health",
        description=(
            "Comprehensive database health check: version, uptime, connections, "
            "cache hit ratio, dead tuples, long-running queries, replication lag."
        ),
        inputSchema=compat_empty_schema(),
    ),
    Tool(
        name="active_queries",
        description="Show currently running queries with duration, state, and wait events.",
        inputSchema={
            "type": "object",
            "properties": {
                "min_duration_ms": {
                    "type": "integer",
                    "description": "Only show queries running longer than N milliseconds. Default: 0",
                },
            },
        },
    ),
    Tool(
        name="table_bloat",
        description="Estimate table and index bloat for tables in a schema.",
        inputSchema={
            "type": "object",
            "properties": {
                "schema": {"type": "string", "description": "Schema name. Default: 'public'"},
            },
        },
    ),
    Tool(
        name="vacuum_stats",
        description="Show vacuum and autovacuum statistics for tables.",
        inputSchema={
            "type": "object",
            "properties": {
                "schema": {"type": "string", "description": "Schema name. Default: 'public'"},
            },
        },
    ),
    Tool(
        name="lock_info",
        description="Show current locks and any blocked/blocking queries.",
        inputSchema=compat_empty_schema(),
    ),
]


async def handle(name: str, arguments: dict, session_id: str | None = None) -> list[TextContent]:
    pool = pool_manager.get_pool(session_id)

    if name == "db_health":
        async with pool.acquire() as conn:
            # Version
            ver = await conn.fetchval("SELECT version()")

            # Uptime
            uptime = await conn.fetchval("SELECT now() - pg_postmaster_start_time()")

            # Connections
            conns = await conn.fetchrow("""
                SELECT count(*) AS total,
                       count(*) FILTER (WHERE state = 'active') AS active,
                       count(*) FILTER (WHERE state = 'idle') AS idle,
                       count(*) FILTER (WHERE state = 'idle in transaction') AS idle_in_tx,
                       (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') AS max_conn
                FROM pg_stat_activity WHERE backend_type = 'client backend'
            """)

            # Cache hit ratio
            cache = await conn.fetchrow("""
                SELECT sum(blks_hit) AS hits, sum(blks_read) AS reads,
                       CASE WHEN sum(blks_hit) + sum(blks_read) > 0
                            THEN round(sum(blks_hit)::numeric / (sum(blks_hit) + sum(blks_read)) * 100, 2)
                            ELSE 0 END AS hit_ratio_pct
                FROM pg_stat_database WHERE datname = current_database()
            """)

            # Database size
            size = await conn.fetchval("SELECT pg_size_pretty(pg_database_size(current_database()))")

            # Dead tuples (top 5)
            dead = await conn.fetch("""
                SELECT schemaname || '.' || relname AS table,
                       n_dead_tup, n_live_tup,
                       CASE WHEN n_live_tup > 0
                            THEN round(n_dead_tup::numeric / n_live_tup * 100, 1)
                            ELSE 0 END AS dead_pct
                FROM pg_stat_user_tables
                WHERE n_dead_tup > 0
                ORDER BY n_dead_tup DESC LIMIT 5
            """)

            # Long-running queries (> 5s)
            slow = await conn.fetch("""
                SELECT pid, now() - query_start AS duration,
                       state, left(query, 200) AS query
                FROM pg_stat_activity
                WHERE state != 'idle'
                  AND query NOT ILIKE '%pg_stat_activity%'
                  AND now() - query_start > interval '5 seconds'
                ORDER BY duration DESC LIMIT 5
            """)

            # Replication (if any)
            repl = await conn.fetch("""
                SELECT client_addr::text, state, sent_lsn::text, write_lsn::text,
                       flush_lsn::text, replay_lsn::text
                FROM pg_stat_replication
            """)
            result = build_db_health_payload(
                version=ver,
                uptime=uptime,
                connections_row=conns,
                cache_row=cache,
                database_size=size,
                dead_rows=dead,
                slow_rows=slow,
                replication_rows=repl,
            )

        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    if name == "active_queries":
        min_dur = arguments.get("min_duration_ms", 0)
        rows = await pool.fetch("""
            SELECT pid, usename, client_addr::text,
                   now() - query_start AS duration,
                   state, wait_event_type, wait_event,
                   left(query, 300) AS query
            FROM pg_stat_activity
            WHERE backend_type = 'client backend'
              AND state != 'idle'
              AND query NOT ILIKE '%pg_stat_activity%'
              AND EXTRACT(EPOCH FROM (now() - query_start)) * 1000 >= $1
            ORDER BY query_start
        """, min_dur)

        return [TextContent(type="text", text=render_active_queries(rows, min_dur))]

    if name == "table_bloat":
        schema = arguments.get("schema", "public")
        # pg_stat_user_tables exposes the table as `relname` (not `tablename`).
        # Quote fully-qualified names to survive mixed-case identifiers.
        rows = await pool.fetch("""
            SELECT schemaname || '.' || relname AS table,
                   pg_size_pretty(
                       pg_total_relation_size(
                           quote_ident(schemaname) || '.' || quote_ident(relname)
                       )
                   ) AS size,
                   n_dead_tup,
                   CASE WHEN n_live_tup > 0
                        THEN round(n_dead_tup::numeric / n_live_tup * 100, 1)
                        ELSE 0 END AS bloat_pct,
                   last_autovacuum::text
            FROM pg_stat_user_tables
            WHERE schemaname = $1
            ORDER BY n_dead_tup DESC
        """, schema)

        return [TextContent(type="text", text=render_table_bloat(schema, rows))]

    if name == "vacuum_stats":
        schema = arguments.get("schema", "public")
        rows = await pool.fetch("""
            SELECT relname AS table,
                   n_live_tup, n_dead_tup,
                   last_vacuum::text, last_autovacuum::text,
                   vacuum_count, autovacuum_count,
                   last_analyze::text, last_autoanalyze::text
            FROM pg_stat_user_tables
            WHERE schemaname = $1
            ORDER BY relname
        """, schema)

        if not rows:
            return [TextContent(type="text", text=f"No tables in schema '{schema}'")]

        result = serialize_vacuum_stats(rows)
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    if name == "lock_info":
        rows = await pool.fetch("""
            SELECT
                blocked_locks.pid AS blocked_pid,
                blocked_activity.usename AS blocked_user,
                left(blocked_activity.query, 200) AS blocked_query,
                blocking_locks.pid AS blocking_pid,
                blocking_activity.usename AS blocking_user,
                left(blocking_activity.query, 200) AS blocking_query
            FROM pg_catalog.pg_locks blocked_locks
            JOIN pg_catalog.pg_stat_activity blocked_activity
                ON blocked_activity.pid = blocked_locks.pid
            JOIN pg_catalog.pg_locks blocking_locks
                ON blocking_locks.locktype = blocked_locks.locktype
                AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
                AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
                AND blocking_locks.page IS NOT DISTINCT FROM blocked_locks.page
                AND blocking_locks.tuple IS NOT DISTINCT FROM blocked_locks.tuple
                AND blocking_locks.virtualxid IS NOT DISTINCT FROM blocked_locks.virtualxid
                AND blocking_locks.transactionid IS NOT DISTINCT FROM blocked_locks.transactionid
                AND blocking_locks.classid IS NOT DISTINCT FROM blocked_locks.classid
                AND blocking_locks.objid IS NOT DISTINCT FROM blocked_locks.objid
                AND blocking_locks.objsubid IS NOT DISTINCT FROM blocked_locks.objsubid
                AND blocking_locks.pid != blocked_locks.pid
            JOIN pg_catalog.pg_stat_activity blocking_activity
                ON blocking_activity.pid = blocking_locks.pid
            WHERE NOT blocked_locks.granted
        """)

        return [TextContent(type="text", text=render_lock_info(rows))]

    return [TextContent(type="text", text=f"Unknown health tool: {name}")]

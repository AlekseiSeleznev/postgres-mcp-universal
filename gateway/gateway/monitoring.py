"""PostgreSQL monitoring — comprehensive metrics collection."""

from __future__ import annotations

import logging
from gateway.pg_pool import pool_manager

log = logging.getLogger(__name__)


async def get_overview(session_id: str | None = None) -> dict:
    """Top-level server metrics: version, uptime, connections, cache, size."""
    pool = pool_manager.get_pool(session_id)
    async with pool.acquire() as conn:
        ver = await conn.fetchval("SELECT version()")
        uptime = await conn.fetchval("SELECT now() - pg_postmaster_start_time()")

        conns = await conn.fetchrow("""
            SELECT count(*) AS total,
                   count(*) FILTER (WHERE state = 'active') AS active,
                   count(*) FILTER (WHERE state = 'idle') AS idle,
                   count(*) FILTER (WHERE state = 'idle in transaction') AS idle_in_tx,
                   count(*) FILTER (WHERE state = 'idle in transaction (aborted)') AS idle_in_tx_abort,
                   (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') AS max_conn
            FROM pg_stat_activity WHERE backend_type = 'client backend'
        """)

        cache = await conn.fetchrow("""
            SELECT sum(blks_hit)::bigint AS hits, sum(blks_read)::bigint AS reads,
                   CASE WHEN sum(blks_hit) + sum(blks_read) > 0
                        THEN round(sum(blks_hit)::numeric / (sum(blks_hit) + sum(blks_read)) * 100, 2)
                        ELSE 100 END AS hit_ratio
            FROM pg_stat_database WHERE datname = current_database()
        """)

        db_stats = await conn.fetchrow("""
            SELECT xact_commit::bigint AS commits, xact_rollback::bigint AS rollbacks,
                   tup_returned::bigint, tup_fetched::bigint,
                   tup_inserted::bigint, tup_updated::bigint, tup_deleted::bigint,
                   conflicts::bigint, deadlocks::bigint,
                   pg_database_size(current_database()) AS size_bytes,
                   pg_size_pretty(pg_database_size(current_database())) AS size_pretty,
                   numbackends
            FROM pg_stat_database WHERE datname = current_database()
        """)

        # Checkpoint stats — pg_stat_checkpointer (PG17+) or pg_stat_bgwriter (PG<17)
        bgw = None
        try:
            bgw = await conn.fetchrow("""
                SELECT num_timed AS checkpoints_timed, num_requested AS checkpoints_req,
                       buffers_written::bigint AS buffers_checkpoint
                FROM pg_stat_checkpointer
            """)
        except Exception:
            pass
        if bgw is None:
            try:
                bgw = await conn.fetchrow("""
                    SELECT checkpoints_timed, checkpoints_req,
                           buffers_checkpoint::bigint
                    FROM pg_stat_bgwriter
                """)
            except Exception:
                pass

        # Background writer stats
        bgw_extra = None
        try:
            bgw_extra = await conn.fetchrow("""
                SELECT buffers_clean::bigint, buffers_alloc::bigint, maxwritten_clean
                FROM pg_stat_bgwriter
            """)
        except Exception:
            pass
        if bgw and bgw_extra:
            bgw = {**dict(bgw), **dict(bgw_extra)}

        # WAL stats (PG14+)
        wal = None
        try:
            wal = await conn.fetchrow("SELECT wal_records::bigint, wal_bytes::bigint FROM pg_stat_wal")
        except Exception:
            pass

    return {
        "version": ver,
        "uptime": str(uptime),
        "connections": dict(conns),
        "cache": dict(cache),
        "db_stats": {k: v for k, v in dict(db_stats).items()} if db_stats else {},
        "bgwriter": dict(bgw) if bgw else {},
        "wal": dict(wal) if wal else None,
    }


async def get_activity(session_id: str | None = None) -> dict:
    """Active queries, waits, long-running."""
    pool = pool_manager.get_pool(session_id)
    async with pool.acquire() as conn:
        queries = await conn.fetch("""
            SELECT pid, usename, client_addr::text, datname,
                   now() - query_start AS duration,
                   state, wait_event_type, wait_event,
                   left(query, 500) AS query
            FROM pg_stat_activity
            WHERE backend_type = 'client backend'
              AND pid != pg_backend_pid()
            ORDER BY
                CASE state WHEN 'active' THEN 0 WHEN 'idle in transaction' THEN 1 ELSE 2 END,
                query_start NULLS LAST
        """)

        locks = await conn.fetch("""
            SELECT
                bl.pid AS blocked_pid,
                ba.usename AS blocked_user,
                left(ba.query, 300) AS blocked_query,
                now() - ba.query_start AS blocked_duration,
                kl.pid AS blocking_pid,
                ka.usename AS blocking_user,
                left(ka.query, 300) AS blocking_query
            FROM pg_locks bl
            JOIN pg_stat_activity ba ON bl.pid = ba.pid
            JOIN pg_locks kl ON bl.locktype = kl.locktype
                AND kl.relation IS NOT DISTINCT FROM bl.relation
                AND kl.page IS NOT DISTINCT FROM bl.page
                AND kl.tuple IS NOT DISTINCT FROM bl.tuple
                AND kl.transactionid IS NOT DISTINCT FROM bl.transactionid
                AND kl.pid != bl.pid AND NOT bl.granted
            JOIN pg_stat_activity ka ON kl.pid = ka.pid
            WHERE kl.granted
        """)

    return {
        "queries": [
            {**dict(r), "duration": str(r["duration"])} for r in queries
        ],
        "locks": [
            {**dict(r), "blocked_duration": str(r["blocked_duration"])} for r in locks
        ],
    }


async def get_tables_stats(schema: str = "public", session_id: str | None = None) -> list[dict]:
    """Per-table statistics: size, tuples, scans, vacuum."""
    pool = pool_manager.get_pool(session_id)
    rows = await pool.fetch("""
        SELECT
            s.relname AS name,
            CASE c.relkind WHEN 'r' THEN 'table' WHEN 'v' THEN 'view'
                 WHEN 'm' THEN 'matview' WHEN 'p' THEN 'partitioned' END AS type,
            pg_total_relation_size(c.oid) AS total_bytes,
            pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size,
            pg_relation_size(c.oid) AS table_bytes,
            pg_indexes_size(c.oid) AS index_bytes,
            s.n_live_tup::bigint AS live_tuples,
            s.n_dead_tup::bigint AS dead_tuples,
            CASE WHEN s.n_live_tup > 0
                 THEN round(s.n_dead_tup::numeric / s.n_live_tup * 100, 1)
                 ELSE 0 END AS dead_pct,
            s.seq_scan::bigint,
            s.idx_scan::bigint,
            s.n_tup_ins::bigint AS inserts,
            s.n_tup_upd::bigint AS updates,
            s.n_tup_del::bigint AS deletes,
            s.last_vacuum::text,
            s.last_autovacuum::text,
            s.last_analyze::text,
            s.last_autoanalyze::text,
            s.vacuum_count::int,
            s.autovacuum_count::int
        FROM pg_stat_user_tables s
        JOIN pg_class c ON c.oid = s.relid
        WHERE s.schemaname = $1
        ORDER BY pg_total_relation_size(c.oid) DESC
    """, schema)
    return [dict(r) for r in rows]


async def get_indexes_stats(schema: str = "public", session_id: str | None = None) -> list[dict]:
    """Index usage statistics."""
    pool = pool_manager.get_pool(session_id)
    rows = await pool.fetch("""
        SELECT
            s.relname AS table_name,
            s.indexrelname AS index_name,
            s.idx_scan::bigint AS scans,
            s.idx_tup_read::bigint AS tuples_read,
            s.idx_tup_fetch::bigint AS tuples_fetched,
            pg_relation_size(s.indexrelid) AS size_bytes,
            pg_size_pretty(pg_relation_size(s.indexrelid)) AS size,
            pi.indexdef
        FROM pg_stat_user_indexes s
        JOIN pg_indexes pi ON s.indexrelname = pi.indexname AND s.schemaname = pi.schemaname
        WHERE s.schemaname = $1
        ORDER BY s.idx_scan ASC, pg_relation_size(s.indexrelid) DESC
    """, schema)
    return [dict(r) for r in rows]


async def get_replication(session_id: str | None = None) -> dict:
    """Replication status and slots."""
    pool = pool_manager.get_pool(session_id)
    async with pool.acquire() as conn:
        replicas = await conn.fetch("""
            SELECT client_addr::text, application_name, state,
                   sent_lsn::text, write_lsn::text, flush_lsn::text, replay_lsn::text,
                   write_lag::text, flush_lag::text, replay_lag::text,
                   pg_wal_lsn_diff(sent_lsn, replay_lsn)::bigint AS replay_lag_bytes
            FROM pg_stat_replication
        """)
        slots = await conn.fetch("""
            SELECT slot_name, slot_type, active,
                   pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint AS retained_bytes,
                   pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS retained_size
            FROM pg_replication_slots
        """)
    return {
        "replicas": [dict(r) for r in replicas],
        "slots": [dict(r) for r in slots],
    }


async def get_schemas(session_id: str | None = None) -> list[dict]:
    """List schemas with table counts."""
    pool = pool_manager.get_pool(session_id)
    rows = await pool.fetch("""
        SELECT n.nspname AS name,
               count(c.oid) AS tables
        FROM pg_namespace n
        LEFT JOIN pg_class c ON c.relnamespace = n.oid AND c.relkind IN ('r','v','m','p')
        WHERE n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
          AND n.nspname NOT LIKE 'pg_temp%'
        GROUP BY n.nspname
        ORDER BY n.nspname
    """)
    return [dict(r) for r in rows]

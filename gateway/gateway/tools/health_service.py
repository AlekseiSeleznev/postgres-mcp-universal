"""Pure helpers for health tool payload and text rendering."""

from __future__ import annotations

from gateway.tools._row_helpers import row_as_dict, row_get


def build_db_health_payload(
    *,
    version,
    uptime,
    connections_row,
    cache_row,
    database_size,
    dead_rows: list,
    slow_rows: list,
    replication_rows: list,
) -> dict:
    payload = {
        "version": version,
        "uptime": str(uptime),
        "connections": row_as_dict(connections_row),
        "cache": row_as_dict(cache_row),
        "database_size": database_size,
        "top_dead_tuples": [row_as_dict(r) for r in dead_rows],
        "long_queries": [{**row_as_dict(r), "duration": str(row_get(r, "duration", ""))} for r in slow_rows],
    }
    if replication_rows:
        payload["replication"] = [row_as_dict(r) for r in replication_rows]
    return payload


def render_active_queries(rows: list, min_duration_ms: int) -> str:
    if not rows:
        return "No active queries" + (f" (>{min_duration_ms}ms)" if min_duration_ms else "")
    lines = []
    for r in rows:
        wait_event = row_get(r, "wait_event")
        wait = f" [{row_get(r, 'wait_event_type')}/{wait_event}]" if wait_event else ""
        lines.append(
            f"PID {row_get(r, 'pid')} ({row_get(r, 'usename')}@{row_get(r, 'client_addr')}) "
            f"{row_get(r, 'state')} {row_get(r, 'duration')}{wait}\n  {row_get(r, 'query')}"
        )
    return "\n\n".join(lines)


def render_table_bloat(schema: str, rows: list) -> str:
    if not rows:
        return f"No tables in schema '{schema}'"
    lines = [
        f"  {row_get(r, 'table')} — {row_get(r, 'size')}, dead: {row_get(r, 'n_dead_tup')} "
        f"({row_get(r, 'bloat_pct')}%), last vacuum: {row_get(r, 'last_autovacuum') or 'never'}"
        for r in rows
    ]
    return "Table bloat:\n" + "\n".join(lines)


def serialize_vacuum_stats(rows: list) -> list[dict]:
    return [row_as_dict(r) for r in rows]


def render_lock_info(rows: list) -> str:
    if not rows:
        return "No blocked queries"
    lines = []
    for r in rows:
        lines.append(
            f"BLOCKED: PID {row_get(r, 'blocked_pid')} ({row_get(r, 'blocked_user')})\n"
            f"  Query: {row_get(r, 'blocked_query')}\n"
            f"  BY: PID {row_get(r, 'blocking_pid')} ({row_get(r, 'blocking_user')})\n"
            f"  Query: {row_get(r, 'blocking_query')}"
        )
    return "\n\n".join(lines)

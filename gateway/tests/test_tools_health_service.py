"""Tests for gateway.tools.health_service pure helpers."""

from __future__ import annotations
from gateway.tools.health_service import (
    build_db_health_payload,
    render_active_queries,
    render_lock_info,
    render_table_bloat,
    row_as_dict,
    row_get,
    serialize_vacuum_stats,
)


def _rec(data: dict):
    class _Rec:
        def __getitem__(self, k):
            return data[k]

        def keys(self):
            return list(data.keys())

        def get(self, k, default=None):
            return data.get(k, default)

        def items(self):
            return data.items()

    return _Rec()


def test_build_db_health_payload_includes_replication():
    payload = build_db_health_payload(
        version="PostgreSQL 16",
        uptime="0:01:00",
        connections_row=_rec({"total": 2}),
        cache_row=_rec({"hit_ratio_pct": 99.0}),
        database_size="10 MB",
        dead_rows=[_rec({"table": "public.t", "n_dead_tup": 1})],
        slow_rows=[_rec({"pid": 1, "duration": "0:00:06", "query": "select 1"})],
        replication_rows=[_rec({"state": "streaming"})],
    )
    assert payload["connections"]["total"] == 2
    assert payload["cache"]["hit_ratio_pct"] == 99.0
    assert payload["long_queries"][0]["duration"] == "0:00:06"
    assert payload["replication"][0]["state"] == "streaming"


def test_render_active_queries_and_lock_info():
    query_text = render_active_queries(
        [_rec({"pid": 7, "usename": "u", "client_addr": "127.0.0.1", "state": "active", "duration": "0:00:02", "wait_event_type": None, "wait_event": None, "query": "select 1"})],
        0,
    )
    assert "PID 7" in query_text

    lock_text = render_lock_info(
        [_rec({"blocked_pid": 10, "blocked_user": "a", "blocked_query": "update", "blocking_pid": 11, "blocking_user": "b", "blocking_query": "select for update"})]
    )
    assert "BLOCKED: PID 10" in lock_text
    assert "BY: PID 11" in lock_text


def test_render_table_bloat_and_serialize_vacuum_stats():
    bloat_text = render_table_bloat("public", [_rec({"table": "public.users", "size": "1 MB", "n_dead_tup": 10, "bloat_pct": 2.3, "last_autovacuum": None})])
    assert "public.users" in bloat_text
    assert "never" in bloat_text

    vacuum = serialize_vacuum_stats([_rec({"table": "users", "vacuum_count": 1})])
    assert vacuum[0]["table"] == "users"


def test_row_helpers_cover_record_fallbacks_and_empty_states():
    class KeysOnly:
        def keys(self):
            return ["value"]

        def __getitem__(self, key):
            if key == "value":
                return 7
            raise KeyError(key)

    class ItemsOnly:
        def items(self):
            return [("state", "ok")]

    class Broken:
        pass

    assert row_as_dict({"a": 1}) == {"a": 1}
    assert row_as_dict(KeysOnly()) == {"value": 7}
    assert row_as_dict(ItemsOnly()) == {"state": "ok"}
    assert row_as_dict(Broken()) == {}
    assert row_get({"a": 1}, "a") == 1
    assert row_get(Broken(), "missing", "fallback") == "fallback"
    assert render_active_queries([], 50) == "No active queries (>50ms)"
    assert render_lock_info([]) == "No blocked queries"


def test_render_active_queries_includes_wait_marker():
    query_text = render_active_queries(
        [_rec({"pid": 8, "usename": "u", "client_addr": "127.0.0.2", "state": "active", "duration": "0:00:03", "wait_event_type": "Lock", "wait_event": "transactionid", "query": "select pg_sleep(1)"})],
        0,
    )
    assert "[Lock/transactionid]" in query_text


def test_row_as_dict_keys_fallback_path_is_covered():
    class KeysFallback:
        def keys(self):
            return ["value"]

        def __getitem__(self, key):
            return 9

    assert row_as_dict(KeysFallback()) == {"value": 9}


def test_row_as_dict_handles_broken_keys_and_items_gracefully():
    class BrokenEverywhere:
        def keys(self):
            raise RuntimeError("boom")

        def items(self):
            raise RuntimeError("boom")

        def __iter__(self):
            raise RuntimeError("boom")

    assert row_as_dict(BrokenEverywhere()) == {}
